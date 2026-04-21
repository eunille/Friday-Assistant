# tui.py — Modern Iron Man-inspired terminal UI for Friday Assistant
import math
import time
import threading
from datetime import datetime
from collections import deque
from rich.console import Console, Group
from rich.text import Text
from rich.live import Live
from rich.align import Align
from rich.layout import Layout
from rich.panel import Panel
from rich.columns import Columns

# --- States ---
STATE_IDLE = "idle"
STATE_LISTENING = "listening"
STATE_THINKING = "thinking"
STATE_SPEAKING = "speaking"
STATE_STARTUP = "startup"

# --- Color palette (Iron Man / purple HUD) ---
CLR_PRIMARY = "bright_magenta"
CLR_ACCENT = "medium_purple3"
CLR_DIM = "grey50"
CLR_LISTENING = "green3"
CLR_SPEAKING = "bright_magenta"
CLR_THINKING = "medium_purple3"
CLR_BORDER = "grey37"
CLR_HEADER = "bold bright_magenta"
CLR_SUBTITLE = "grey62"


def _wave_heights(frame, num_bars=11, max_h=10):
    """Generate smooth wave bar heights — more bars, taller, smoother."""
    heights = []
    for i in range(num_bars):
        h = (
            math.sin(frame * 0.25 + i * 0.7) * 0.35
            + math.sin(frame * 0.12 + i * 1.3) * 0.25
            + math.sin(frame * 0.4 + i * 0.4) * 0.25
            + math.sin(frame * 0.08 + i * 2.0) * 0.15
        )
        h = int((h + 1) / 2 * max_h)
        heights.append(max(1, min(max_h, h)))
    return heights


