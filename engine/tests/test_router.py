"""The keyword router sends each utterance to the right handler.

These pin today's behaviour so the restructure (and later the agent) can't
silently change what a spoken command does.
"""
import pytest

from friday.agent import router

HANDLERS = [
    "handle_compare", "handle_crypto", "handle_knowledge", "handle_world_monitor",
    "handle_tech_news", "handle_stock", "handle_weather", "handle_news",
    "handle_volume", "handle_screenshot", "handle_time", "handle_timer",
    "handle_system_info", "handle_search", "handle_browser_action",
    "handle_app_launch", "handle_open",
]


@pytest.fixture
def calls(monkeypatch):
    """Replace every handler with a recorder; no audio, network or model."""
    seen = []

    def recorder(name):
        def handler(text):
            seen.append(name)
            return True
        return handler

    for name in HANDLERS:
        monkeypatch.setattr(router, name, recorder(name))
    monkeypatch.setattr(router, "speak", lambda text, **kw: seen.append(f"speak:{text}"))
    monkeypatch.setattr(router, "get_crypto_keywords", lambda: ["bitcoin", "ethereum"])
    monkeypatch.setattr(router, "_ask_agent", lambda text: None)
    monkeypatch.setattr(router, "get_context_summary", lambda: "")
    return seen


@pytest.mark.parametrize("utterance, handler", [
    ("compare bitcoin and ethereum", "handle_compare"),
    ("how is bitcoin doing", "handle_crypto"),
    ("what is quantum computing", "handle_knowledge"),
    ("tell me about black holes", "handle_knowledge"),
    ("check the news", "handle_world_monitor"),
    ("latest tech news", "handle_tech_news"),
    ("tesla stock price", "handle_stock"),
    ("weather today", "handle_weather"),
    ("give me the headlines", "handle_news"),
    ("volume up", "handle_volume"),
    ("take a screenshot", "handle_screenshot"),
    ("what time is it", "handle_time"),
    ("set a timer for five minutes", "handle_timer"),
    ("cpu usage", "handle_system_info"),
    ("search for python tutorials", "handle_search"),
    ("scroll down", "handle_browser_action"),
    ("launch spotify", "handle_app_launch"),
    ("open youtube", "handle_open"),
])
def test_utterance_reaches_handler(calls, utterance, handler):
    router.process_command(utterance)
    assert calls == [handler]


def test_text_is_lowercased_and_trimmed(calls):
    router.process_command("  Open YouTube  ")
    assert calls == ["handle_open"]


def test_thanks_ends_politely_without_a_handler(calls):
    router.process_command("thanks")
    assert calls == ["speak:Anytime, boss."]


@pytest.mark.parametrize("text", ["", " ", "a", None])
def test_empty_input_does_nothing(calls, text):
    router.process_command(text)
    assert calls == []


def test_unknown_command_without_a_model_gets_a_spoken_fallback(calls):
    router.process_command("blorp zizzle")
    assert len(calls) == 1 and calls[0].startswith("speak:")


def test_falls_through_when_a_handler_declines(calls, monkeypatch):
    monkeypatch.setattr(router, "handle_app_launch", lambda text: False)
    router.process_command("start browser")
    assert calls == ["handle_open"]


def test_has_word_matches_whole_words_only():
    assert router._has_word("turn the volume up", "volume")
    assert not router._has_word("a voluminous book", "volume")
    assert router._has_word("what is the time", "what is")


def test_unrecognised_command_goes_to_the_agent_and_its_reply_is_spoken(calls, monkeypatch):
    asked = []
    monkeypatch.setattr(router, "_ask_agent", lambda text: asked.append(text) or "Sorted, boss.")
    router.process_command("Book me a table somewhere nice")
    assert asked == ["book me a table somewhere nice"]
    assert calls == ["speak:Sorted, boss."]


def test_recognised_command_never_reaches_the_agent(calls, monkeypatch):
    monkeypatch.setattr(router, "_ask_agent", lambda text: pytest.fail("agent should not be asked"))
    router.process_command("volume up")
    assert calls == ["handle_volume"]
