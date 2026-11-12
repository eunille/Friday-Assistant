"""What Friday is doing right now.

The voice loop reports here. Each change is kept in a snapshot (so a newly
connected app can catch up), published on the event bus, and passed on to the
terminal screen when one is attached.
"""
import threading

from friday.core.events import bus as default_bus

STATE_STARTUP = "startup"
STATE_IDLE = "idle"
STATE_LISTENING = "listening"
STATE_THINKING = "thinking"
STATE_SPEAKING = "speaking"


class Status:
    def __init__(self, bus=default_bus, ui=None):
        self._bus = bus
        self._ui = ui
        self._lock = threading.Lock()
        self._snapshot = {"state": STATE_STARTUP, "heard": "", "response": "",
                          "mic": "", "model": "", "history": []}
        # Handlers speak directly; whatever is spoken becomes the current response.
        bus.subscribe(self._on_event)

    def _on_event(self, event):
        if event.get("type") == "speech_start":
            with self._lock:
                self._snapshot["response"] = event.get("text", "")
            if self._ui:
                self._ui.set_response(event.get("text", ""))

    def attach_ui(self, ui):
        self._ui = ui

    def snapshot(self):
        with self._lock:
            return {**self._snapshot, "history": list(self._snapshot["history"])}

    def _set(self, key, value, event, **data):
        with self._lock:
            self._snapshot[key] = value
        self._bus.publish(event, **data)

    def set_state(self, state):
        self._set("state", state, "state", state=state)
        if self._ui:
            self._ui.set_state(state)

    def set_heard(self, text):
        self._set("heard", text, "heard", text=text)
        if self._ui:
            self._ui.set_heard(text)

    def set_response(self, text):
        self._set("response", text, "response", text=text)
        if self._ui:
            self._ui.set_response(text)

    def set_mic_status(self, status):
        self._set("mic", status, "mic", status=status)
        if self._ui:
            self._ui.set_mic_status(status)

    def set_model(self, name):
        self._set("model", name, "model", name=name)
        if self._ui:
            self._ui.set_model(name)

    def set_calibration(self, ambient, threshold):
        self._bus.publish("calibration", ambient=float(ambient), threshold=float(threshold))
        if self._ui:
            self._ui.set_calibration(ambient, threshold)

    def add_history(self, command, result):
        with self._lock:
            self._snapshot["history"] = (self._snapshot["history"] + [{"command": command, "result": result}])[-20:]
        self._bus.publish("history", command=command, result=result)
        if self._ui:
            self._ui.add_history(command, result)


status = Status()