class FridayTUI:
    """Modern Iron Man HUD-style terminal UI — purple theme, activity sidebar."""

    def __init__(self):
        self.console = Console()
        self.state = STATE_STARTUP
        self.frame_idx = 0
        self.start_time = datetime.now()
        self.history = deque(maxlen=8)
        self.last_heard = ""
        self.last_response = ""
        self.mic_status = ""
        self.model_name = ""
        self.silence_threshold = 0
        self.ambient_noise = 0.0
        self._live = None
        self._running = False
        self._lock = threading.Lock()

    # --- State setters (thread-safe) ---

    def set_state(self, state):
        with self._lock:
            self.state = state
            self.frame_idx = 0

    def set_mic_status(self, status):
        with self._lock:
            self.mic_status = status

    def set_model(self, name):
        with self._lock:
            self.model_name = name

    def set_calibration(self, ambient, threshold):
        with self._lock:
            self.ambient_noise = ambient
            self.silence_threshold = threshold

    def set_heard(self, text):
        with self._lock:
            self.last_heard = text

    def set_response(self, text):
        with self._lock:
            self.last_response = text
            if text:
                timestamp = datetime.now().strftime("%H:%M")
                self.history.appendleft(("friday", timestamp, text))

    def add_history(self, command, result):
        with self._lock:
            timestamp = datetime.now().strftime("%H:%M")
            self.history.appendleft(("user", timestamp, command))

    # --- Renderers ---

    def _render_waveform(self, heights, color=CLR_SPEAKING):
        """Render tall vertical bars with gradient effect."""
        max_h = max(heights) if heights else 1
        lines = []
        for row in range(max(heights), 0, -1):
            line = Text()
            for i, h in enumerate(heights):
                if i > 0:
                    line.append(" ")
                if h >= row:
                    # Gradient: brighter at top
                    if row > max_h * 0.7:
                        line.append("██", style=f"bold {color}")
                    elif row > max_h * 0.4:
                        line.append("▓▓", style=f"{CLR_ACCENT}")
                    else:
                        line.append("░░", style=f"{CLR_DIM}")
                else:
                    line.append("  ")
            lines.append(Align.center(line))
        return lines

    def _render_dot(self, pulse_val, color=CLR_PRIMARY):
        """Render a single pulsing dot with ring effect."""
        chars = ["·", "∘", "○", "◎", "●", "◉"]
        idx = int(pulse_val * (len(chars) - 1))
        return Align.center(Text(chars[min(idx, len(chars) - 1)], style=f"bold {color}"))

    def _render_thinking(self, frame):
        """Render thinking dots with purple glow."""
        patterns = [
            "·  ·  ·",
            "●  ·  ·",
            "●  ●  ·",
            "●  ●  ●",
            "·  ●  ●",
            "·  ·  ●",
        ]
        return Align.center(Text(patterns[frame % len(patterns)], style=f"bold {CLR_THINKING}"))

    def _render_listening_dots(self, frame):
        """Render animated bouncing dots for listening state."""
        num_dots = 7
        parts = []
        for i in range(num_dots):
            val = (math.sin(frame * 0.2 + i * 0.9) + 1) / 2
            chars = ["·", "∘", "○", "●", "◉"]
            idx = int(val * (len(chars) - 1))
            parts.append(chars[min(idx, len(chars) - 1)])
        return Align.center(Text("  ".join(parts), style=f"bold {CLR_LISTENING}"))

    def _render_sidebar(self, height):
        """Render the activity sidebar showing conversation history."""
        lines = []

        # Current state indicator
        state_labels = {
            STATE_IDLE: ("STANDBY", CLR_DIM),
            STATE_LISTENING: ("LISTENING", CLR_LISTENING),
            STATE_THINKING: ("PROCESSING", CLR_THINKING),
            STATE_SPEAKING: ("SPEAKING", CLR_SPEAKING),
            STATE_STARTUP: ("BOOTING", CLR_DIM),
        }
        label, color = state_labels.get(self.state, ("UNKNOWN", CLR_DIM))
        status_line = Text()
        status_line.append("◆ ", style=f"bold {color}")
        status_line.append(label, style=f"bold {color}")
        lines.append(status_line)
        lines.append(Text("─" * 28, style=CLR_BORDER))

        # Current heard text
        if self.last_heard:
            lines.append(Text("YOU", style=f"bold {CLR_DIM}"))
            heard_display = self.last_heard if len(self.last_heard) <= 26 else self.last_heard[:23] + "..."
            lines.append(Text(f"  {heard_display}", style="white"))
            lines.append(Text())

        # Current response
        if self.last_response:
            lines.append(Text("FRIDAY", style=CLR_HEADER))
            resp = self.last_response
            # Word wrap at ~26 chars
            while resp:
                chunk = resp[:26]
                if len(resp) > 26:
                    # Try to break at word boundary
                    space_idx = chunk.rfind(" ")
                    if space_idx > 10:
                        chunk = resp[:space_idx]
                lines.append(Text(f"  {chunk}", style=CLR_SUBTITLE))
                resp = resp[len(chunk):].lstrip()
            lines.append(Text())

        # History
        if self.history:
            lines.append(Text("─" * 28, style=CLR_BORDER))
            lines.append(Text("ACTIVITY LOG", style=f"bold {CLR_DIM}"))
            for speaker, ts, msg in list(self.history)[:5]:
                prefix = "▸" if speaker == "user" else "◂"
                color = "white" if speaker == "user" else CLR_SUBTITLE
                clip = msg if len(msg) <= 24 else msg[:21] + "..."
                entry = Text()
                entry.append(f" {prefix} ", style=CLR_DIM)
                entry.append(clip, style=color)
                lines.append(entry)

        # Pad to fill height
        while len(lines) < height:
            lines.append(Text())

        return lines[:height]

    def build_display(self):
        """Build the full-screen display with center visualization + sidebar."""
        with self._lock:
            state = self.state
            idx = self.frame_idx
            self.frame_idx += 1
            response = self.last_response
            heard = self.last_heard

        term_h = self.console.height or 30
        term_w = self.console.width or 80

        # --- Center visualization ---
        center_lines = []

        if state == STATE_SPEAKING:
            heights = _wave_heights(idx, num_bars=11, max_h=10)
            center_lines = self._render_waveform(heights)
        elif state == STATE_LISTENING:
            center_lines = [self._render_listening_dots(idx)]
        elif state == STATE_THINKING:
            center_lines = [self._render_thinking(idx)]
        elif state == STATE_STARTUP:
            center_lines = [Align.center(Text("· · ·", style=f"dim {CLR_ACCENT}"))]
        else:
            pulse = (math.sin(idx * 0.12) + 1) / 2
            center_lines = [self._render_dot(pulse)]

        # State label below visualization
        state_text = Text()
        if state == STATE_LISTENING:
            state_text = Text("listening", style=f"italic {CLR_LISTENING}")
        elif state == STATE_SPEAKING:
            state_text = Text("speaking", style=f"italic {CLR_SPEAKING}")
        elif state == STATE_THINKING:
            state_text = Text("processing", style=f"italic {CLR_THINKING}")
        elif state == STATE_IDLE:
            state_text = Text("say hey jarvis", style=f"italic {CLR_DIM}")

        # --- Build layout ---
        # Sidebar on right (30 chars), center takes the rest
        sidebar_width = 30
        use_sidebar = term_w >= 70

        # Vertical centering for center content
        content_h = len(center_lines) + 3
        center_area_h = term_h - 4  # Leave room for header/footer
        top_pad = max((center_area_h - content_h) // 2, 1)

        # Center group
        center_items = [Text("\n" * top_pad)]
        center_items.extend(center_lines)
        center_items.append(Text())
        center_items.append(Align.center(state_text))

        # Header
        header = Text()
        header.append("  F R I D A Y", style=CLR_HEADER)
        uptime = datetime.now() - self.start_time
        mins = int(uptime.total_seconds() // 60)
        header.append(f"  ·  {mins}m", style=CLR_DIM)

        # Footer
        footer = Text()
        mic_clean = self.mic_status.replace("✅ ", "").replace("❌ ", "")
        if mic_clean:
            footer.append(f"  {mic_clean}", style=CLR_DIM)
        if self.model_name:
            footer.append(f"  ·  {self.model_name}", style=CLR_DIM)

        if use_sidebar:
            sidebar_lines = self._render_sidebar(center_area_h)
            sidebar_content = Group(*sidebar_lines)

            # Build with sidebar
            layout = Layout()
            layout.split_column(
                Layout(Align.left(header), name="header", size=1),
                Layout(name="body"),
                Layout(Align.left(footer), name="footer", size=1),
            )
            layout["body"].split_row(
                Layout(Group(*center_items), name="center"),
                Layout(Text("│\n" * center_area_h, style=CLR_BORDER), name="divider", size=1),
                Layout(sidebar_content, name="sidebar", size=sidebar_width),
            )
        else:
            # Narrow terminal — no sidebar
            layout = Layout()
            layout.split_column(
                Layout(Align.left(header), name="header", size=1),
                Layout(Group(*center_items), name="center"),
                Layout(Align.left(footer), name="footer", size=1),
            )

        return layout

    def start(self):
        """Start the live TUI rendering loop."""
        self._running = True
        self._live = Live(
            self.build_display(),
            console=self.console,
            refresh_per_second=10,
            screen=True,
        )
        self._live.start()
        self._start_refresh_thread()

    def stop(self):
        """Stop the TUI."""
        self._running = False
        if self._live:
            self._live.stop()

    def _start_refresh_thread(self):
        """Background thread to refresh the display."""
        def _refresh():
            while self._running:
                try:
                    if self._live:
                        self._live.update(self.build_display())
                except Exception:
                    pass
                time.sleep(0.1)

        thread = threading.Thread(target=_refresh, daemon=True)
        thread.start()

    def print_startup(self, message):
        """Print a message during startup (before TUI takes over)."""
        self.console.print(f"  {message}")
