# handlers/weather_handlers.py — Weather handler
import concurrent.futures
import threading
import httpx

from friday.voice.tts.speaker import speak
from friday.browser import controller as web
from friday.agent.context import update_context
from friday.core.log import log
import re


def handle_weather(text):
    """Get weather info via wttr.in."""
    match = re.search(r"(?:weather|temperature|forecast)\s+(?:in|at|for)\s+(.+)", text)
    city = match.group(1).strip() if match else ""

    try:
        base = f"https://wttr.in/{city}" if city else "https://wttr.in"
        url_simple = f"{base}?format=3"
        url_detail = f"{base}?format=%C+%t+%h+humidity+%w+wind"

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(httpx.get, url_simple, timeout=5, follow_redirects=True)
            f2 = pool.submit(httpx.get, url_detail, timeout=5, follow_redirects=True)
            resp1 = f1.result()
            resp1.raise_for_status()
            weather_text = resp1.text.strip()
            detail = f2.result().text.strip()

        # Open browser in parallel with speech
        browser_url = f"https://wttr.in/{city}" if city else "https://wttr.in/"
        def _open_weather_browser():
            try:
                web.open_url(browser_url)
            except Exception as e:
                log.error(f"Browser weather error: {e}")
        bt = threading.Thread(target=_open_weather_browser, daemon=True)
        bt.start()

        speak(f"Here's the weather, boss. {weather_text}. {detail}.")
        bt.join(timeout=10)

        update_context("weather", city or "current location", browser_url)
        return True
    except Exception as e:
        log.error(f"Weather error: {e}")
        speak("Couldn't get the weather right now, boss. Service might be down.")
        return True
