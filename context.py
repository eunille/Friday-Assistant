# context.py — Session context tracker for Friday
# Tracks current topic, last entity, and recent actions for follow-up resolution
import threading
from collections import deque
from logger import log


class SessionContext:
    """Thread-safe session context for tracking conversation state."""

    def __init__(self):
        self._lock = threading.Lock()
        self._topic = None          # "stock", "news", "search", "open", etc.
        self._entity = None         # Last entity: "tesla", "python tutorials", etc.
        self._last_action = None    # Last command type executed
        self._last_url = None       # Last URL opened in browser
        self._history = deque(maxlen=10)  # Recent (topic, entity) pairs

    def update(self, topic, entity=None, url=None):
        """Update context after a command executes."""
        with self._lock:
            if topic:
                self._topic = topic
            if entity:
                self._entity = entity
            if url:
                self._last_url = url
            self._last_action = topic
            if topic or entity:
                self._history.appendleft((topic, entity))

    @property
    def topic(self):
        with self._lock:
            return self._topic

    @property
    def entity(self):
        with self._lock:
            return self._entity

    @property
    def last_action(self):
        with self._lock:
            return self._last_action

    @property
    def last_url(self):
        with self._lock:
            return self._last_url

    def get_context_summary(self):
        """Return a string summary of current context for LLM prompts."""
        with self._lock:
            parts = []
            if self._topic:
                parts.append(f"current_topic={self._topic}")
            if self._entity:
                parts.append(f"last_entity={self._entity}")
            if self._last_url:
                parts.append(f"last_url={self._last_url}")
            if self._history:
                recent = [(t, e) for t, e in list(self._history)[:3] if e]
                if recent:
                    parts.append(f"recent={recent}")
            return "; ".join(parts) if parts else "no prior context"

    def clear(self):
        """Clear all context (e.g. on new session)."""
        with self._lock:
            self._topic = None
            self._entity = None
            self._last_action = None
            self._last_url = None
            self._history.clear()


# Module-level singleton
_ctx = SessionContext()


def update_context(topic, entity=None, url=None):
    """Update the global session context."""
    _ctx.update(topic, entity, url)


def get_context():
    """Get the global session context object."""
    return _ctx


def get_context_summary():
    """Get a string summary of current context."""
    return _ctx.get_context_summary()


def clear_context():
    """Clear all session context."""
    _ctx.clear()
