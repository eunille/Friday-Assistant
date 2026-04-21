# commands.py — Command processor (the brain)
import subprocess
import re
import random
from datetime import datetime

import httpx
import psutil
import yfinance as yf
import feedparser

from speaker import speak
from personality import get_unknown_command, get_browser_opening
from brain import chat as llm_chat, is_available as llm_available, classify as llm_classify
import browser as web
import app_launcher
from timers import start_timer, get_remaining, cancel_timer, active_timer_count
from context import update_context, get_context_summary, clear_context
import world_monitor
from config_loader import get as cfg
from logger import log


# --- Config-driven lookups (loaded once on first access) ---

_site_map = None
_news_feeds = None
_news_topics = None
_stock_symbols = None
_crypto_symbols = None
_coin_slugs = None
_overview_coins = None


def _get_site_map():
    global _site_map
    if _site_map is None:
        _site_map = cfg("sites") or {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "github": "https://github.com",
            "reddit": "https://www.reddit.com",
            "twitter": "https://twitter.com",
            "gmail": "https://mail.google.com",
            "netflix": "https://www.netflix.com",
            "spotify": "https://open.spotify.com",
        }
    return _site_map


def _get_news_feeds():
    global _news_feeds
    if _news_feeds is None:
        _news_feeds = cfg("news", "feeds") or [
            "https://feeds.bbci.co.uk/news/rss.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
        ]
    return _news_feeds


def _get_news_topics():
    global _news_topics
    if _news_topics is None:
        _news_topics = cfg("news", "topics") or {}
    return _news_topics


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


# --- Command handlers ---


def handle_open(text):
    """Open a website using Playwright browser."""
    # Detect "open/launch/start browser" regardless of exact verb
    if re.search(r"\b(?:browser|brave)\b", text):
        speak("Opening the browser, boss.")
        try:
            web.open_url("about:blank")
        except Exception as e:
            log.error(f"Browser error: {e}")
            speak("Couldn't launch the browser.")
        update_context("open", "browser")
        return True

    # Check for "open X and search for Y" pattern first
    search_match = re.search(
        r"open\s+(\w+)\s+and\s+(?:search|look)\s+(?:for\s+)?(.+)", text
    )
    if search_match:
        site_name = search_match.group(1).strip()
        query = search_match.group(2).strip()
        url = _get_site_map().get(site_name)
        if url:
            speak(f"Opening {site_name} and searching for {query}.")
            try:
                web.search_site(url, query)
                return True
            except Exception as e:
                log.error(f"Browser error: {e}")
                speak(f"Couldn't search on {site_name}.")
                return True

    for name, url in _get_site_map().items():
        if name in text:
            speak(f"Opening {name}, boss.")
            try:
                web.open_url(url)
            except Exception as e:
                log.error(f"Browser error: {e}")
                speak(f"Couldn't open {name}.")
            update_context("open", name, url)
            return True

    match = re.search(r"open\s+(.+)", text)
    if match:
        target = match.group(1).strip().rstrip(".")
        # Skip pronouns / filler words that aren't real targets
        if target in ("it", "that", "this", "something", "up", "one", "the"):
            return False
        if "." in target:
            url = target if target.startswith("http") else f"https://{target}"
            speak(get_browser_opening())
            try:
                web.open_url(url)
            except Exception as e:
                log.error(f"Browser error: {e}")
                speak(f"Couldn't open {target}.")
            update_context("open", target, url)
            return True
        # Unknown target without a dot — try app launcher first
        app_name = app_launcher.launch(target)
        if app_name:
            speak(f"Launching {app_name}, boss.")
            update_context("app", app_name)
            return True
        # Fall back to search
        speak(get_browser_opening())
        try:
            web.search_site("https://www.google.com", target)
        except Exception as e:
            log.error(f"Browser search error: {e}")
            speak(f"Couldn't search for {target}.")
        update_context("search", target)
        return True
    return False


