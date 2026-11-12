"""Asking the user before Friday does something that changes things.

The broker doesn't know how the question reaches the user. A channel does:
in the terminal it speaks and listens; in the app it also shows a card.
"""
import re
import threading
import uuid

_YES = re.compile(r"\b(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|allow|approved?|confirm|please do)\b")
_NO = re.compile(r"\b(no|nope|nah|don'?t|do not|stop|cancel|deny|denied|never mind|nevermind)\b")


def parse_yes_no(text):
    """True for yes, False for no, None if it's neither. A 'no' wins over a 'yes'."""
    text = (text or "").lower()
    if _NO.search(text):
        return False
    if _YES.search(text):
        return True
    return None


class PendingApprovals:
    """An approval channel that can be answered from the app or by voice.

    Publishes 'approval_request' on the bus, asks out loud if a voice asker is
    given, and waits for whichever answer arrives first. No answer means no.
    """

    def __init__(self, bus, ask_by_voice=None, timeout=60.0):
        self._bus = bus
        self._ask_by_voice = ask_by_voice
        self._timeout = timeout
        self._lock = threading.Lock()
        self._waiting: dict[str, dict] = {}

    def pending(self):
        with self._lock:
            return [{"id": k, "question": v["question"]} for k, v in self._waiting.items()]

    def resolve(self, request_id, allow) -> bool:
        """Answer a pending request. Returns False if it is unknown or already answered."""
        with self._lock:
            entry = self._waiting.get(request_id)
            if entry is None or entry["answer"] is not None:
                return False
            entry["answer"] = bool(allow)
        entry["event"].set()
        return True

    def channel(self, question) -> bool:
        request_id = uuid.uuid4().hex[:12]
        entry = {"question": question, "answer": None, "event": threading.Event()}
        with self._lock:
            self._waiting[request_id] = entry
        self._bus.publish("approval_request", id=request_id, question=question)

        if self._ask_by_voice:
            def by_voice():
                try:
                    verdict = parse_yes_no(self._ask_by_voice(question))
                except Exception:
                    verdict = None
                if verdict is not None:
                    self.resolve(request_id, verdict)
            threading.Thread(target=by_voice, daemon=True).start()

        entry["event"].wait(self._timeout)
        with self._lock:
            self._waiting.pop(request_id, None)
        allowed = entry["answer"] is True
        self._bus.publish("approval_resolved", id=request_id, allowed=allowed)
        return allowed


class Approvals:
    def __init__(self, channel=None):
        """channel(question: str) -> the user's answer as text (or True/False)."""
        self._channel = channel
        self._always: set[str] = set()

    def set_channel(self, channel):
        self._channel = channel

    def allow_always(self, key):
        self._always.add(key)

    def ask(self, question, key=None) -> bool:
        """Ask once. Anything that isn't a clear yes counts as no."""
        if key and key in self._always:
            return True
        if self._channel is None:
            return False
        answer = self._channel(question)
        if isinstance(answer, bool):
            return answer
        return parse_yes_no(answer) is True
