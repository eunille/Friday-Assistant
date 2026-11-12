"""Dispatcher for voice commands.

  1. Keyword matching (fast path): recognised commands run their handler directly.
  2. Everything else goes to the agent, which picks tools itself and replies.
"""
import re

from friday.voice.tts.speaker import speak
from friday.agent.personality import get_unknown_command
from friday.agent.context import get_context_summary
from friday.core.events import bus
from friday.core.log import log

# Handler imports
from friday.tools.web import (
    handle_open, handle_search, handle_browser_action, handle_knowledge,
)
from friday.tools.finance import (
    handle_stock, handle_crypto, get_crypto_keywords,
)
from friday.tools.news import handle_news, handle_tech_news, handle_tech_followup
from friday.tools.system import (
    handle_volume, handle_screenshot, handle_time,
    handle_timer, handle_system_info, handle_app_launch,
)
from friday.tools.weather import handle_weather
from friday.tools.world import handle_world_monitor, handle_news_followup
from friday.tools.compare import handle_compare


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
    ctx = get_context_summary()
    if "world_monitor" in ctx:
        if handle_news_followup(text):
            return
    if "tech_news" in ctx:
        if handle_tech_followup(text):
            return

    # =====================================================================
    # AGENT — everything the keyword list above didn't recognise
    # =====================================================================
    reply = _ask_agent(text)
    speak(reply or get_unknown_command(text))


_agent = None
_approval_channel = None  # set by the API so the app can answer too


def set_approval_channel(channel):
    """channel(question) -> answer text or bool. None restores voice-only."""
    global _approval_channel
    _approval_channel = channel


def _ask_user(question):
    return (_approval_channel or _voice_approval)(question)


def _on_agent_event(event):
    log.info(f"agent: {event}")
    bus.publish("agent", **{("step" if k == "type" else k): v for k, v in event.items()})


def _voice_approval(question):
    """Ask out loud and return what the user says."""
    from friday.voice.stt import listen
    speak(question)
    return listen()


def _get_agent():
    """Build the agent on first use (model source and tools come from settings)."""
    global _agent
    if _agent is None:
        from friday.agent.approvals import Approvals
        from friday.agent.loop import Agent
        from friday.core.config import get as cfg
        from friday.llm.factory import get_model_source
        from friday.tools.builtin import build_registry
        _agent = Agent(
            get_model_source(), build_registry(),
            approvals=Approvals(_ask_user),
            max_steps=int(cfg("agent", "max_steps") or 6),
            on_event=_on_agent_event,
        )
    return _agent


def _ask_agent(text):
    """Return the agent's spoken reply, or None if no model is set up."""
    try:
        from friday.llm.factory import get_model_source
        if not get_model_source().available():
            return None
        return _get_agent().run(text)
    except Exception as e:
        log.error(f"Agent error: {e}", exc_info=True)
        return None
