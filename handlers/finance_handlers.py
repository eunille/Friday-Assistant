# handlers/finance_handlers.py — Stock, crypto, and commodity handlers
import yfinance as yf
import threading
import json
from urllib.request import urlopen, Request
from urllib.error import URLError

from speaker import speak
from personality import (
    get_browser_opening, get_data_ready, get_summary_done,
    get_thinking_pause, get_market_quip, get_repeat_quip,
)
from brain import is_available as llm_available, classify as llm_classify
import browser as web
from context import update_context
from config_loader import get as cfg
from logger import log
import time as _time


_COINGECKO_API = "https://api.coingecko.com/api/v3"

# Track recent queries for repeat-sarcasm: {topic_key: last_timestamp}
_last_query_time: dict = {}
_REPEAT_WINDOW = 300  # seconds — queries within 5 min trigger quip


def _check_repeat(topic_key):
    """Return a repeat quip if this topic was recently queried, else empty string."""
    now = _time.time()
    if topic_key in _last_query_time and (now - _last_query_time[topic_key]) < _REPEAT_WINDOW:
        return get_repeat_quip(topic_key)
    _last_query_time[topic_key] = now
    return ""


_stock_symbols = None
_crypto_symbols = None
_coin_slugs = None
_overview_coins = None


def _get_stock_symbols():
    global _stock_symbols
    if _stock_symbols is None:
        _stock_symbols = cfg("stocks") or {}
    return _stock_symbols


def _get_crypto_symbols():
    global _crypto_symbols
    if _crypto_symbols is None:
        _crypto_symbols = cfg("crypto", "symbols") or {}
    return _crypto_symbols


def _get_coin_slugs():
    global _coin_slugs
    if _coin_slugs is None:
        _coin_slugs = cfg("crypto", "slugs") or {}
    return _coin_slugs


def _get_overview_coins():
    global _overview_coins
    if _overview_coins is None:
        raw = cfg("crypto", "overview_coins") or [
            {"symbol": "BTC-USD", "name": "Bitcoin"},
            {"symbol": "ETH-USD", "name": "Ethereum"},
            {"symbol": "SOL-USD", "name": "Solana"},
            {"symbol": "XRP-USD", "name": "XRP"},
            {"symbol": "DOGE-USD", "name": "Dogecoin"},
        ]
        _overview_coins = [(c["symbol"], c["name"]) for c in raw]
    return _overview_coins


def get_crypto_keywords():
    """Return all crypto coin names for dynamic routing."""
    symbols = _get_crypto_symbols()
    keywords = set(symbols.keys()) if symbols else set()
    keywords.add("crypto")
    return keywords


def handle_stock(text):
    """Check stock prices — open browser first, then speak result."""
    symbol = None
    matched_name = None
    for name, sym in _get_stock_symbols().items():
        if name in text:
            symbol = sym
            matched_name = name
            break

    if not symbol and llm_available():
        symbol, matched_name = _resolve_stock_ticker(text)

    if not symbol:
        return False

    # Repeat-query sarcasm
    repeat = _check_repeat(f"stock:{symbol}")
    if repeat:
        speak(repeat)

    # Run browser, data fetch, and TTS in parallel
    stock_data = {}

    def _fetch_price():
        try:
            ticker = yf.Ticker(symbol)
            fi = ticker.fast_info
            stock_data["price"] = fi.get("lastPrice") or fi.get("regularMarketPrice")
            stock_data["prev_close"] = fi.get("previousClose")
            stock_data["name"] = matched_name.title()
        except Exception as e:
            log.error(f"Stock data error: {e}")

    def _open_browser():
        try:
            web.open_url(f"https://finance.yahoo.com/quote/{symbol}")
        except Exception as e:
            log.error(f"Browser error opening stock: {e}")

    t_price = threading.Thread(target=_fetch_price, daemon=True)
    t_browser = threading.Thread(target=_open_browser, daemon=True)
    t_price.start()
    t_browser.start()
    if not repeat:
        speak(get_processing_start())
    t_price.join(timeout=10)
    t_browser.join(timeout=15)

    price = stock_data.get("price")
    prev_close = stock_data.get("prev_close")
    display_name = stock_data.get("name", matched_name.title())

    if price:
        if prev_close and prev_close > 0:
            change_pct = ((price - prev_close) / prev_close) * 100
            direction = "up" if change_pct > 0 else "down"
            speak(
                f"{get_thinking_pause()} {display_name} at {price:.2f} dollars, "
                f"{direction} {abs(change_pct):.1f} percent today."
            )
            quip = get_market_quip(direction, change_pct)
            if quip:
                speak(quip)
        else:
            speak(f"{get_thinking_pause()} {display_name} at {price:.2f} dollars.")
    else:
        speak(
            f"I've got {display_name} on screen. "
            "Couldn't pull the live data though."
        )

    speak(get_summary_done())
    update_context("stock", matched_name, f"https://finance.yahoo.com/quote/{symbol}")
    return True