def handle_stock(text):
    """Check stock prices — open browser first, then speak result.
    Works with 60+ known companies and uses LLM to resolve unknown ones."""
    # Try to match a known company
    symbol = None
    matched_name = None
    for name, sym in _get_stock_symbols().items():
        if name in text:
            symbol = sym
            matched_name = name
            break

    # If no match, try LLM to extract company/ticker
    if not symbol and llm_available():
        symbol, matched_name = _resolve_stock_ticker(text)

    if not symbol:
        return False

    # Announce before opening
    speak(get_browser_opening())

    # Open stock page in browser first
    try:
        web.open_url(f"https://finance.yahoo.com/quote/{symbol}")
    except Exception as e:
        log.error(f"Browser error opening stock: {e}")

    # Then speak the data
    try:
        ticker = yf.Ticker(symbol)
        price = ticker.info.get("regularMarketPrice") or ticker.info.get(
            "currentPrice"
        )
        change = ticker.info.get("regularMarketChangePercent", 0)
        display_name = ticker.info.get("shortName", matched_name.title())

        if price:
            direction = "up" if change and change > 0 else "down"
            change_val = abs(change) if change else 0
            speak(
                f"{display_name} is currently at {price:.2f} dollars, "
                f"{direction} {change_val:.1f} percent today."
            )
        else:
            speak(
                f"I pulled up {display_name} on screen, boss. "
                "Markets might be closed right now."
            )
    except Exception as e:
        speak(
            f"I've got {matched_name.title()} on screen, boss. "
            "Couldn't pull the live data though."
        )
        log.error(f"Stock error: {e}")
    update_context("stock", matched_name, f"https://finance.yahoo.com/quote/{symbol}")
    return True


def _resolve_stock_ticker(text):
    """Use LLM to extract company name and ticker from text.
    Uses classify() to avoid polluting conversation memory.
    Returns (ticker_symbol, company_name) or (None, None)."""
    system_prompt = (
        "Extract the company or stock name from this voice command "
        "and return its stock ticker symbol.\n"
        "Reply ONLY in format: TICKER|COMPANY_NAME\n"
        "If no stock/company is mentioned, reply: NONE\n\n"
        "Examples:\n"
        "- check the price of boeing -> BA|boeing\n"
        "- how is AMD doing -> AMD|amd\n"
        "- what about bitcoin -> BTC-USD|bitcoin\n"
        "- tell me a joke -> NONE"
    )
    try:
        result = llm_classify(text, system_prompt)
        if result:
            result = result.strip()
            if result.upper() == "NONE":
                return None, None
            if "|" in result:
                parts = result.split("|", 1)
                ticker = parts[0].strip().upper()
                name = parts[1].strip().lower()
                if ticker and len(ticker) <= 10:
                    return ticker, name
    except Exception:
        pass
    return None, None


def handle_news(text):
    """Open news in browser first, then speak top headlines.
    Supports topic-specific news: tech, sports, business, etc."""
    # Detect topic
    topic_feed = None
    topic_name = None
    for topic, feed_url in _get_news_topics().items():
        if topic in text:
            topic_feed = feed_url
            topic_name = topic
            break

    # Announce before opening
    if topic_name:
        speak(f"Got it. Pulling up {topic_name} news for you.")
    else:
        speak(get_browser_opening())

    # Open news in browser first
    try:
        if topic_name:
            web.open_url(f"https://news.google.com/topics/{topic_name}")
        else:
            web.open_url("https://news.google.com")
    except Exception as e:
        log.error(f"Browser error opening news: {e}")

    # Then speak headlines
    try:
        feeds = [topic_feed] if topic_feed else _get_news_feeds()
        headlines = []
        for feed_url in feeds:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:5]:
                headlines.append(entry.title)

        if headlines:
            count = min(len(headlines), 5)
            prefix = f"top {topic_name}" if topic_name else "top"
            speak(f"Here are the {prefix} {count} headlines.")
            for i, headline in enumerate(headlines[:5], 1):
                speak(f"{i}. {headline}")
        else:
            speak("I've got the news page up, boss. Couldn't pull the RSS headlines though.")
        update_context("news", topic_name)
        return True
    except Exception as e:
        speak("News page is on screen, boss. RSS feeds seem down though.")
        log.error(f"News error: {e}")
        update_context("news", topic_name)
        return True


def handle_volume(text):
    """Control system volume via pactl (PipeWire compatible)."""
    try:
        if "mute" in text or "unmute" in text:
            subprocess.run(
                ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"], check=True
            )
            speak("Audio toggled.")
            return True
        if "up" in text or "increase" in text or "louder" in text:
            subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"], check=True
            )
            speak("Volume up.")
            return True
        if "down" in text or "decrease" in text or "lower" in text or "quieter" in text:
            subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"], check=True
            )
            speak("Volume down.")
            return True
        if "max" in text or "full" in text:
            subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "100%"], check=True
            )
            speak("Volume at maximum.")
            return True
    except subprocess.CalledProcessError:
        speak("I couldn't adjust the volume.")
    return False


