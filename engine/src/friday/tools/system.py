# handlers/system_handlers.py — Volume, screenshot, time, timer, system info, app launch
import platform
import subprocess
import re
from datetime import datetime

import psutil

from friday.voice.tts.speaker import speak
from friday.tools import app_launcher
from friday.tools.timers import start_timer, get_remaining, cancel_timer
from friday.agent.context import update_context
from friday.core.log import log

_IS_WINDOWS = platform.system() == "Windows"

# Windows virtual-key codes for media keys
_VK_VOLUME_MUTE = 0xAD
_VK_VOLUME_DOWN = 0xAE
_VK_VOLUME_UP = 0xAF
_VK_SNAPSHOT = 0x2C


def _win_press_key(vk_code, times=1):
    """Simulate a key press on Windows via user32 (no dependencies)."""
    import ctypes
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)          # key down
        ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)          # key up


def handle_volume(text):
    """Control system volume — media keys on Windows, pactl on Linux."""
    if _IS_WINDOWS:
        # Each volume key press changes volume by 2 units (of 100)
        if "mute" in text or "unmute" in text:
            _win_press_key(_VK_VOLUME_MUTE)
            speak("Audio toggled.")
            return True
        if "max" in text or "full" in text:
            _win_press_key(_VK_VOLUME_UP, times=50)
            speak("Volume at maximum.")
            return True
        if "up" in text or "increase" in text or "louder" in text:
            _win_press_key(_VK_VOLUME_UP, times=5)
            speak("Volume up.")
            return True
        if "down" in text or "decrease" in text or "lower" in text or "quieter" in text:
            _win_press_key(_VK_VOLUME_DOWN, times=5)
            speak("Volume down.")
            return True
        return False

    try:
        if "mute" in text or "unmute" in text:
            subprocess.run(
                ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"], check=True
            )
            speak("Audio toggled.")
            return True
        if "up" in text or "increase" in text or "louder" in text:
            subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"], check=True
            )
            speak("Volume up.")
            return True
        if "down" in text or "decrease" in text or "lower" in text or "quieter" in text:
            subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"], check=True
            )
            speak("Volume down.")
            return True
        if "max" in text or "full" in text:
            subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "100%"], check=True
            )
            speak("Volume at maximum.")
            return True
    except subprocess.CalledProcessError:
        speak("I couldn't adjust the volume.")
    return False


def handle_screenshot(text):
    """Take a screenshot — PrtScn to clipboard on Windows, Spectacle on Linux."""
    if _IS_WINDOWS:
        try:
            _win_press_key(_VK_SNAPSHOT)
            speak("Screenshot taken and copied to clipboard.")
            return True
        except Exception as e:
            log.error(f"Screenshot failed: {e}")
            speak("I couldn't take a screenshot.")
            return False

    try:
        subprocess.Popen(["spectacle", "--background", "--copy-image"])
        speak("Screenshot taken and copied to clipboard.")
        return True
    except FileNotFoundError:
        speak("Spectacle is not installed. Install it with: sudo dnf install spectacle")
        return False


def handle_time(text):
    """Tell the current time."""
    now = datetime.now()
    time_str = now.strftime("%I:%M %p")
    speak(f"It's currently {time_str}.")
    update_context("time")
    return True


def handle_timer(text):
    """Set, check, or cancel timers."""
    if any(word in text for word in ["cancel", "stop", "clear", "remove"]):
        if cancel_timer():
            speak("Timer cancelled, boss.")
        else:
            speak("No active timers to cancel, boss.")
        return True

    if any(phrase in text for phrase in ["how much time", "time left",
                                         "time remaining", "how long"]):
        remaining = get_remaining()
        if remaining is None:
            speak("No active timers right now, boss.")
        else:
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            if mins > 0:
                speak(f"About {mins} minutes and {secs} seconds left, boss.")
            else:
                speak(f"About {secs} seconds left, boss.")
        return True

    match = re.search(r"(\d+)\s*(second|minute|hour)s?", text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        multiplier = {"second": 1, "minute": 60, "hour": 3600}
        seconds = amount * multiplier.get(unit, 1)
        label = f"{amount}_{unit}"

        if start_timer(label, seconds):
            if unit == "second":
                speak(f"Timer set for {amount} seconds, boss.")
            elif unit == "minute":
                speak(f"Timer set for {amount} minutes, boss.")
            else:
                speak(f"Timer set for {amount} hours, boss.")
        else:
            speak("There's already a timer running with that duration, boss.")
        update_context("timer", f"{amount} {unit}s")
        return True

    speak("I didn't catch the duration, boss. Try something like 'set a timer for 5 minutes'.")
    return True


def handle_system_info(text):
    """Report system metrics — CPU, RAM, battery."""
    parts = []

    if any(word in text for word in ["cpu", "processor"]):
        cpu = psutil.cpu_percent(interval=0.5)
        parts.append(f"CPU is at {cpu}%")
    elif any(word in text for word in ["ram", "memory"]):
        mem = psutil.virtual_memory()
        used_gb = mem.used / (1024 ** 3)
        total_gb = mem.total / (1024 ** 3)
        parts.append(f"Memory usage: {used_gb:.1f} of {total_gb:.1f} gigs, that's {mem.percent}%")
    elif any(word in text for word in ["battery", "charge", "power"]):
        batt = psutil.sensors_battery()
        if batt:
            status = "charging" if batt.power_plugged else "on battery"
            parts.append(f"Battery is at {batt.percent:.0f}%, {status}")
        else:
            parts.append("No battery detected — probably on AC power")
    else:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        used_gb = mem.used / (1024 ** 3)
        total_gb = mem.total / (1024 ** 3)
        parts.append(f"CPU at {cpu}%")
        parts.append(f"Memory at {mem.percent}%, {used_gb:.1f} of {total_gb:.1f} gigs used")
        batt = psutil.sensors_battery()
        if batt:
            status = "charging" if batt.power_plugged else "on battery"
            parts.append(f"Battery at {batt.percent:.0f}%, {status}")

    speak("Here's the rundown, boss. " + ". ".join(parts) + ".")
    update_context("system")
    return True


def handle_app_launch(text):
    """Launch a desktop application by name."""
    match = re.search(r"(?:launch|start|run)\s+(?:the\s+)?(.+)", text)
    if not match:
        return False

    query = match.group(1).strip()
    app_name = app_launcher.launch(query)
    if app_name:
        speak(f"Launching {app_name}, boss.")
        update_context("app", app_name)
        return True

    return False