def _resolve_stock_ticker(text):
    """Use LLM to extract a financial asset and its yfinance ticker.
    Handles stocks, commodities, futures, indices — anything on yfinance."""
    system_prompt = (
        "Extract the financial asset from this voice command "
        "and return its yfinance ticker symbol.\n"
        "This includes stocks, commodities, futures, and indices.\n"
        "Reply ONLY in format: TICKER|ASSET_NAME\n"
        "If no financial asset is mentioned, reply: NONE\n\n"
        "Examples:\n"
        "- check the price of boeing -> BA|boeing\n"
        "- how is AMD doing -> AMD|amd\n"
        "- check the oil price -> CL=F|crude oil\n"
        "- what about gold -> GC=F|gold\n"
        "- silver price -> SI=F|silver\n"
        "- natural gas -> NG=F|natural gas\n"
        "- check brent crude -> BZ=F|brent crude\n"
        "- copper price -> HG=F|copper\n"
        "- wheat futures -> ZW=F|wheat\n"
        "- coffee price -> KC=F|coffee\n"
        "- check the S&P 500 -> ^GSPC|s&p 500\n"
        "- tell me a joke -> NONE\n/no_think"
    )
    try:
        result = llm_classify(text, system_prompt)
        if result:
            result = result.strip()
            if result.upper() == "NONE":
                return None, None
            if "|" in result:
                parts = result.split("|", 1)
                ticker = parts[0].strip()
                name = parts[1].strip().lower()
                # Keep case for tickers like CL=F, ^GSPC
                if ticker and len(ticker) <= 10:
                    return ticker, name
    except Exception:
        pass
    return None, None


def _coingecko_prices(coin_ids):
    """Fetch prices from CoinGecko API. coin_ids is a list of CoinGecko slugs.
    Returns dict: {slug: {usd, usd_24h_change}} or empty dict on failure."""
    ids_str = ",".join(coin_ids)
    url = (f"{_COINGECKO_API}/simple/price"
           f"?ids={ids_str}&vs_currencies=usd&include_24hr_change=true")
    try:
        req = Request(url, headers={"Accept": "application/json",
                                     "User-Agent": "Friday-Assistant/1.0"})
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log.error(f"CoinGecko API error: {e}")
        return {}


def handle_crypto(text):
    """Check cryptocurrency prices via CoinGecko API."""
    coin_name = None
    for name in _get_crypto_symbols():
        if name in text:
            coin_name = name
            break

    coin_slugs = _get_coin_slugs()

    if not coin_name:
        # Overview mode — fetch all overview coins at once
        speak("Okay boss, let me check the crypto market.")
        overview = _get_overview_coins()
        # Map overview coin names → slugs
        slug_map = {}
        for _, name in overview:
            slug = coin_slugs.get(name.lower(), name.lower())
            slug_map[slug] = name

        data = _coingecko_prices(list(slug_map.keys()))

        def _open_overview_browser():
            try:
                web.open_url("https://www.coingecko.com")
            except Exception as e:
                log.error(f"Browser error opening CoinGecko: {e}")

        t_browser = threading.Thread(target=_open_overview_browser, daemon=True)
        t_browser.start()

        parts = []
        for slug, display_name in slug_map.items():
            coin_data = data.get(slug)
            if not coin_data:
                continue
            price = coin_data.get("usd")
            change = coin_data.get("usd_24h_change", 0) or 0
            if price is None:
                continue
            direction = "up" if change > 0 else "down"
            price_str = f"{price:,.2f}" if price >= 1 else f"{price:.6f}"
            parts.append(f"{display_name} at {price_str} dollars, {direction} {abs(change):.1f} percent")

        t_browser.join(timeout=15)

        if parts:
            speak("Here's the crypto overview. " + ". ".join(parts) + ".")
        else:
            speak("I couldn't pull crypto data right now, boss.")

        speak(get_summary_done())
        update_context("crypto")
        return True

    # Single coin mode
    slug = coin_slugs.get(coin_name, coin_name)
    speak(f"Okay boss, let me check {coin_name}.")

    coin_data = {}

    def _fetch_coin():
        result = _coingecko_prices([slug])
        if slug in result:
            coin_data.update(result[slug])

    def _open_coin_browser():
        try:
            web.open_url(f"https://www.coingecko.com/en/coins/{slug}")
        except Exception as e:
            log.error(f"Browser error opening crypto page: {e}")

    t1 = threading.Thread(target=_fetch_coin, daemon=True)
    t2 = threading.Thread(target=_open_coin_browser, daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=15)

    price = coin_data.get("usd")
    change = coin_data.get("usd_24h_change", 0) or 0
    display_name = coin_name.title()

    if price:
        direction = "up" if change > 0 else "down"
        price_str = f"{price:,.2f}" if price >= 1 else f"{price:.6f}"
        speak(f"{display_name} is at {price_str} dollars, {direction} {abs(change):.1f} percent.")
    else:
        speak(f"{display_name} data isn't available right now. Markets might be updating.")

    speak(get_summary_done())
    update_context("crypto", coin_name)
    return True
