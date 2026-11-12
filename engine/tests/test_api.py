"""The engine API: auth, commands, live events and approvals. No audio or model."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from friday.api import app as api
from friday.core.events import EventBus, bus
from friday.core.status import Status

AUTH = {"Authorization": "Bearer secret"}


@pytest.fixture
def client(monkeypatch):
    ran = []
    monkeypatch.setattr(api, "_run_command", ran.append)
    with TestClient(api.create_app(token="secret", voice=False)) as c:
        c.ran = ran
        yield c


def test_health_needs_no_token(client):
    assert client.get("/health").json()["ok"] is True


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "secret"}])
def test_everything_else_needs_the_token(client, headers):
    assert client.get("/status", headers=headers).status_code == 401
    assert client.post("/command", json={"text": "hi"}, headers=headers).status_code == 401
    assert client.ran == []


def test_token_also_works_as_a_query_parameter(client):
    assert client.get("/status?token=secret").status_code == 200


def test_status_returns_the_snapshot(client):
    body = client.get("/status", headers=AUTH).json()
    assert {"state", "heard", "response", "history"} <= set(body)


def test_command_runs_typed_text_like_speech(client):
    response = client.post("/command", json={"text": "  open youtube "}, headers=AUTH)
    assert response.status_code == 200 and response.json()["ok"] is True
    assert client.ran == ["open youtube"]


@pytest.mark.parametrize("body", [{}, {"text": ""}, {"text": "x" * 2001}])
def test_command_rejects_bad_input(client, body):
    assert client.post("/command", json=body, headers=AUTH).status_code == 422
    assert client.ran == []


def test_websocket_rejects_a_wrong_token(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws?token=nope") as ws:
            ws.receive_json()


def test_websocket_sends_a_snapshot_then_live_events(client):
    with client.websocket_connect("/ws?token=secret") as ws:
        first = ws.receive_json()
        assert first["type"] == "snapshot" and "state" in first
        bus.publish("state", state="listening")
        bus.publish("level", source="mic", bands=[0.1] * 16)
        assert ws.receive_json()["state"] == "listening"
        level = ws.receive_json()
        assert level["type"] == "level" and len(level["bands"]) == 16


def test_approval_can_be_answered_from_the_app(client):
    approvals = client.app.state.approvals
    result = {}
    worker = threading.Thread(target=lambda: result.update(allowed=approvals.channel("Sign in to example.com?")))
    worker.start()
    deadline = time.time() + 5
    while not approvals.pending() and time.time() < deadline:
        time.sleep(0.01)

    pending = client.get("/approvals", headers=AUTH).json()
    assert pending[0]["question"] == "Sign in to example.com?"
    assert client.post(f"/approvals/{pending[0]['id']}", json={"allow": True}, headers=AUTH).status_code == 200
    worker.join(5)
    assert result == {"allowed": True}
    assert client.get("/approvals", headers=AUTH).json() == []


def test_answering_an_unknown_approval_is_a_404(client):
    assert client.post("/approvals/nope", json={"allow": True}, headers=AUTH).status_code == 404


def test_unanswered_approval_counts_as_no():
    from friday.agent.approvals import PendingApprovals
    assert PendingApprovals(EventBus(), timeout=0.05).channel("Buy it?") is False


def test_approval_can_be_answered_by_voice():
    from friday.agent.approvals import PendingApprovals
    events = []
    local_bus = EventBus()
    local_bus.subscribe(events.append)
    approvals = PendingApprovals(local_bus, ask_by_voice=lambda q: "yeah go ahead", timeout=5)
    assert approvals.channel("Send it?") is True
    assert [e["type"] for e in events] == ["approval_request", "approval_resolved"]


def test_status_publishes_changes_and_keeps_a_snapshot():
    events = []
    local_bus = EventBus()
    local_bus.subscribe(events.append)
    s = Status(bus=local_bus)
    s.set_state("listening")
    s.set_heard("open youtube")
    s.add_history("open youtube", "ok")
    assert [e["type"] for e in events] == ["state", "heard", "history"]
    assert s.snapshot()["state"] == "listening" and s.snapshot()["history"][0]["command"] == "open youtube"


def test_a_broken_listener_never_breaks_publishing():
    local_bus = EventBus()
    good = []
    local_bus.subscribe(lambda e: 1 / 0)
    unsubscribe = local_bus.subscribe(good.append)
    local_bus.publish("state", state="idle")
    assert len(good) == 1
    unsubscribe()
    local_bus.publish("state", state="idle")
    assert len(good) == 1


def test_whatever_is_spoken_becomes_the_current_response():
    local_bus = EventBus()
    s = Status(bus=local_bus)
    local_bus.publish("speech_start", text="It's four o'clock, boss.")
    assert s.snapshot()["response"] == "It's four o'clock, boss."
