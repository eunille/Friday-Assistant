# router.py — Command routing with 3 core verbs: Check, Tell me, Compare
"""Simple dispatcher for voice commands.

Routing strategy:
  1. Keyword matching (fast path) — 3 verbs + system commands
  2. LLM intent classification (smart fallback)
  3. LLM conversational chat
"""
import re

from speaker import speak
from personality import get_browser_opening, get_unknown_command, get_confirmation
from brain import chat as llm_chat, is_available as llm_available, classify as llm_classify
import browser as web
import app_launcher
from context import update_context, get_context_summary
from logger import log

# Handler imports
from handlers.web_handlers import (
    handle_open, handle_search, handle_browser_action, handle_knowledge,
)
from handlers.finance_handlers import (
    handle_stock, handle_crypto, get_crypto_keywords,
)
from handlers.news_handlers import handle_news, handle_tech_news, handle_tech_followup
from handlers.system_handlers import (
    handle_volume, handle_screenshot, handle_time,
    handle_timer, handle_system_info, handle_app_launch,
)
from handlers.weather_handlers import handle_weather
from handlers.world_handlers import handle_world_monitor, handle_news_followup
from handlers.compare_handlers import handle_compare


def _has_word(text, *words):
    """Check if any of the given words/phrases appear in text."""
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
    """Route transcribed text to the correct handler."""
    if not text or len(text.strip()) < 2:
        return

    text = text.lower().strip()

    # Quick exit
    if _has_word(text, "thanks", "thank you", "never mind", "nevermind",
                 "that's all", "forget it", "goodbye", "bye"):
        speak("Anytime, boss.")
        return

    # =====================================================================
    # VERB 1: "COMPARE" — side-by-side comparison
    # =====================================================================
    if _has_word(text, "compare", "versus", "vs", "difference between",
                 "which is better"):
        if handle_compare(text):
            return

    # =====================================================================
    # CRYPTO — checked BEFORE knowledge so "what is bitcoin" routes here
    # =====================================================================
    crypto_kws = get_crypto_keywords()
    if any(_has_word(text, kw) for kw in crypto_kws):
        if handle_crypto(text):
            return

    # =====================================================================
    # VERB 2: "TELL ME" — definitions, explanations, knowledge
    # =====================================================================
    if text.startswith("tell me") or _has_word(
            text, "what is", "what are", "who is", "who are",
            "how does", "how do", "why is", "why are",
            "where is", "when was", "when did",
            "meaning of", "definition of", "explain"):
        if handle_knowledge(text):
            return

    # =====================================================================
    # VERB 3: "CHECK" — look up current data
    # =====================================================================

    # Check news → World Monitor
    if _has_word(text, "check news", "check the news", "world monitor",
                 "world news", "global news", "latest news",
                 "what's happening in the world", "world situation",
                 "global situation", "world events"):
        if handle_world_monitor(text):
            return

    # Tech news → daily.dev (BEFORE general news so "tech news" doesn't fall through)
    if _has_word(text, "tech news", "latest tech", "technology news",
                 "what's new in tech", "what's happening in tech",
                 "trending in tech", "developer news", "daily dev",
                 "daily.dev", "tech headlines", "latest in tech"):
        if handle_tech_news(text):
            return

    # Check prices (stocks, commodities, futures — LLM resolves ticker)
    if _has_word(text, "stock", "price", "share", "ticker",
                 "how much", "worth", "trading",
                 "oil", "gold", "silver", "copper", "gas"):
        if handle_stock(text):
            return

    # Check weather
    if _has_word(text, "weather", "temperature", "forecast",
                 "rain", "sunny", "hot outside", "cold outside"):
        if handle_weather(text):
            return

    # General news (non-world)
    if _has_word(text, "news", "headlines", "what's happening"):
        if handle_news(text):
            return

    # "Check [anything else]" → Google search + speak
    if text.startswith("check "):
        query = text[6:].strip()
        if query and len(query) > 2:
            if handle_knowledge(query):
                return

    # =====================================================================
    # SYSTEM COMMANDS — volume, time, timer, screenshot, apps, browser
    # =====================================================================
    if _has_word(text, "volume", "louder", "quieter", "mute", "unmute"):
        if handle_volume(text):
            return

    if _has_word(text, "screenshot", "screen shot", "capture screen"):
        if handle_screenshot(text):
            return

    if any(phrase in text for phrase in [
            "what time", "what's the time", "tell me the time"]) \
            or text in ("time", "clock"):
        if handle_time(text):
            return

    if _has_word(text, "timer", "alarm", "countdown",
                 "time left", "time remaining"):
        if handle_timer(text):
            return

    if _has_word(text, "cpu", "ram", "memory usage", "battery",
                 "system info", "system status"):
        if handle_system_info(text):
            return

    if _has_word(text, "search", "google", "look up", "look for",
                 "find me", "find out"):
        if handle_search(text):
            return

    if _has_word(text, "click", "go back", "scroll", "read this",
                 "read the page", "summarize this"):
        if handle_browser_action(text):
            return

    if _has_word(text, "launch", "start", "run"):
        if handle_app_launch(text):
            return

    if _has_word(text, "open", "go to", "navigate", "browser", "brave"):
        if handle_open(text):
            return

    # =====================================================================
    # CONTEXT-AWARE FOLLOW-UP — if last action was news, try follow-up
    # =====================================================================
    from context import get_context_summary
    ctx = get_context_summary()
    if "world_monitor" in ctx:
        if handle_news_followup(text):
            return
    if "tech_news" in ctx:
        if handle_tech_followup(text):
            return

    # =====================================================================
    # LLM FALLBACK — classify intent, then conversation
    # =====================================================================
    if llm_available():
        intent, entity = _classify_intent(text)

        if intent == "check":
            # LLM thinks user wants to look something up
            if handle_knowledge(entity or text):
                return

        if intent == "compare":
            if handle_compare(entity or text):
                return

        if intent == "stock":
            if handle_stock(text):
                return

        if intent == "crypto":
            if handle_crypto(text):
                return

        if intent == "commodity":
            if handle_stock(text):
                return

        if intent == "news":
            if handle_world_monitor(text):
                return

        if intent == "tech_news":
            if handle_tech_news(text):
                return

        if intent == "weather":
            handle_weather(text)
            return

        if intent == "open":
            if handle_open(text):
                return

        if intent == "search":
            query = entity or text
            speak(get_browser_opening())
            try:
                web.search_site(None, query)
            except Exception as e:
                log.error(f"Browser search error: {e}")
            update_context("search", query)
            return

        if intent == "time":
            handle_time(text)
            return

        if intent == "volume":
            handle_volume(text)
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

        if intent == "knowledge":
            handle_knowledge(entity or text)
            return

        # Tier 3: LLM conversation
        response = llm_chat(text)
        if response:
            speak(response)
            return

    speak(get_unknown_command(text))


