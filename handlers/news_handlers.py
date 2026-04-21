# handlers/news_handlers.py — News handler
import concurrent.futures
import feedparser

from speaker import speak
from personality import get_browser_opening
import browser as web
from context import update_context
from config_loader import get as cfg
from logger import log


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
        speak(get_browser_opening())

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
            return feedparser.parse(url)

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
