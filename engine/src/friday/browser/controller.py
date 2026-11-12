# browser.py — Playwright browser automation for Friday
import threading
from urllib.parse import quote_plus
from friday.core.config import get as cfg
from friday.core.log import log


_BROWSER = None
_PAGE = None        # Extraction/internal page (stays on about:blank)
_DISPLAY_PAGE = None  # Reusable visible tab for all open_url calls
_CONTEXT = None
_PLAYWRIGHT = None
_LOCK = threading.Lock()
_OP_LOCK = threading.Lock()  # Serializes page operations against stale threads


def _page_timeout():
    """Page load timeout from config (ms)."""
    return cfg("browser", "page_load_timeout") or 15000


def _action_timeout():
    """Action timeout from config (ms)."""
    return cfg("browser", "action_timeout") or 10000


def _render_wait():
    """JS render wait from config (ms)."""
    return cfg("browser", "js_render_wait") or 2000


def _max_page_chars():
    """Max chars to extract from page text."""
    return cfg("browser", "max_page_chars") or 2000


def _max_search_results():
    """Max search results to extract."""
    return cfg("browser", "max_search_results") or 5


def _max_visit_chars():
    """Max chars from visited page."""
    return cfg("browser", "max_visit_chars") or 3000


def _default_search_url(query):
    """Build search URL from config; defaults to DuckDuckGo to avoid CAPTCHA."""
    template = cfg("browser", "search_url") or "https://duckduckgo.com/?q={query}"
    encoded_query = quote_plus(query)
    return template.replace("{query}", encoded_query)


def _is_robot_check_page(page):
    """Detect anti-bot challenge pages that block automated browsing."""
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""

    blocked_markers = (
        "google.com/sorry",
        "captcha",
        "recaptcha",
        "unusual traffic",
    )
    if any(marker in url for marker in blocked_markers):
        return True

    try:
        title = (page.title() or "").lower()
        if any(marker in title for marker in blocked_markers):
            return True
    except Exception:
        pass

    return False


def _sanitize_url(url):
    """Validate URL is safe to open (http/https only)."""
    from urllib.parse import urlparse

    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsafe URL scheme: {parsed.scheme}")
    return url


def _reset_display_page():
    """Close the display page if it's dead."""
    global _DISPLAY_PAGE
    try:
        if _DISPLAY_PAGE is not None:
            _DISPLAY_PAGE.close()
    except Exception:
        pass
    _DISPLAY_PAGE = None


def _reset_browser():
    """Reset all browser state (called on crash recovery)."""
    global _BROWSER, _PAGE, _CONTEXT, _PLAYWRIGHT, _DISPLAY_PAGE
    _BROWSER = None
    _PAGE = None
    _DISPLAY_PAGE = None
    _CONTEXT = None
    if _PLAYWRIGHT:
        try:
            _PLAYWRIGHT.stop()
        except Exception:
            pass
    _PLAYWRIGHT = None


def _resolve_browser_executable():
    """Resolve the browser executable path for this platform.
    Uses the configured path if it exists, otherwise probes common install
    locations (Brave/Chrome on Windows and Linux). Returns None to let
    Playwright use its own bundled Chromium."""
    import os
    import platform

    configured = cfg("browser", "executable")
    if configured and configured != "auto" and os.path.isfile(configured):
        return configured

    if platform.system() == "Windows":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            rf"{program_files}\BraveSoftware\Brave-Browser\Application\brave.exe",
            rf"{program_files_x86}\BraveSoftware\Brave-Browser\Application\brave.exe",
            rf"{local_appdata}\BraveSoftware\Brave-Browser\Application\brave.exe",
            rf"{program_files}\Google\Chrome\Application\chrome.exe",
            rf"{local_appdata}\Google\Chrome\Application\chrome.exe",
        ]
    else:
        candidates = [
            "/usr/bin/brave-browser",
            "/usr/bin/brave",
            "/snap/bin/brave",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]

    for path in candidates:
        if os.path.isfile(path):
            log.info(f"Using browser: {path}")
            return path

    log.warning("No system browser found — using Playwright's Chromium "
                "(run: playwright install chromium)")
    return None


