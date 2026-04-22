# handlers/news_handlers.py — News handler
import concurrent.futures
import socket
import threading
import feedparser

from speaker import speak
from personality import get_processing_start, get_thinking_pause, get_summary_done
from brain import summarize as llm_summarize, is_available as llm_available
import browser as web
from context import update_context
from config_loader import get as cfg
from logger import log

_FEED_TIMEOUT = 8  # seconds per RSS fetch

# ── Tech news RSS feeds (daily.dev has no public RSS; use Hacker News + dev.to)
_TECH_FEEDS = [
    "https://hnrss.org/frontpage",   # Hacker News front page
    "https://dev.to/feed",           # dev.to community
]
_DAILY_DEV_URL = "https://app.daily.dev"


_news_feeds = None
_news_topics = None


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


def handle_news(text):
    """Open news in browser first, then speak top headlines."""
    topic_feed = None
    topic_name = None
    for topic, feed_url in _get_news_topics().items():
        if topic in text:
            topic_feed = feed_url
            topic_name = topic
            break

    if topic_name:
        speak(f"Got it. Pulling up {topic_name} news for you.")
    else:
        speak(get_processing_start())

    try:
        if topic_name:
            web.open_url(f"https://news.google.com/topics/{topic_name}")
        else:
            web.open_url("https://news.google.com")
    except Exception as e:
        log.error(f"Browser error opening news: {e}")

    try:
        feeds = [topic_feed] if topic_feed else _get_news_feeds()
        headlines = []

        def _parse_feed(url):
            old = socket.getdefaulttimeout()
            try:
                socket.setdefaulttimeout(_FEED_TIMEOUT)
                return feedparser.parse(url)
            finally:
                socket.setdefaulttimeout(old)

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(feeds)) as pool:
            results = list(pool.map(_parse_feed, feeds))

        for feed in results:
            for entry in feed.entries[:5]:
                headlines.append(entry.title)

        if headlines:
            count = min(len(headlines), 5)
            prefix = f"top {topic_name}" if topic_name else "top"
            numbered = ". ".join(f"{i}, {h}" for i, h in enumerate(headlines[:5], 1))
            speak(f"Here are the {prefix} {count} headlines. {numbered}.")
        else:
            speak("I've got the news page up, boss. Couldn't pull the RSS headlines though.")
        update_context("news", topic_name)
        return True
    except Exception as e:
        speak("News page is on screen, boss. RSS feeds seem down though.")
        log.error(f"News error: {e}")
        update_context("news", topic_name)
        return True


# ── Tech news (daily.dev visual + Hacker News / dev.to headlines) ────────────

_last_tech_headlines = None   # cache for follow-up queries

def _fetch_tech_headlines(max_items=8):
    """Pull top stories from Hacker News and dev.to RSS."""
    headlines = []

    def _parse(url):
        old = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(_FEED_TIMEOUT)
            return feedparser.parse(url)
        except Exception:
            return None
        finally:
            socket.setdefaulttimeout(old)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(_TECH_FEEDS)) as pool:
        results = list(pool.map(_parse, _TECH_FEEDS))

    for feed in results:
        if feed is None:
            continue
        for entry in feed.entries[:5]:
            title = entry.get("title", "").strip()
            if title:
                headlines.append(title)

    # Deduplicate by 40-char prefix
    seen, unique = set(), []
    for h in headlines:
        key = h[:40].lower()
        if key not in seen:
            seen.add(key)
            unique.append(h)
    return unique[:max_items]


def handle_tech_news(text):
    """Open daily.dev in browser, fetch tech headlines, LLM-summarize, speak."""
    global _last_tech_headlines
    speak(get_thinking_pause())

    # Open daily.dev and fetch headlines in parallel
    browser_err = []

    def _open_browser():
        try:
            web.open_url(_DAILY_DEV_URL)
        except Exception as e:
            browser_err.append(e)
            log.error(f"Browser error opening daily.dev: {e}")

    t = threading.Thread(target=_open_browser, daemon=True)
    t.start()

    headlines = _fetch_tech_headlines(max_items=8)
    t.join(timeout=12)

    if not headlines:
        speak("Daily.dev is up on screen. Couldn't pull headlines from the feeds right now.")
        update_context("tech_news", "tech")
        return True

    _last_tech_headlines = "\n".join(headlines)

    summary = llm_summarize(
        _last_tech_headlines,
        instruction=(
            "You are Friday, an Iron Man-style AI assistant. "
            "Summarize these top tech headlines into 2-3 natural spoken sentences. "
            "Be concise and conversational. No bullet points. No 'boss'."
        ),
        max_predict=120,
    ) if llm_available() else None

    if summary:
        speak(summary.strip())
    else:
        # Fallback: read top 5 headlines directly
        items = ". ".join(
            f"{i}. {h}" for i, h in enumerate(headlines[:5], 1)
        )
        speak(f"Here are the top tech stories. {items}.")

    speak(get_summary_done())
    update_context("tech_news", "tech")
    return True


def handle_tech_followup(text):
    """Answer a follow-up question using the cached tech headlines."""
    if not _last_tech_headlines:
        return False

    # Try LLM answer first (don't pre-check llm_available — it may have loaded by now)
    answer = llm_summarize(
        _last_tech_headlines,
        instruction=(
            f"The user just heard a tech news summary and now asks: \"{text}\". "
            "Answer their question using only the headlines above. "
            "Be concise — 1-2 sentences max. Conversational tone. No bullet points."
        ),
        max_predict=120,
    )
    if answer:
        speak(answer.strip())
        return True

    # LLM unavailable — keyword-search the cached headlines as a fallback
    words = [w for w in text.lower().split() if len(w) > 3]
    if words:
        matched = [
            h for h in _last_tech_headlines.splitlines()
            if any(w in h.lower() for w in words)
        ]
        if matched:
            speak(f"From the headlines — {matched[0]}")
            return True

    return False
