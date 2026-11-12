# world_monitor.py — World Monitor integration (worldmonitor.app)
"""Simple scraper for worldmonitor.app — opens the site, scrapes text,
extracts a speakable overview. No categories, no layers, no menus."""

import re
import time

from friday.browser import controller as web
from friday.core.config import get as cfg
from friday.core.log import log


_WM_URL = "https://www.worldmonitor.app/"

_cached_page_text = None
_cache_timestamp = 0


def _scrape_timeout():
    return cfg("world_monitor", "scrape_timeout") or 20000


def _render_wait():
    return cfg("world_monitor", "render_wait") or 5000


def _cache_ttl():
    return cfg("world_monitor", "cache_ttl") or 300


def _is_cache_valid():
    if _cached_page_text is None:
        return False
    return (time.time() - _cache_timestamp) < _cache_ttl()


def scrape():
    """Navigate to World Monitor and grab the page text.
    Uses the main browser page. Returns raw text or None."""
    global _cached_page_text, _cache_timestamp
    if _is_cache_valid():
        return _cached_page_text
    try:
        _, page = web._ensure_browser()
        with web._OP_LOCK:
            page.goto(_WM_URL, wait_until="domcontentloaded",
                      timeout=_scrape_timeout())
            try:
                page.wait_for_selector(
                    "text=/WORLD BRIEF|GLOBAL SITUATION|BREAKING/i",
                    timeout=_render_wait(),
                )
            except Exception:
                # Fallback: wait a fixed time for content to load
                time.sleep(3)
            raw = page.inner_text("body")
        _cached_page_text = raw
        _cache_timestamp = time.time()
        return raw
    except Exception as e:
        log.error(f"World Monitor scrape error: {e}")
        return None


def _sanitize_for_speech(text):
    """Strip non-English and non-speakable content for TTS.
    Removes repeated characters, non-ASCII noise, and garbled text."""
    # Remove non-ASCII characters (keeps English text clean for Piper)
    text = re.sub(r'[^\x20-\x7E]', ' ', text)
    # Collapse repeated characters (e.g. "yehehe" → remove)
    text = re.sub(r'(.)\1{3,}', '', text)
    # Remove lines that are mostly non-word characters
    lines = []
    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped:
            continue
        # Count actual word characters vs total
        word_chars = len(re.findall(r'[a-zA-Z]', stripped))
        if len(stripped) > 0 and word_chars / len(stripped) < 0.5:
            continue
        # Skip very short fragments
        if len(stripped) < 10:
            continue
        lines.append(stripped)
    return '\n'.join(lines)


def get_overview(raw=None):
    """Extract a short speakable overview from WM page text.
    Returns a string ready for TTS (max ~500 chars)."""
    if raw is None:
        raw = _cached_page_text or scrape()
    if not raw:
        log.warning("WM overview: no raw text available")
        return None

    log.debug(f"WM overview: raw text length = {len(raw)}")
    parts = []

    # Extract WORLD BRIEF — appears inline after emoji header
    brief = _extract_section(raw, r'WORLD\s*BRIEF\s*', limit=500)
    log.debug(f"WM overview: brief = {repr(brief[:120]) if brief else 'EMPTY'}")
    if brief:
        parts.append(brief)

    # Extract BREAKING headlines
    breaking = _extract_breaking(raw, max_items=3)
    log.debug(f"WM overview: breaking = {repr(breaking[:120]) if breaking else 'EMPTY'}")
    if breaking:
        parts.append(breaking)

    if not parts:
        log.warning("WM overview: no sections extracted")
        return None

    summary = _sanitize_for_speech(". ".join(parts))
    log.debug(f"WM overview: sanitized length = {len(summary)}")

    if len(summary) > 500:
        cut = summary[:500]
        last_end = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
        summary = cut[:last_end + 1] if last_end > 50 else cut.rsplit(" ", 1)[0] + "."

    # Final safety — check the summary is mostly real English words
    word_chars = len(re.findall(r'[a-zA-Z]', summary))
    if len(summary) > 0 and word_chars / len(summary) < 0.4:
        log.warning(f"WM overview: failed alpha check ({word_chars}/{len(summary)})")
        return None

    log.info(f"WM overview: returning {len(summary)} chars")
    return summary


def _extract_section(raw, header_pattern, limit=500):
    """Extract text following a section header pattern (inline or standalone)."""
    match = re.search(header_pattern, raw, re.IGNORECASE)
    if not match:
        return ""
    start = match.end()
    chunk = raw[start:start + limit]
    # Take text up to next section marker or widget boundary
    end_match = re.search(
        r'FOCAL\s*POINT|BREAKING|STRATEGIC|AI\s*INSIGHTS|AI\s*FORECAST|'
        r'FORCE\s*POSTURE|ESCALATION|ECONOMIC|SECTOR|LIVE\s*INTELLIGENCE',
        chunk, re.IGNORECASE
    )
    if end_match:
        chunk = chunk[:end_match.start()]
    # Clean up: take meaningful text fragments (>10 chars, mostly words)
    lines = [ln.strip() for ln in chunk.split('\n') if ln.strip() and len(ln.strip()) > 10]
    return " ".join(lines[:8])


def _extract_breaking(raw, max_items=3):
    """Extract BREAKING & CONFIRMED headlines."""
    match = re.search(r'BREAKING\s*[&]\s*CONFIRMED', raw, re.IGNORECASE)
    if not match:
        return ""
    start = match.end()
    chunk = raw[start:start + 800]
    # Headlines follow ALERT markers: "⚠ ALERTconflictHeadline text2 sources"
    # No space between ALERTtype and headline text on WM page
    headlines = re.findall(
        r'ALERT[a-z]*\s*(.{20,120}?)(?:\d+\s*source|\d+\s*hour|\d+\s*day)',
        chunk, re.IGNORECASE
    )
    if not headlines:
        # Fallback: grab lines that look like headlines
        lines = [ln.strip() for ln in chunk.split('\n')
                 if ln.strip() and 20 < len(ln.strip()) < 150]
        headlines = lines[:max_items]
    items = [h.strip() for h in headlines[:max_items]]
    if items:
        return "Breaking news: " + ". ".join(items)
    return ""