def _tile_browser_left():
    """Move the active Playwright browser window to the left half of the primary screen.
    Uses KDE KWin's qdbus interface. Falls back to xdotool if available.
    Linux-only — no-op on Windows/macOS.
    Called after the browser first opens (runs in a background thread)."""
    import platform as _platform
    if _platform.system() != "Linux":
        return

    import time as _time
    import subprocess as _sp

    _time.sleep(1.2)  # Let the window appear and settle

    # Screen geometry — primary monitor
    sw, sh = 1920, 1080
    try:
        xr = _sp.check_output(
            "xrandr --current 2>/dev/null | grep ' connected primary'",
            shell=True,
        ).decode()
        import re as _re
        m = _re.search(r"(\d+)x(\d+)\+0\+0", xr)
        if m:
            sw, sh = int(m.group(1)), int(m.group(2))
    except Exception:
        pass

    half_w = sw // 2

    # Try xdotool (most reliable, available if installed)
    if _sp.run(["which", "xdotool"], capture_output=True).returncode == 0:
        try:
            # Find Brave/Chromium window
            win_ids = _sp.check_output(
                "xdotool search --class 'brave-browser' 2>/dev/null || "
                "xdotool search --class 'chromium' 2>/dev/null",
                shell=True,
            ).decode().strip().split()
            for wid in win_ids[:1]:
                _sp.run(f"xdotool windowmove {wid} 0 0", shell=True, capture_output=True)
                _sp.run(f"xdotool windowsize {wid} {half_w} {sh}", shell=True, capture_output=True)
            return
        except Exception:
            pass

    # KDE KWin fallback: send the QuickTileLeft action via dbus
    try:
        _sp.run(
            ["qdbus", "org.kde.KWin", "/KWin", "slotWindowQuickTileLeft"],
            capture_output=True, timeout=3,
        )
    except Exception:
        pass


def _ensure_browser():
    """Launch browser if not already running. Returns (browser, page).
    Auto-recovers if browser crashed or connection was lost."""
    global _BROWSER, _PAGE, _CONTEXT, _PLAYWRIGHT

    with _LOCK:
        # Check if existing browser is still alive
        if _BROWSER is not None and _PAGE is not None:
            try:
                # Quick health check — will throw if browser is dead
                _PAGE.evaluate("1")
                return _BROWSER, _PAGE
            except Exception:
                log.warning("Browser connection lost. Relaunching...")
                _reset_browser()

        from playwright.sync_api import sync_playwright

        _PLAYWRIGHT = sync_playwright().start()
        browser_path = _resolve_browser_executable()

        # --start-maximized makes the OS window maximized on launch.
        # no_viewport=True lets the browser use the natural OS window size.
        _BROWSER = _PLAYWRIGHT.chromium.launch(
            headless=False,
            executable_path=browser_path,
            args=["--start-maximized"],
        )
        _CONTEXT = _BROWSER.new_context(no_viewport=True)
        _PAGE = _CONTEXT.new_page()

        # Optionally tile browser to left half in background
        if cfg("browser", "tile_left"):
            import threading as _t
            _t.Thread(target=_tile_browser_left, daemon=True).start()

        return _BROWSER, _PAGE


def _get_display_page():
    """Return the reusable display tab, creating it if needed."""
    global _DISPLAY_PAGE
    _, _ = _ensure_browser()  # guarantees _CONTEXT is alive
    if _DISPLAY_PAGE is not None:
        try:
            _DISPLAY_PAGE.evaluate("1")
            return _DISPLAY_PAGE
        except Exception:
            log.warning("Display tab dead, opening a new one")
            _reset_display_page()
    _DISPLAY_PAGE = _CONTEXT.new_page()
    return _DISPLAY_PAGE