def handle_screenshot(text):
    """Take a screenshot using KDE's Spectacle."""
    try:
        subprocess.Popen(["spectacle", "--background", "--copy-image"])
        speak("Screenshot taken and copied to clipboard.")
        return True
    except FileNotFoundError:
        speak("Spectacle is not installed. Install it with: sudo dnf install spectacle")
        return False


def handle_search(text):
    """Search the web via Playwright browser."""
    match = re.search(r"(?:search|google|look up)\s+(?:for\s+)?(.+)", text)
    if match:
        query = match.group(1).strip()
        speak(get_browser_opening())
        try:
            web.search_site("https://www.google.com", query)
        except Exception as e:
            log.error(f"Browser search error: {e}")
            speak(f"Couldn't search for {query}.")
        update_context("search", query)
        return True
    return False


def handle_browser_action(text):
    """Handle browser interaction commands: click, go back, scroll, read page."""
    # Go back
    if any(phrase in text for phrase in ["go back", "back", "previous page"]):
        try:
            title = web.go_back()
            speak(f"Went back to {title}." if title else "Went back.")
            return True
        except Exception:
            speak("Can't go back right now.")
            return True

    # Scroll
    if any(phrase in text for phrase in ["scroll down", "page down"]):
        web.scroll_down()
        speak("Scrolled down.")
        return True
    if any(phrase in text for phrase in ["scroll up", "page up"]):
        web.scroll_up()
        speak("Scrolled up.")
        return True

    # Click something
    click_match = re.search(r"click\s+(?:on\s+)?(?:the\s+)?(.+)", text)
    if click_match:
        target = click_match.group(1).strip()
        speak(f"Clicking {target}.")
        try:
            result = web.click_element(target)
            if result:
                speak(f"Now on {result}.")
            else:
                speak(f"Couldn't find {target} to click.")
        except Exception as e:
            log.error(f"Click error: {e}")
            speak("Couldn't click that element.")
        return True

    # Read current page
    if any(phrase in text for phrase in ["read this page", "read the page", "what's on this page", "summarize this page"]):
        try:
            page_text = web.get_page_text(max_chars=2000)
            if page_text and llm_available():
                summary = llm_chat(
                    f"Summarize this web page content in 2-3 sentences for spoken delivery:\n\n{page_text}"
                )
                if summary:
                    speak(summary)
                    return True
            speak("I can see the page but couldn't summarize it.")
        except Exception as e:
            log.error(f"Read page error: {e}")
            speak("Couldn't read the current page.")
        return True

    return False


def handle_weather(text):
    """Get weather info via wttr.in."""
    # Extract city from text
    match = re.search(r"(?:weather|temperature|forecast)\s+(?:in|at|for)\s+(.+)", text)
    city = match.group(1).strip() if match else ""

    try:
        # Get spoken summary
        url = f"https://wttr.in/{city}?format=3" if city else "https://wttr.in/?format=3"
        resp = httpx.get(url, timeout=5, follow_redirects=True)
        resp.raise_for_status()
        weather_text = resp.text.strip()

        # Get detailed forecast line
        detail_url = f"https://wttr.in/{city}?format=%C+%t+%h+humidity+%w+wind" if city else "https://wttr.in/?format=%C+%t+%h+humidity+%w+wind"
        detail = httpx.get(detail_url, timeout=5, follow_redirects=True).text.strip()

        speak(f"Here's the weather, boss. {weather_text}. {detail}.")

        # Open visual in browser
        browser_url = f"https://wttr.in/{city}" if city else "https://wttr.in/"
        try:
            web.open_url(browser_url)
        except Exception as e:
            log.error(f"Browser weather error: {e}")

        update_context("weather", city or "current location", browser_url)
        return True
    except Exception as e:
        log.error(f"Weather error: {e}")
        speak("Couldn't get the weather right now, boss. Service might be down.")
        return True