def _classify_intent(text):
    """Ask LLM to classify user intent."""
    ctx_summary = get_context_summary()
    system_prompt = (
        "Classify this voice command. Reply ONLY: CATEGORY|ENTITY\n"
        "If no entity: CATEGORY|none\n"
        "Categories: check,compare,knowledge,stock,crypto,commodity,news,tech_news,"
        "search,open,time,volume,weather,timer,system,app,chat\n"
        f"Context: {ctx_summary}\n"
        "Examples:\n"
        "- check tesla price -> stock|tesla\n"
        "- compare bitcoin and ethereum -> compare|bitcoin and ethereum\n"
        "- tell me about quantum computing -> knowledge|quantum computing\n"
        "- what's happening in the world -> news|none\n"
        "- what's the latest tech news -> tech_news|none\n"
        "- what's trending in tech -> tech_news|none\n"
        "- open youtube -> open|youtube\n"
        "- how is bitcoin -> crypto|bitcoin\n"
        "- how are you -> chat|none\n/no_think"
    )
    try:
        result = llm_classify(text, system_prompt)
        if result:
            result = result.strip().lower().rstrip(".")
            valid = ("check", "compare", "knowledge", "stock", "crypto",
                     "commodity", "news", "tech_news", "search", "open", "time",
                     "volume", "weather", "timer", "system", "app")
            if "|" in result:
                parts = result.split("|", 1)
                category = parts[0].strip()
                entity = parts[1].strip()
                if entity == "none":
                    entity = None
                if category in valid:
                    return category, entity
            result = result.split()[0] if result else "chat"
            if result in valid:
                return result, None
    except Exception:
        pass
    return "chat", None
