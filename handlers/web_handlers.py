# handlers/web_handlers.py — Browser, search, and knowledge handlers
import re
import threading

from speaker import speak
from personality import get_browser_opening, get_data_ready
from brain import chat as llm_chat, is_available as llm_available
import browser as web
from context import update_context
from logger import log


def _get_site_map():
    from config_loader import get as cfg
    return cfg("sites") or {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "github": "https://github.com",
        "reddit": "https://www.reddit.com",
        "twitter": "https://twitter.com",
        "gmail": "https://mail.google.com",
        "netflix": "https://www.netflix.com",
        "spotify": "https://open.spotify.com",
    }


def handle_open(text):
    """Open a website using Playwright browser."""
    import app_launcher

    if re.search(r"\b(?:browser|brave)\b", text):
        speak("Opening the browser, boss.")
        try:
            web.open_url("about:blank")
        except Exception as e:
            log.error(f"Browser error: {e}")
            speak("Couldn't launch the browser.")
        update_context("open", "browser")
        return True

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
        app_name = app_launcher.launch(target)
        if app_name:
            speak(f"Launching {app_name}, boss.")
            update_context("app", app_name)
            return True
        speak(get_browser_opening())
        try:
            web.search_site(None, target)
        except Exception as e:
            log.error(f"Browser search error: {e}")
            speak(f"Couldn't search for {target}.")
        update_context("search", target)
        return True
    return False


def handle_search(text):
    """Search the web via Playwright browser."""
    match = re.search(r"(?:search|google|look up)\s+(?:for\s+)?(.+)", text)
    if match:
        query = match.group(1).strip()
        speak(get_browser_opening())
        try:
            web.search_site(None, query)
        except Exception as e:
            log.error(f"Browser search error: {e}")
            speak(f"Couldn't search for {query}.")
        update_context("search", query)
        return True
    return False


def handle_browser_action(text):
    """Handle browser interaction commands: click, go back, scroll, read page."""
    if any(phrase in text for phrase in ["go back", "back", "previous page"]):
        try:
            title = web.go_back()
            speak(f"Went back to {title}." if title else "Went back.")
            return True
        except Exception:
            speak("Can't go back right now.")
            return True

    if any(phrase in text for phrase in ["scroll down", "page down"]):
        web.scroll_down()
        speak("Scrolled down.")
        return True
    if any(phrase in text for phrase in ["scroll up", "page up"]):
        web.scroll_up()
        speak("Scrolled up.")
        return True

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

    if any(phrase in text for phrase in [
            "read this page", "read the page",
            "what's on this page", "summarize this page"]):
        try:
            page_text = web.get_page_text(max_chars=2000)
            if page_text and llm_available():
                summary = llm_chat(
                    f"Summarize this web page content in 2-3 sentences "
                    f"for spoken delivery:\n\n{page_text}\n/no_think"
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


def handle_knowledge(text):
    """Answer questions using multi-source web research pipeline.
    Flow: echo query → search silently → open browser → speak analysis."""
    # Extract the core query for spoken echo
    import re
    query = text
    for prefix in ["tell me about", "tell me", "what is", "what are",
                    "who is", "who are", "explain", "check"]:
        if query.startswith(prefix):
            query = query[len(prefix):].strip()
            break
    echo = query[:60] if len(query) > 60 else query
    speak(f"Looking into {echo}.")

    try:
        results = web.search_and_extract(text, max_results=5)
    except Exception as e:
        log.error(f"Web search error: {e}")
        speak("Couldn't search the web right now, boss.")
        return True

    if not results:
        speak("Couldn't find anything relevant, boss.")
        return True

    snippets = []
    best_url = ""
    for r in results:
        if r.get("snippet"):
            snippets.append(f"• {r['title']}: {r['snippet']}")
        if not best_url and r.get("url") and r["url"].startswith("http"):
            best_url = r["url"]

    # Start page visit in background while building snippet context
    page_holder = {}
    source_title = results[0].get("title", "") if results else ""
    visit_thread = None
    if best_url:
        def _visit():
            try:
                page_holder["content"] = web.visit_and_extract(best_url, max_chars=3000)
            except Exception as e:
                log.error(f"Page visit error: {e}")
                page_holder["content"] = ""
        visit_thread = threading.Thread(target=_visit, daemon=True)
        visit_thread.start()

    # Build snippet context while page visit runs in parallel
    context_parts = []
    if snippets:
        context_parts.append("Search results:\n" + "\n".join(snippets[:3]))

    # Now wait for page visit to complete
    if visit_thread:
        visit_thread.join(timeout=10)
    page_content = page_holder.get("content", "")

    if page_content and len(page_content) > 100:
        context_parts.insert(0, f"Source ({source_title}):\n{page_content[:2000]}")

    context = "\n\n".join(context_parts)

    if not context:
        speak("I've pulled up the results on screen, boss. Take a look.")
        update_context("knowledge", text)
        return True

    if llm_available():
        prompt = (
            f"Answer briefly as Friday (AI assistant): \"{text}\"\n\n"
            f"{context[:1200]}\n\n"
            f"3-4 sentences. Key facts + your insight. Speak naturally."
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
