"""OpenRouter: free models only, and automatic switching when one is limited."""
import httpx
import pytest

from friday.llm.base import LLMError, NoModelAvailable
from friday.llm.openrouter import OpenRouterFree, is_free, supports_tools

MODELS = {"data": [
    {"id": "paid/big", "pricing": {"prompt": "0.000003", "completion": "0.000015"},
     "supported_parameters": ["tools"]},
    {"id": "free/a:free", "pricing": {"prompt": "0", "completion": "0"},
     "supported_parameters": ["tools"]},
    {"id": "free/b:free", "pricing": {"prompt": "0", "completion": "0"},
     "supported_parameters": ["tools", "temperature"]},
    {"id": "free/no-tools:free", "pricing": {"prompt": "0", "completion": "0"},
     "supported_parameters": ["temperature"]},
    {"id": "half/free-prompt", "pricing": {"prompt": "0", "completion": "0.00001"},
     "supported_parameters": ["tools"]},
    {"id": "odd/no-pricing", "supported_parameters": ["tools"]},
]}


def ok(text="hello boss", tool_calls=None):
    message = {"role": "assistant", "content": text}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return httpx.Response(200, json={"choices": [{"message": message}]})


class Server:
    """Fake OpenRouter: `replies` maps model id -> list of responses, used in order."""

    def __init__(self, replies):
        self.replies = {k: list(v) for k, v in replies.items()}
        self.requested = []

    def __call__(self, request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELS)
        import json
        model = json.loads(request.content)["model"]
        self.requested.append(model)
        queue = self.replies.get(model) or [httpx.Response(500)]
        return queue.pop(0) if len(queue) > 1 else queue[0]


def make(replies, **kw):
    server = Server(replies)
    clock = {"t": 0.0}
    provider = OpenRouterFree(
        "test-key", preference=["free/a:free"],
        client=httpx.Client(transport=httpx.MockTransport(server)),
        clock=lambda: clock["t"], **kw)
    return provider, server, clock


def test_only_zero_priced_tool_models_are_listed():
    provider, _, _ = make({})
    assert provider.free_models() == ["free/a:free", "free/b:free"]


def test_is_free_requires_both_prices_present_and_zero():
    assert is_free({"pricing": {"prompt": "0", "completion": "0"}})
    assert not is_free({"pricing": {"prompt": "0", "completion": "0.1"}})
    assert not is_free({"pricing": {"prompt": "0"}})
    assert not is_free({})
    assert not supports_tools({})


def test_answers_from_the_preferred_free_model():
    provider, server, _ = make({"free/a:free": [ok("hi")]})
    result = provider.chat([{"role": "user", "content": "hey"}])
    assert (result.content, result.model) == ("hi", "free/a:free")
    assert server.requested == ["free/a:free"]


@pytest.mark.parametrize("status", [429, 402, 404, 503])
def test_limited_model_falls_over_to_the_next_free_one(status):
    provider, server, _ = make({"free/a:free": [httpx.Response(status)], "free/b:free": [ok("from b")]})
    result = provider.chat([{"role": "user", "content": "hey"}])
    assert result.model == "free/b:free"
    assert server.requested == ["free/a:free", "free/b:free"]


def test_error_inside_a_200_reply_also_falls_over():
    broken = httpx.Response(200, json={"error": {"code": 429, "message": "rate limited upstream"}})
    provider, _, _ = make({"free/a:free": [broken], "free/b:free": [ok("from b")]})
    assert provider.chat([{"role": "user", "content": "x"}]).model == "free/b:free"


def test_empty_reply_moves_on_without_resting_the_model():
    provider, server, _ = make({"free/a:free": [ok(""), ok("a works now")], "free/b:free": [ok("from b")]})
    assert provider.chat([{"role": "user", "content": "1"}]).model == "free/b:free"
    assert provider.chat([{"role": "user", "content": "2"}]).model == "free/a:free"


def test_limited_model_rests_then_is_tried_again_after_cooldown():
    provider, server, clock = make(
        {"free/a:free": [httpx.Response(429), ok("a is back")], "free/b:free": [ok("from b")]},
        cooldown_seconds=300)
    provider.chat([{"role": "user", "content": "1"}])
    provider.chat([{"role": "user", "content": "2"}])
    assert server.requested == ["free/a:free", "free/b:free", "free/b:free"]  # a skipped while resting
    clock["t"] = 301
    assert provider.chat([{"role": "user", "content": "3"}]).model == "free/a:free"


def test_a_paid_model_is_never_requested_even_when_every_free_one_fails():
    provider, server, _ = make({"free/a:free": [httpx.Response(429)], "free/b:free": [httpx.Response(429)]})
    with pytest.raises(NoModelAvailable):
        provider.chat([{"role": "user", "content": "x"}])
    assert set(server.requested) == {"free/a:free", "free/b:free"}
    with pytest.raises(NoModelAvailable):  # all resting: only the longest-rested free one is retried
        provider.chat([{"role": "user", "content": "x"}])
    assert server.requested == ["free/a:free", "free/b:free", "free/a:free"]
    assert "paid/big" not in server.requested


def test_when_all_are_resting_the_longest_rested_gets_another_try():
    provider, server, clock = make(
        {"free/a:free": [httpx.Response(429), ok("a recovered")], "free/b:free": [httpx.Response(429)]})
    with pytest.raises(NoModelAvailable):
        provider.chat([{"role": "user", "content": "1"}])
    clock["t"] = 5  # well inside the cool-down
    assert provider.chat([{"role": "user", "content": "2"}]).content == "a recovered"


def test_local_model_must_match_name_and_tag_exactly():
    from friday.llm.ollama_provider import OllamaLocal

    class FakeOllama:
        def list(self):
            return {"models": [{"name": "qwen3:1.7b"}]}

    assert not OllamaLocal("qwen3:4b", client=FakeOllama()).available()
    assert OllamaLocal("qwen3:1.7b", client=FakeOllama()).available()


def test_a_paid_model_in_the_preference_list_is_ignored():
    server = Server({"free/a:free": [ok()]})
    provider = OpenRouterFree("k", preference=["paid/big", "free/a:free"],
                              client=httpx.Client(transport=httpx.MockTransport(server)))
    provider.chat([{"role": "user", "content": "x"}])
    assert "paid/big" not in provider.free_models()
    assert server.requested == ["free/a:free"]


def test_rejected_key_stops_immediately_instead_of_burning_through_models():
    provider, server, _ = make({"free/a:free": [httpx.Response(401)], "free/b:free": [ok()]})
    with pytest.raises(LLMError):
        provider.chat([{"role": "user", "content": "x"}])
    assert server.requested == ["free/a:free"]


def test_missing_key_is_reported_and_unavailable():
    provider = OpenRouterFree("")
    assert not provider.available()
    with pytest.raises(LLMError):
        provider.chat([{"role": "user", "content": "x"}])


def test_tool_calls_are_parsed_with_json_arguments():
    call = {"id": "c1", "type": "function",
            "function": {"name": "web_search", "arguments": '{"query": "btc price"}'}}
    provider, _, _ = make({"free/a:free": [ok("", [call])]})
    result = provider.chat([{"role": "user", "content": "x"}], tools=[{"type": "function"}])
    assert result.tool_calls[0].name == "web_search"
    assert result.tool_calls[0].arguments == {"query": "btc price"}