def open_url(url):
    """Open a URL in the reusable display tab. Never opens a new browser window."""
    url = _sanitize_url(url)
    with _OP_LOCK:
        page = _get_display_page()
        try:
            current = (page.url or "").split("?")[0].rstrip("/")
            target = url.split("?")[0].rstrip("/")
            if current and current == target:
                log.debug(f"Display tab already on {target}, skipping navigation")
                return page.title()
        except Exception:
            pass
        page.goto(url, wait_until="domcontentloaded", timeout=_page_timeout())
        return page.title()


def search_site(site_url, query):
    """Navigate to a site and type a search query.
    Works for YouTube, Google, etc. — finds the search input and submits.
    """
    site_url = _sanitize_url(site_url) if site_url else _default_search_url(query)
    _, page = _ensure_browser()
    with _OP_LOCK:
        page.goto(site_url, wait_until="domcontentloaded", timeout=_page_timeout())

        # If anti-bot page appears, fall back to configured search engine.
        if _is_robot_check_page(page):
            fallback_url = _default_search_url(query)
            log.warning(f"Robot-check detected at {page.url}; falling back to {fallback_url}")
            page.goto(fallback_url, wait_until="domcontentloaded", timeout=_page_timeout())
            return page.title()

        # Common search input selectors
        selectors = [
            'input[name="search_query"]',  # YouTube
            'input[name="q"]',             # Google
            'textarea[name="q"]',          # Google (new)
            'input[type="search"]',        # Generic
            'input[name="search"]',        # Generic
            'input[placeholder*="earch"]', # Placeholder contains "search"
        ]

        for selector in selectors:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    el.click()
                    el.fill(query)
                    page.keyboard.press("Enter")
                    page.wait_for_load_state("domcontentloaded", timeout=_action_timeout())

                    if _is_robot_check_page(page):
                        fallback_url = _default_search_url(query)
                        log.warning(
                            f"Robot-check detected after submit at {page.url}; "
                            f"falling back to {fallback_url}"
                        )
                        page.goto(fallback_url, wait_until="domcontentloaded", timeout=_page_timeout())
                    return page.title()
            except Exception:
                continue

        return None


def click_element(description):
    """Click an element by visible text or aria label."""
    _, page = _ensure_browser()
    with _OP_LOCK:
        # Try visible text match first
        try:
            el = page.get_by_text(description, exact=False).first
            if el and el.is_visible():
                el.click()
                page.wait_for_load_state("domcontentloaded", timeout=_action_timeout())
                return page.title()
        except Exception:
            pass

        # Try role-based
        try:
            el = page.get_by_role("link", name=description).first
            if el:
                el.click()
                page.wait_for_load_state("domcontentloaded", timeout=_action_timeout())
                return page.title()
        except Exception:
            pass

        return None


def type_text(text):
    """Type text into the currently focused element."""
    _, page = _ensure_browser()
    page.keyboard.type(text)
    return True


def go_back():
    """Go back one page."""
    _, page = _ensure_browser()
    with _OP_LOCK:
        page.go_back(wait_until="domcontentloaded", timeout=_action_timeout())
        return page.title()


def scroll_down():
    """Scroll down the page."""
    _, page = _ensure_browser()
    page.keyboard.press("PageDown")
    return True


def scroll_up():
    """Scroll up the page."""
    _, page = _ensure_browser()
    page.keyboard.press("PageUp")
    return True


def get_page_text(max_chars=None):
    if max_chars is None:
        max_chars = _max_page_chars()
    """Extract visible text content from the current page, preferring main content."""
    _, page = _ensure_browser()
    # Try semantic content containers first to skip nav/ads/sidebars
    for selector in ("main", "article", '[role="main"]', "#content", ".content", "body"):
        try:
            el = page.query_selector(selector)
            if el:
                text = el.inner_text()
                lines = [ln.strip() for ln in text.split("\n") if len(ln.strip()) > 15]
                cleaned = "\n".join(lines)
                if len(cleaned) > 200:
                    return cleaned[:max_chars]
        except Exception:
            continue
    return ""


