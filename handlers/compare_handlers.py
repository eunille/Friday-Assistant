# handlers/compare_handlers.py — Side-by-side comparison handler
"""Routes comparison queries to the appropriate website.
  - Crypto: CoinGecko compare
  - Stocks: Google Finance / Yahoo Finance
  - General: Google search "X vs Y"
"""
import re

from speaker import speak
from brain import is_available as llm_available, classify as llm_classify
import browser as web
from context import update_context
from logger import log


def _extract_comparison_pair(text):
    """Extract two items being compared from text.
    Handles: 'compare X and Y', 'X vs Y', 'X versus Y',
             'difference between X and Y'."""
    patterns = [
        r"compare\s+(.+?)\s+(?:and|vs|versus|with|to)\s+(.+)",
        r"difference\s+between\s+(.+?)\s+and\s+(.+)",
        r"(.+?)\s+(?:vs|versus)\s+(.+)",
        r"which\s+is\s+better\s+(.+?)\s+or\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            a = match.group(1).strip().rstrip(".,!?")
            b = match.group(2).strip().rstrip(".,!?")
            return a, b
    return None, None


_CRYPTO_NAMES = {
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "solana": "solana", "sol": "solana",
    "xrp": "ripple", "ripple": "ripple",
    "dogecoin": "dogecoin", "doge": "dogecoin",
    "cardano": "cardano", "ada": "cardano",
    "polygon": "polygon-ecosystem-token", "matic": "polygon-ecosystem-token",
    "avalanche": "avalanche-2", "avax": "avalanche-2",
    "chainlink": "chainlink", "link": "chainlink",
    "polkadot": "polkadot", "dot": "polkadot",
    "litecoin": "litecoin", "ltc": "litecoin",
    "shiba": "shiba-inu", "shib": "shiba-inu",
}


def _is_crypto(name):
    """Check if a name is a known cryptocurrency."""
    return name.lower() in _CRYPTO_NAMES


def _get_coingecko_slug(name):
    """Get CoinGecko slug for a crypto name."""
    return _CRYPTO_NAMES.get(name.lower(), name.lower())


def handle_compare(text):
    """Handle comparison queries — route to appropriate site."""
    a, b = _extract_comparison_pair(text)

    if not a or not b:
        # Try LLM extraction as fallback
        if llm_available():
            a, b = _llm_extract_pair(text)

    if not a or not b:
        speak("What two things do you want me to compare, boss?")
        return True

    # Both crypto → CoinGecko compare
    if _is_crypto(a) and _is_crypto(b):
        slug_a = _get_coingecko_slug(a)
        slug_b = _get_coingecko_slug(b)
        url = f"https://www.coingecko.com/en/coins/compare?coin_ids={slug_a}&compare_coin_ids={slug_b}"
        speak(f"Comparing {a} and {b} on CoinGecko.")
        try:
            web.open_url(url)
        except Exception as e:
            log.error(f"Browser error: {e}")
        update_context("compare", f"{a} vs {b}", url)
        return True

    # General comparison → Google search
    query = f"{a} vs {b}"
    speak(f"Comparing {a} and {b}.")
    try:
        web.search_site("https://www.google.com", query)
    except Exception as e:
        log.error(f"Browser search error: {e}")
    update_context("compare", query)
    return True


def _llm_extract_pair(text):
    """Use LLM to extract comparison pair from text."""
    prompt = (
        "Extract the two things being compared from this text.\n"
        "Reply ONLY: ITEM_A|ITEM_B\n"
        "If not a comparison: NONE\n"
        f"Text: {text}\n/no_think"
    )
    try:
        result = llm_classify(text, prompt)
        if result and "|" in result:
            parts = result.strip().split("|", 1)
            a = parts[0].strip()
            b = parts[1].strip()
            if a.upper() != "NONE" and b:
                return a, b
    except Exception:
        pass
    return None, None
