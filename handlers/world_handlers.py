# handlers/world_handlers.py — World news: RSS feeds + LLM summary
import threading
import feedparser

from speaker import speak
from brain import chat as llm_chat, is_available as llm_available, summarize as llm_summarize
from personality import get_summary_done, get_thinking_pause
import browser as web
from context import update_context
from logger import log

# RSS feeds for world news
_WORLD_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://news.google.com/rss?topic=WORLD&hl=en-US&gl=US&ceid=US:en",
]

# Store last overview for follow-up queries
_last_overview = None
_last_headlines = None


def _fetch_headlines(max_items=8):
    """Fetch top headlines from RSS feeds."""
    headlines = []
    for url in _WORLD_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title = entry.get("title", "").strip()
                desc = entry.get("summary", entry.get("description", "")).strip()
                if title:
                    headlines.append(f"{title}. {desc}" if desc else title)
        except Exception as e:
            log.error(f"RSS feed error ({url}): {e}")
    # Deduplicate by title prefix
    seen = set()
    unique = []
    for h in headlines:
        key = h[:40].lower()
        if key not in seen:
            seen.add(key)
            unique.append(h)
    return unique[:max_items]


def handle_world_monitor(text):
    """Fetch world news via RSS, summarize with LLM, open World Monitor."""
    global _last_overview, _last_headlines
    speak("Okay boss, just a second.")

    # Fetch RSS and open browser in parallel
    headlines_result = []

    def _fetch():
        headlines_result.extend(_fetch_headlines())

    def _open_browser():
        try:
            web.open_url("https://www.worldmonitor.app/")
        except Exception as e:
            log.error(f"Browser error opening World Monitor: {e}")

    t_fetch = threading.Thread(target=_fetch, daemon=True)
    t_browser = threading.Thread(target=_open_browser, daemon=True)
    t_fetch.start()
    t_browser.start()
    t_fetch.join(timeout=10)
    t_browser.join(timeout=15)

    if not headlines_result:
        speak("I couldn't pull any news right now, boss.")
        _last_overview = None
        _last_headlines = None
        update_context("world_monitor", "overview")
        return True

    _last_headlines = "\n".join(headlines_result)
    log.info(f"WM: fetched {len(headlines_result)} headlines")

    # Summarize with LLM
    if llm_available():
        overview = llm_summarize(
            _last_headlines,
            "Summarize these news headlines into a brief spoken overview. "
            "2-3 sentences covering the biggest stories. Be concise and factual.",
            max_predict=150,
        )
    else:
        # No LLM — just read top 3 headlines
        top3 = headlines_result[:3]
        overview = ". ".join(h.split(".")[0] for h in top3)

    if overview:
        speak(f"{get_thinking_pause()} According to the latest reports, {overview}")
        _last_overview = overview
    else:
        # LLM failed — fall back to reading headlines
        top3 = ". ".join(h.split(".")[0] for h in headlines_result[:3])
        speak(f"{get_thinking_pause()} Here are the top stories. {top3}.")
        _last_overview = top3

    speak(get_summary_done())
    update_context("world_monitor", "overview")
    return True


def handle_news_followup(text):
    """Handle follow-up questions about the last news overview.
    Uses LLM to answer based on cached headlines."""
    if not _last_overview:
        return False

    if not llm_available():
        return False

    context = _last_headlines or _last_overview

    prompt = (
        f"Based on this news overview, answer the user's question briefly "
        f"(2-3 sentences max).\n\n"
        f"News context:\n{context}\n\n"
        f"User question: {text}"
    )
    response = llm_chat(prompt)
    if response:
        speak(response)
        return True
    return False
