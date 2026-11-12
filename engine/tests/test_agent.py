"""The agent loop, the tool registry and approvals, with a scripted fake model."""
import pytest

from friday.agent.approvals import Approvals, parse_yes_no
from friday.agent.loop import NO_MODEL_REPLY, STEP_LIMIT_REPLY, Agent
from friday.llm.base import ChatResult, LLMError, ToolCall
from friday.tools.registry import Registry, Tool


class FakeModel:
    """Returns the scripted results in order and records what it was sent."""

    def __init__(self, *results):
        self.results = list(results)
        self.seen = []

    def chat(self, messages, tools=None, max_tokens=None):
        self.seen.append([dict(m) for m in messages])
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def call(name, **arguments):
    return ChatResult("", [ToolCall("c1", name, arguments)])


def registry_with(risk="read"):
    reg = Registry()
    ran = []
    reg.register(Tool("lookup", "Look something up", {"type": "object", "properties": {}},
                      lambda q="": ran.append(q) or f"result for {q}", risk))
    return reg, ran


def test_plain_answer_needs_no_tools():
    reg, ran = registry_with()
    agent = Agent(FakeModel(ChatResult("Morning, boss.")), reg)
    assert agent.run("hello") == "Morning, boss."
    assert ran == []


def test_tool_result_is_fed_back_before_the_answer():
    reg, ran = registry_with()
    model = FakeModel(call("lookup", q="btc"), ChatResult("Bitcoin's up, boss."))
    assert Agent(model, reg).run("how's bitcoin") == "Bitcoin's up, boss."
    assert ran == ["btc"]
    second_request = model.seen[1]
    assert second_request[-1] == {"role": "tool", "tool_call_id": "c1", "content": "result for btc"}
    assert second_request[-2]["tool_calls"][0]["function"]["name"] == "lookup"


def test_last_step_must_answer_without_tools():
    reg, ran = registry_with()
    model = FakeModel(call("lookup", q="1"), call("lookup", q="2"), ChatResult("Best I found, boss."))
    assert Agent(model, reg, max_steps=3).run("dig deep") == "Best I found, boss."
    assert ran == ["1", "2"]
    assert "out of steps" in model.seen[2][-1]["content"].lower()


def test_gives_up_politely_if_the_model_still_wants_tools_at_the_limit():
    reg, ran = registry_with()
    model = FakeModel(*[call("lookup", q=str(i)) for i in range(10)])
    assert Agent(model, reg, max_steps=3).run("loop forever") == STEP_LIMIT_REPLY
    assert len(ran) == 2  # the third call's tools are not run


def test_model_failure_gives_a_spoken_apology_not_a_crash():
    reg, _ = registry_with()
    assert Agent(FakeModel(LLMError("down")), reg).run("hi") == NO_MODEL_REPLY


def test_conversation_is_remembered_across_turns():
    reg, _ = registry_with()
    model = FakeModel(ChatResult("I'm Friday."), ChatResult("You asked who I am."))
    agent = Agent(model, reg)
    agent.run("who are you")
    agent.run("what did I just ask")
    contents = [m["content"] for m in model.seen[1]]
    assert "who are you" in contents and "I'm Friday." in contents


def test_tool_messages_are_not_kept_in_memory():
    reg, _ = registry_with()
    model = FakeModel(call("lookup", q="x"), ChatResult("ok"), ChatResult("again"))
    agent = Agent(model, reg)
    agent.run("first")
    agent.run("second")
    assert all(m["role"] in ("system", "user", "assistant") and "tool_calls" not in m
               for m in model.seen[2])


def test_write_tool_runs_only_after_a_yes():
    reg, ran = registry_with(risk="write")
    asked = []
    approvals = Approvals(channel=lambda q: asked.append(q) or "yes go ahead")
    model = FakeModel(call("lookup", q="send"), ChatResult("Sent."))
    assert Agent(model, reg, approvals=approvals).run("send it") == "Sent."
    assert ran == ["send"] and len(asked) == 1


@pytest.mark.parametrize("answer", ["no", "", "hmm what", None])
def test_write_tool_is_skipped_without_a_clear_yes(answer):
    reg, ran = registry_with(risk="write")
    model = FakeModel(call("lookup", q="send"), ChatResult("Okay, I won't."))
    agent = Agent(model, reg, approvals=Approvals(channel=lambda q: answer))
    assert agent.run("send it") == "Okay, I won't."
    assert ran == []
    assert "declined" in model.seen[1][-1]["content"]


def test_write_tool_is_skipped_when_nobody_can_be_asked():
    reg, ran = registry_with(risk="write")
    model = FakeModel(call("lookup", q="send"), ChatResult("Can't."))
    Agent(model, reg, approvals=None).run("send it")
    assert ran == []


def test_events_report_tool_progress():
    reg, _ = registry_with()
    events = []
    model = FakeModel(call("lookup", q="x"), ChatResult("ok"))
    Agent(model, reg, on_event=events.append).run("go")
    assert [e["type"] for e in events] == ["tool_start", "tool_end"]
    assert events[1]["ok"] is True


def test_registry_reports_errors_as_text():
    reg = Registry()
    reg.register(Tool("boom", "Explodes", {}, lambda: 1 / 0))
    assert reg.call("boom", {}).startswith("Error:")
    assert reg.call("missing", {}).startswith("Error:")
    assert reg.call("boom", {"unexpected": 1}).startswith("Error:")


def test_registry_serialises_and_truncates_results():
    reg = Registry()
    reg.register(Tool("data", "Data", {}, lambda: [{"title": "a"}]))
    reg.register(Tool("big", "Big", {}, lambda: "x" * 10000))
    reg.register(Tool("nothing", "None", {}, lambda: None))
    assert reg.call("data", {}) == '[{"title": "a"}]'
    assert len(reg.call("big", {})) == 4000
    assert reg.call("nothing", {}) == "Done."


def test_builtin_registry_exposes_valid_schemas():
    from friday.tools.builtin import build_registry
    reg = build_registry()
    assert {"web_search", "read_page", "open_website", "launch_app", "get_time"} <= set(reg.names())
    for schema in reg.schemas():
        assert schema["type"] == "function" and schema["function"]["parameters"]["type"] == "object"
    assert all(reg.get(n).risk == "read" for n in reg.names())
    assert "20" in reg.call("get_time", {})  # a year


@pytest.mark.parametrize("text, expected", [
    ("yes", True), ("yeah go ahead", True), ("okay do it", True),
    ("no", False), ("don't", False), ("no, yes, wait", False), ("cancel that", False),
    ("the weather is nice", None), ("", None), (None, None),
])
def test_parse_yes_no(text, expected):
    assert parse_yes_no(text) is expected


def test_always_allow_skips_the_question():
    asked = []
    approvals = Approvals(channel=lambda q: asked.append(q) or "no")
    approvals.allow_always("lookup")
    assert approvals.ask("Go ahead?", key="lookup") is True
    assert asked == []