def _ddg_search(query, max_results=5):
    """Fetch DuckDuckGo search results via plain HTTP — no browser required.
    Uses DDG's HTML endpoint so the visible browser stays clean.
    Returns list of dicts: [{"title": ..., "snippet": ..., "url": ...}]
    """
    from urllib.request import urlopen, Request as _Req
    from urllib.parse import quote_plus, unquote_plus, parse_qs, urlparse
    from html.parser import HTMLParser

    class _DDGParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.results = []
            self._state = None      # 'title' | 'snippet'
            self._current = {}
            self._buf = []

        def handle_starttag(self, tag, attrs):
            if tag != "a":
                return
            attrs_d = dict(attrs)
            cls = attrs_d.get("class", "")
            if "result__a" in cls:
                href = attrs_d.get("href", "")
                # DDG wraps URLs: /l/?uddg=ENCODED_URL&...
                if "uddg=" in href:
                    qs = parse_qs(urlparse(href).query)
                    real_url = qs.get("uddg", [href])[0]
                    real_url = unquote_plus(real_url)
                elif href.startswith("/y.js") or "ad_domain=" in href or "ad_provider=" in href:
                    # DDG ad redirect — skip
                    real_url = None
                else:
                    real_url = href
                if not real_url:
                    return
                self._current["url"] = real_url
                self._state = "title"
                self._buf = []
            elif "result__snippet" in cls:
                self._state = "snippet"
                self._buf = []

        def handle_endtag(self, tag):
            if tag != "a":
                return
            if self._state == "title":
                self._current["title"] = "".join(self._buf).strip()
                self._state = None
            elif self._state == "snippet":
                self._current["snippet"] = "".join(self._buf).strip()
                if self._current.get("title"):
                    self.results.append(dict(self._current))
                self._current = {}
                self._state = None

        def handle_data(self, data):
            if self._state in ("title", "snippet"):
                self._buf.append(data)

        def handle_entityref(self, name):
            if self._state in ("title", "snippet"):
                _ents = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}
                self._buf.append(_ents.get(name, ""))

        def handle_charref(self, name):
            if self._state in ("title", "snippet"):
                try:
                    ch = chr(int(name[1:], 16) if name.startswith("x") else int(name))
                    self._buf.append(ch)
                except ValueError:
                    pass

    encoded = quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    try:
        req = _Req(url, headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) "
                "Gecko/20100101 Firefox/120.0"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.5",
        })
        with urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        log.error(f"DDG search HTTP error: {e}")
        return []

    parser = _DDGParser()
    try:
        parser.feed(html)
    except Exception as e:
        log.error(f"DDG HTML parse error: {e}")

    return parser.results[:max_results]


def search_and_extract(query, max_results=None):
    """Search DuckDuckGo via HTTP — no browser opened, keeps visible window clean.
    Returns list of dicts: [{"title": ..., "snippet": ..., "url": ...}]
    """
    if max_results is None:
        max_results = _max_search_results()
    return _ddg_search(query, max_results=max_results)


def visit_and_extract(url=None, max_chars=None):
    if max_chars is None:
        max_chars = _max_visit_chars()
    """Visit a URL (or use current page) and extract clean text content.
    Returns the extracted text string."""
    _, page = _ensure_browser()
    with _OP_LOCK:
        if url:
            page.goto(url, wait_until="domcontentloaded", timeout=_page_timeout())
            try:
                page.wait_for_load_state("networkidle", timeout=2000)
            except Exception:
                pass
        return get_page_text(max_chars=max_chars)


def get_current_url():
    """Get the current page URL."""
    _, page = _ensure_browser()
    return page.url


def close_browser():
    """Close the browser and stop Playwright."""
    global _BROWSER, _PAGE, _CONTEXT, _PLAYWRIGHT
    with _LOCK:
        if _BROWSER:
            _BROWSER.close()
        if _PLAYWRIGHT:
            _PLAYWRIGHT.stop()
        _BROWSER = None
        _PAGE = None
        _CONTEXT = None
        _PLAYWRIGHT = None
