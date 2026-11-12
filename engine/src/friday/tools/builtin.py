"""The tools the agent starts with.

These wrap what Friday can already do, but return data instead of speaking.
The keyword router still handles the commands it recognises; the agent gets
everything else and reaches for these.
"""
from datetime import datetime

from friday.tools.registry import Registry


def _str_param(name, description):
    return {"type": "object",
            "properties": {name: {"type": "string", "description": description}},
            "required": [name]}


def _news_search(query, limit=6):
    """Headlines from Google News' RSS search. Used when the web search is
    blocked or empty; good for anything recent."""
    from urllib.parse import quote_plus

    import feedparser
    import requests
    try:
        response = requests.get(f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en",
                                timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        entries = feedparser.parse(response.text).entries[:limit]
    except Exception:
        return []
    return [{"title": e.get("title", ""), "published": e.get("published", ""),
             "source": (e.get("source") or {}).get("title", "")} for e in entries]


def build_registry() -> Registry:
    reg = Registry()

    @reg.tool("web_search", "Search the web. Returns titles, snippets and URLs. "
              "Use for anything current or factual you are not sure of.",
              _str_param("query", "What to search for"))
    def web_search(query):
        from friday.browser import controller
        return controller.search_and_extract(query) or _news_search(query) or "No results."

    @reg.tool("read_page", "Open a web page in the background and return its text.",
              _str_param("url", "Full URL of the page to read"))
    def read_page(url):
        from friday.browser import controller
        return controller.visit_and_extract(url) or "The page had no readable text."

    @reg.tool("open_website", "Show a web page to the user in the browser.",
              _str_param("url", "Full URL to open"))
    def open_website(url):
        from friday.browser import controller
        return f"Opened: {controller.open_url(url)}"

    @reg.tool("read_current_page", "Return the text of the page currently shown in the browser.")
    def read_current_page():
        from friday.browser import controller
        return controller.get_page_text() or "Nothing readable on the current page."

    @reg.tool("launch_app", "Start a program installed on this computer by name.",
              _str_param("name", "Program name, e.g. 'spotify' or 'vs code'"))
    def launch_app(name):
        from friday.tools import app_launcher
        launched = app_launcher.launch(name)
        return f"Started {launched}." if launched else f"No installed program matches '{name}'."

    @reg.tool("get_time", "Current local date and time.")
    def get_time():
        return datetime.now().strftime("%A %d %B %Y, %I:%M %p")

    @reg.tool("system_status", "CPU, memory and battery status of this computer.")
    def system_status():
        import psutil
        status = {"cpu_percent": psutil.cpu_percent(interval=0.3),
                  "memory_percent": psutil.virtual_memory().percent}
        battery = psutil.sensors_battery()
        if battery:
            status["battery_percent"] = battery.percent
            status["plugged_in"] = battery.power_plugged
        return status

    return reg
