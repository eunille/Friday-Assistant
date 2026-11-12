"""A small in-process event bus.

The voice loop, speaker and agent publish what they are doing; the API
forwards it to the desktop app. Publishing never blocks and never raises.
"""
import threading
import time


class EventBus:
    def __init__(self):
        self._subscribers = []
        self._lock = threading.Lock()

    def subscribe(self, callback):
        """callback(event: dict) is called on the publisher's thread. Returns an unsubscribe function."""
        with self._lock:
            self._subscribers.append(callback)

        def unsubscribe():
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)
        return unsubscribe

    @property
    def has_subscribers(self):
        return bool(self._subscribers)

    def publish(self, type, **data):
        if not self._subscribers:
            return
        event = {"type": type, "t": time.time(), **data}
        with self._lock:
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:
                pass  # a broken listener must never break the voice loop


bus = EventBus()
