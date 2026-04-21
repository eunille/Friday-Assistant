# timers.py — Timer/alarm manager for Friday
import atexit
import threading
import time

from speaker import speak
from logger import log


class TimerManager:
    """Thread-safe timer manager with countdown tracking."""

    _ALERTS = [
        "Time's up, boss!",
        "Timer's done, boss. That's your cue.",
        "Boss, your timer just went off.",
        "And that's time. You're up, boss.",
        "Ding! Timer complete, boss.",
    ]

    def __init__(self):
        self._timers = {}
        self._lock = threading.Lock()
        atexit.register(self.cancel_all)

    def start(self, label, seconds):
        """Start a named timer. Returns True if started, False if duplicate."""
        with self._lock:
            if label in self._timers:
                return False
            timer = threading.Timer(seconds, self._fire, args=(label,))
            timer.daemon = True
            self._timers[label] = {
                "timer": timer,
                "start": time.monotonic(),
                "duration": seconds,
            }
            timer.start()
            log.info(f"Timer '{label}' started for {seconds}s")
            return True

    def _fire(self, label):
        """Callback when a timer expires."""
        with self._lock:
            self._timers.pop(label, None)
        import random
        speak(random.choice(self._ALERTS))
        log.info(f"Timer '{label}' fired")

    def remaining(self, label=None):
        """Get seconds remaining. If no label, returns first active timer.
        Returns None if no timer found."""
        with self._lock:
            if label and label in self._timers:
                entry = self._timers[label]
                elapsed = time.monotonic() - entry["start"]
                return max(0, entry["duration"] - elapsed)
            if not label and self._timers:
                entry = next(iter(self._timers.values()))
                elapsed = time.monotonic() - entry["start"]
                return max(0, entry["duration"] - elapsed)
            return None

    def active_count(self):
        with self._lock:
            return len(self._timers)

    def cancel(self, label=None):
        """Cancel a timer by label, or the first active one if no label."""
        with self._lock:
            if label and label in self._timers:
                self._timers[label]["timer"].cancel()
                self._timers.pop(label)
                return True
            if not label and self._timers:
                key = next(iter(self._timers))
                self._timers[key]["timer"].cancel()
                self._timers.pop(key)
                return True
            return False

    def cancel_all(self):
        """Cancel all active timers. Called at exit."""
        with self._lock:
            for entry in self._timers.values():
                entry["timer"].cancel()
            self._timers.clear()


# Module-level singleton
_manager = TimerManager()

start_timer = _manager.start
get_remaining = _manager.remaining
active_timer_count = _manager.active_count
cancel_timer = _manager.cancel
cancel_all_timers = _manager.cancel_all