def handle_timer(text):
    """Set, check, or cancel timers."""
    # Cancel timer
    if any(word in text for word in ["cancel", "stop", "clear", "remove"]):
        if cancel_timer():
            speak("Timer cancelled, boss.")
        else:
            speak("No active timers to cancel, boss.")
        return True

    # Check remaining time
    if any(phrase in text for phrase in ["how much time", "time left",
                                         "time remaining", "how long"]):
        remaining = get_remaining()
        if remaining is None:
            speak("No active timers right now, boss.")
        else:
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            if mins > 0:
                speak(f"About {mins} minutes and {secs} seconds left, boss.")
            else:
                speak(f"About {secs} seconds left, boss.")
        return True

    # Set timer — parse duration
    match = re.search(r"(\d+)\s*(second|minute|hour)s?", text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        multiplier = {"second": 1, "minute": 60, "hour": 3600}
        seconds = amount * multiplier.get(unit, 1)
        label = f"{amount}_{unit}"

        if start_timer(label, seconds):
            if unit == "second":
                speak(f"Timer set for {amount} seconds, boss.")
            elif unit == "minute":
                speak(f"Timer set for {amount} minutes, boss.")
            else:
                speak(f"Timer set for {amount} hours, boss.")
        else:
            speak("There's already a timer running with that duration, boss.")
        update_context("timer", f"{amount} {unit}s")
        return True

    speak("I didn't catch the duration, boss. Try something like 'set a timer for 5 minutes'.")
    return True


def handle_system_info(text):
    """Report system metrics — CPU, RAM, battery."""
    parts = []

    if any(word in text for word in ["cpu", "processor"]):
        cpu = psutil.cpu_percent(interval=0.5)
        parts.append(f"CPU is at {cpu}%")
    elif any(word in text for word in ["ram", "memory"]):
        mem = psutil.virtual_memory()
        used_gb = mem.used / (1024 ** 3)
        total_gb = mem.total / (1024 ** 3)
        parts.append(f"Memory usage: {used_gb:.1f} of {total_gb:.1f} gigs, that's {mem.percent}%")
    elif any(word in text for word in ["battery", "charge", "power"]):
        batt = psutil.sensors_battery()
        if batt:
            status = "charging" if batt.power_plugged else "on battery"
            parts.append(f"Battery is at {batt.percent:.0f}%, {status}")
        else:
            parts.append("No battery detected — probably on AC power")
    else:
        # Full system info
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        used_gb = mem.used / (1024 ** 3)
        total_gb = mem.total / (1024 ** 3)
        parts.append(f"CPU at {cpu}%")
        parts.append(f"Memory at {mem.percent}%, {used_gb:.1f} of {total_gb:.1f} gigs used")
        batt = psutil.sensors_battery()
        if batt:
            status = "charging" if batt.power_plugged else "on battery"
            parts.append(f"Battery at {batt.percent:.0f}%, {status}")

    speak("Here's the rundown, boss. " + ". ".join(parts) + ".")
    update_context("system")
    return True


def handle_app_launch(text):
    """Launch a desktop application by name."""
    match = re.search(r"(?:launch|start|run)\s+(?:the\s+)?(.+)", text)
    if not match:
        return False

    query = match.group(1).strip()
    app_name = app_launcher.launch(query)
    if app_name:
        speak(f"Launching {app_name}, boss.")
        update_context("app", app_name)
        return True

    return False


def handle_knowledge(text):
    """Answer questions using multi-source web research pipeline.
    Flow: acknowledge → search silently → open browser → speak analysis."""
    from personality import get_data_ready

    # Step 1: Acknowledge
    speak("Okay boss, let me look into that.")

    # Step 2: Search silently
    try:
        results = web.search_and_extract(text, max_results=5)
    except Exception as e:
        log.error(f"Web search error: {e}")
        speak("Couldn't search the web right now, boss.")
        return True

    if not results:
        speak("Couldn't find anything relevant, boss.")
        return True

    # Collect snippet context
    snippets = []
    best_url = ""
    for r in results:
        if r.get("snippet"):
            snippets.append(f"• {r['title']}: {r['snippet']}")
        if not best_url and r.get("url") and r["url"].startswith("http"):
            best_url = r["url"]

    # Visit best result for deeper content
    page_content = ""
    source_title = results[0].get("title", "") if results else ""
    if best_url:
        try:
            page_content = web.visit_and_extract(best_url, max_chars=3000)
        except Exception as e:
            log.error(f"Page visit error: {e}")

    # Build combined context
    context_parts = []
    if page_content and len(page_content) > 100:
        context_parts.append(f"Source ({source_title}):\n{page_content[:2000]}")
    if snippets:
        context_parts.append("Other search results:\n" + "\n".join(snippets[:3]))

    context = "\n\n".join(context_parts)

    if not context:
        speak("I've pulled up the results on screen, boss. Take a look.")
        update_context("knowledge", text)
        return True

    # Step 3: Announce data ready + open browser
    speak(get_data_ready())

    # Step 4: Speak analysis with reasoning
    if llm_available():
        prompt = (
            f"You are Friday, an analytical AI assistant. "
            f"Based on this web research, answer the question: \"{text}\"\n\n"
            f"{context[:2500]}\n\n"
            f"Give a conversational answer in 4-6 sentences. Don't just read facts — "
            f"reason about them, share what's interesting or important. "
            f"If comparing things, explain the key differences with your own insight. "
            f"Mention the source briefly. Speak naturally as if discussing with a colleague."
            f"\n/no_think"
        )
        answer = llm_chat(prompt)
        if answer:
            speak(answer)
        else:
            _speak_raw_content(page_content, snippets)
    else:
        _speak_raw_content(page_content, snippets)

    update_context("knowledge", text)
    return True


def _speak_raw_content(page_content, snippets):
    """Fallback: speak raw content when LLM is unavailable."""
    if page_content:
        lines = [ln for ln in page_content.split("\n") if len(ln.strip()) > 20][:4]
        if lines:
            speak(f"Here's what I found. {'. '.join(lines)[:400]}")
            return
    if snippets:
        speak(f"Here's what I found. {snippets[0][:400]}")
        return
    speak("I've pulled up the results on screen, boss.")


# Topic keywords for World Monitor sub-commands
_WM_TOPIC_KEYWORDS = {
    "conflicts": ["conflict", "war", "military conflict", "armed conflict", "battles"],
    "energy": ["oil price", "energy", "crude oil", "natural gas", "brent", "opec"],
    "disease": ["disease", "outbreak", "pandemic", "epidemic", "health crisis"],
    "nuclear": ["nuclear", "radiation", "enrichment", "nuclear threat"],
    "maritime": ["maritime", "waterway", "chokepoint", "strait", "suez",
                 "panama canal", "naval", "shipping"],
    "sanctions": ["sanction", "trade war", "tariff", "embargo", "economic warfare"],
    "market_stress": ["market stress", "vix", "fear and greed", "treasury yield",
                      "macro stress"],
    "cyber": ["cyber", "cyber threat", "ransomware", "data breach", "infosec"],
    "reddit": ["reddit", "trending on reddit", "social velocity"],
    "disasters": ["disaster", "earthquake", "tsunami", "hurricane", "typhoon",
                  "wildfire", "flood", "climate"],
}


def _detect_wm_topic(text):
    """Detect if the user is asking about a specific World Monitor sub-topic.
    Returns the topic key or 'overview' for general queries."""
    for topic, keywords in _WM_TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return topic
    return "overview"


def handle_world_monitor(text):
    """Fetch global intelligence from World Monitor with conversational flow.
    Flow: acknowledge → search → open browser → speak analysis."""
    from personality import get_data_ready
    topic = _detect_wm_topic(text)

    # Step 1: Acknowledge
    if topic == "overview":
        speak("Okay boss, let me check the global situation.")
    else:
        speak(f"Okay boss, let me check {topic.replace('_', ' ')}.")

    # Step 2: Fetch data silently
    if topic == "overview":
        data = world_monitor.fetch_world_brief()
        summary = world_monitor.summarize_for_speech(data)
        raw_context = summary
    else:
        topic_text = world_monitor.fetch_topic(topic)
        summary = world_monitor.summarize_topic_for_speech(topic, topic_text)
        raw_context = topic_text

    # Step 3: Open browser
    speak(get_data_ready())
    try:
        web.open_url(world_monitor._WM_URL)
    except Exception as e:
        log.error(f"Browser error opening World Monitor: {e}")

    # Step 4: Speak analysis with reasoning
    if llm_available() and raw_context:
        prompt = (
            f"You are Friday, an analytical AI assistant. "
            f"Based on this {topic.replace('_', ' ')} intelligence data, give a conversational briefing "
            f"in 4-6 sentences. Don't just list facts — reason about them. "
            f"Share what stands out, what's concerning, or what's interesting. "
            f"Start with something like 'So here's what's going on...' or 'Hmm, interesting...' "
            f"Speak naturally as if discussing with a colleague.\n\n"
            f"Data:\n{raw_context}\n/no_think"
        )
        refined = llm_chat(prompt)
        if refined:
            speak(refined)
        else:
            speak(summary)
    else:
        speak(summary)

    update_context("world_monitor", topic)
    return True


def handle_crypto(text):
    """Check cryptocurrency prices with conversational flow.
    Flow: acknowledge → fetch data silently → open browser → speak analysis."""
    from personality import get_data_ready
    # Try to match a specific coin
    symbol = None
    coin_name = None
    for name, sym in _get_crypto_symbols().items():
        if name in text:
            symbol = sym
            coin_name = name
            break

    # If no specific coin, give top crypto overview
    if not symbol:
        speak("Okay boss, let me check the crypto market.")
        parts = []
        for sym, name in _get_overview_coins():
            try:
                ticker = yf.Ticker(sym)
                price = ticker.info.get("regularMarketPrice") or ticker.info.get("currentPrice")
                change = ticker.info.get("regularMarketChangePercent", 0)
                if price:
                    direction = "up" if change and change > 0 else "down"
                    change_val = abs(change) if change else 0
                    if price >= 1:
                        parts.append(f"{name} at {price:,.2f} dollars, {direction} {change_val:.1f} percent")
                    else:
                        parts.append(f"{name} at {price:.6f} dollars, {direction} {change_val:.1f} percent")
            except Exception:
                continue

        speak(get_data_ready())
        try:
            web.open_url("https://www.coingecko.com")
        except Exception as e:
            log.error(f"Browser error opening CoinGecko: {e}")

        if parts:
            raw_data = ". ".join(parts)
            if llm_available():
                prompt = (
                    f"You are Friday, an analytical AI assistant. "
                    f"Here's today's crypto data: {raw_data}. "
                    f"Give a quick 3-4 sentence analysis. Don't just list prices — "
                    f"note what's interesting: which coins are moving, any trends, "
                    f"what stands out. Speak naturally.\n/no_think"
                )
                analysis = llm_chat(prompt)
                if analysis:
                    speak(analysis)
                else:
                    speak("Here's the crypto overview. " + raw_data + ".")
            else:
                speak("Here's the crypto overview. " + raw_data + ".")
        else:
            speak("I couldn't pull crypto data right now, boss.")

        update_context("crypto")
        return True

    # Specific coin query
    slug = _get_coin_slugs().get(coin_name, coin_name)
    speak(f"Okay boss, let me check {coin_name}.")
    try:
        ticker = yf.Ticker(symbol)
        price = ticker.info.get("regularMarketPrice") or ticker.info.get("currentPrice")
        change = ticker.info.get("regularMarketChangePercent", 0)
        display_name = ticker.info.get("shortName", coin_name.title())

        speak(get_data_ready())
        try:
            web.open_url(f"https://www.coingecko.com/en/coins/{slug}")
        except Exception as e:
            log.error(f"Browser error opening crypto page: {e}")

        if price:
            direction = "up" if change and change > 0 else "down"
            change_val = abs(change) if change else 0
            if price >= 1:
                price_str = f"{price:,.2f}"
            else:
                price_str = f"{price:.6f}"

            if llm_available():
                prompt = (
                    f"You are Friday, an analytical AI assistant. "
                    f"{display_name} is currently at {price_str} dollars, "
                    f"{direction} {change_val:.1f} percent. "
                    f"Give a quick 2-3 sentence analysis. Report the price and change, "
                    f"then add brief context or observation. Speak naturally.\n/no_think"
                )
                analysis = llm_chat(prompt)
                if analysis:
                    speak(analysis)
                else:
                    speak(f"{display_name} is at {price_str} dollars, {direction} {change_val:.1f} percent.")
            else:
                speak(f"{display_name} is at {price_str} dollars, {direction} {change_val:.1f} percent.")
        else:
            speak(f"{display_name} data isn't available right now. Markets might be updating.")
    except Exception as e:
        speak(f"Couldn't pull {coin_name} data right now, boss.")
        log.error(f"Crypto error: {e}")

    update_context("crypto", coin_name)
    return True


def handle_time(text):
    """Tell the current time."""
    now = datetime.now()
    time_str = now.strftime("%I:%M %p")
    speak(f"It's currently {time_str}.")
    update_context("time")
    return True


# --- Routing helpers ---


def _has_word(text, *words):
    """Check if any of the given words/phrases appear in text.
    Phrases (containing spaces) use substring match.
    Single words use word-boundary regex for precision."""
    for word in words:
        if " " in word:
            if word in text:
                return True
        else:
            if re.search(r"\b" + re.escape(word) + r"\b", text):
                return True
    return False


# --- Main dispatcher ---


def process_command(text):
    """Route transcribed text to the correct command handler.

    Routing strategy (3-tier):
      1. Keyword matching with word boundaries (fast path)
      2. LLM intent classification (smart fallback)
      3. LLM conversational chat / witty unknown-command response
    """
    if not text or len(text.strip()) < 2:
        return

    text = text.lower().strip()

    # Quick exit — non-actionable phrases
    if _has_word(text, "thanks", "thank you", "never mind", "nevermind",
                 "that's all", "forget it", "goodbye", "bye"):
        speak("Anytime, boss.")
        return

    # --- Tier 1: Keyword routing (order matters — more specific first) ---

    # Skip stock/crypto for comparison/general questions
    _is_comparison = _has_word(text, "difference", "compare", "versus",
                               "vs", "similarity", "between",
                               "better", "which is")

    # Crypto before stock — crypto coin names should route to crypto handler
    if not _is_comparison and _has_word(
            text, "crypto", "bitcoin", "btc", "ethereum",
            "eth", "solana", "dogecoin", "doge",
            "xrp", "ripple", "cardano", "litecoin",
            "shiba", "pepe", "sui", "toncoin",
            "avalanche", "polygon", "chainlink",
            "near", "kaspa"):
        if handle_crypto(text):
            return

    if not _is_comparison and _has_word(
            text, "stock", "price", "share", "ticker",
            "how much", "worth", "trading"):
        if handle_stock(text):
            return

    if _has_word(text, "world monitor", "global monitor",
                 "global intelligence", "world situation",
                 "global situation", "world events",
                 "what's happening around the world",
                 "what's happening in the world",
                 "happening in the world",
                 "happening around the world",
                 "what's going on in the world",
                 "global report", "world report",
                 "world news", "global news",
                 "armed conflict", "nuclear threat",
                 "maritime situation", "cyber threat",
                 "market stress", "disease outbreak",
                 "natural disaster", "trending on reddit",
                 "oil price", "energy situation",
                 "sanction", "trade war"):
        if handle_world_monitor(text):
            return

    if _has_word(text, "news", "headlines", "what's happening", "what is happening"):
        # "what's happening" without world/global context → regular news
        if "world" not in text and "global" not in text:
            if handle_news(text):
                return

    if _has_word(text, "volume", "louder", "quieter", "mute", "unmute"):
        if handle_volume(text):
            return

    if _has_word(text, "screenshot", "screen shot",
                 "capture screen", "take a picture"):
        if handle_screenshot(text):
            return

    if _has_word(text, "search", "google", "look up", "look for",
                 "find me", "find out"):
        if handle_search(text):
            return

    if _has_word(text, "click", "go back", "scroll", "read this",
                 "read the page", "summarize this"):
        if handle_browser_action(text):
            return

    # Time — restrictive patterns to avoid "what time does the movie start"
    if any(phrase in text for phrase in [
            "what time", "what's the time", "tell me the time"]) \
            or text in ("time", "clock"):
        if handle_time(text):
            return

    if _has_word(text, "weather", "temperature", "forecast",
                 "rain", "sunny", "hot outside", "cold outside"):
        if handle_weather(text):
            return

    if _has_word(text, "timer", "alarm", "countdown",
                 "time left", "time remaining"):
        if handle_timer(text):
            return

    if _has_word(text, "cpu", "ram", "memory usage", "battery",
                 "system info", "system status"):
        if handle_system_info(text):
            return

    # App launch — "launch/start/run" verbs checked BEFORE "open"
    # so "launch spotify" prefers desktop app over website
    if _has_word(text, "launch", "start", "run"):
        if handle_app_launch(text):
            return

    if _has_word(text, "open", "go to", "navigate", "browser", "brave"):
        if handle_open(text):
            return

    # --- Tier 2: LLM intent classification ---
    if llm_available():
        intent, entity = _classify_intent(text)

        if intent == "stock":
            if handle_stock(text):
                return
            # Stock name not in our list — search it
            query = entity or text
            speak(get_browser_opening())
            try:
                web.search_site("https://www.google.com", f"{query} stock price")
            except Exception as e:
                log.error(f"Browser search error: {e}")
            speak(f"I've pulled up {query} stock info on screen, boss.")
            update_context("stock", query)
            return

        if intent == "news":
            handle_news(text)
            return

        if intent == "search":
            query = entity or text
            speak(get_browser_opening())
            try:
                web.search_site("https://www.google.com", query)
            except Exception as e:
                log.error(f"Browser search error: {e}")
            update_context("search", query)
            return

        if intent == "open":
            if handle_open(text):
                return
            # Couldn't match a site — search for it
            query = entity or text
            speak(get_browser_opening())
            try:
                web.search_site("https://www.google.com", query)
            except Exception as e:
                log.error(f"Browser search error: {e}")
            update_context("open", query)
            return

        if intent == "time":
            handle_time(text)
            return

        if intent == "volume":
            handle_volume(text)
            return

        if intent == "weather":
            handle_weather(text)
            return

        if intent == "timer":
            handle_timer(text)
            return

        if intent == "system":
            handle_system_info(text)
            return

        if intent == "app":
            if handle_app_launch(text):
                return
            # Couldn't match — try launching entity directly
            if entity:
                app_name = app_launcher.launch(entity)
                if app_name:
                    speak(f"Launching {app_name}, boss.")
                    update_context("app", app_name)
                    return
            speak("Couldn't find that app, boss.")
            return

        if intent == "knowledge":
            handle_knowledge(entity or text)
            return

        if intent == "world_monitor":
            handle_world_monitor(text)
            return

        if intent == "crypto":
            handle_crypto(text)
            return

        # --- Tier 3: Generic LLM conversation (intent == "chat") ---
        response = llm_chat(text)
        if response:
            speak(response)
            return

    # Ultimate fallback — witty response
    speak(get_unknown_command(text))


def _classify_intent(text):
    """Ask the LLM to classify user intent and extract the key entity.
    Uses classify() to avoid polluting conversation memory.
    Injects session context for follow-up resolution.
    Returns (intent, entity) tuple."""
    ctx_summary = get_context_summary()
    system_prompt = (
        "You are a command classifier. Classify voice commands into categories "
        "and extract the key entity. Reply ONLY in format: CATEGORY|ENTITY\n"
        "If no entity, reply: CATEGORY|none\n\n"
        "Categories: stock, news, search, open, time, volume, screenshot, weather, timer, system, app, knowledge, world_monitor, crypto, chat\n\n"
        f"Session context: {ctx_summary}\n\n"
        "IMPORTANT: Use context for follow-up resolution. If user says "
        "'what about Apple' and context shows current_topic=stock, "
        "classify as stock|apple. If user says 'how about sports' and "
        "context is news, classify as news|sports.\n\n"
        "Examples:\n"
        "- can you check the price of tesla -> stock|tesla\n"
        "- what about apple (context: stock) -> stock|apple\n"
        "- how about nvidia (context: stock) -> stock|nvidia\n"
        "- what is happening in the world -> world_monitor|none\n"
        "- what's going on in the world -> world_monitor|none\n"
        "- world news -> world_monitor|none\n"
        "- global news -> world_monitor|none\n"
        "- how about tech news (context: news) -> news|tech\n"
        "- search for python tutorials -> search|python tutorials\n"
        "- open youtube -> open|youtube\n"
        "- what time is it -> time|none\n"
        "- what's the weather in manila -> weather|manila\n"
        "- is it going to rain -> weather|none\n"
        "- set a timer for 5 minutes -> timer|5 minutes\n"
        "- how much time is left -> timer|none\n"
        "- what's my battery level -> system|battery\n"
        "- system info -> system|none\n"
        "- launch vs code -> app|vs code\n"
        "- start the terminal -> app|terminal\n"
        "- who invented the internet -> knowledge|who invented the internet\n"
        "- what is quantum computing -> knowledge|quantum computing\n"
        "- how tall is the eiffel tower -> knowledge|eiffel tower height\n"
        "- difference between crypto and stocks -> knowledge|difference between crypto and stocks\n"
        "- compare bitcoin and ethereum -> knowledge|compare bitcoin and ethereum\n"
        "- which is better solana or ethereum -> knowledge|solana vs ethereum\n"
        "- what's the world situation -> world_monitor|none\n"
        "- global intelligence report -> world_monitor|none\n"
        "- world monitor -> world_monitor|none\n"
        "- what's happening globally -> world_monitor|none\n"
        "- any conflicts happening -> world_monitor|conflicts\n"
        "- maritime situation -> world_monitor|maritime\n"
        "- cyber threats -> world_monitor|cyber\n"
        "- any disease outbreaks -> world_monitor|disease\n"
        "- how is bitcoin doing -> crypto|bitcoin\n"
        "- check ethereum price -> crypto|ethereum\n"
        "- crypto prices -> crypto|none\n"
        "- how much is solana -> crypto|solana\n"
        "- how are you doing -> chat|none"
    )
    try:
        result = llm_classify(text, system_prompt)
        if result:
            result = result.strip().lower().rstrip(".")
            if "|" in result:
                parts = result.split("|", 1)
                category = parts[0].strip()
                entity = parts[1].strip()
                if entity == "none":
                    entity = None
                if category in ("stock", "news", "search", "open", "time",
                                "volume", "screenshot", "weather", "timer",
                                "system", "app", "knowledge", "world_monitor",
                                "crypto"):
                    return category, entity
            result = result.split()[0] if result else "chat"
            if result in ("stock", "news", "search", "open", "time",
                          "volume", "screenshot", "weather", "timer",
                          "system", "app", "knowledge", "world_monitor",
                          "crypto"):
                return result, None
    except Exception:
        pass
    return "chat", None
