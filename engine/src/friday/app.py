"""Friday's voice loop: wake -> listen -> act -> speak -> repeat.

`main()` runs it in the terminal with the status screen. The API runs
`run_voice_loop()` on a background thread and streams the same status.
"""
import os
import signal
import sys
import threading
import time

# Windows consoles default to a legacy codepage that can't print the
# emoji used in status output — force UTF-8 so prints never crash.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from friday.agent.context import clear_context
from friday.agent.personality import get_farewell, get_greeting
from friday.agent.router import process_command
from friday.core.config import load_config
from friday.core.log import log
from friday.core.status import (
    STATE_IDLE, STATE_LISTENING, STATE_SPEAKING, STATE_THINKING, status,
)
from friday.voice.audio import find_working_mic, reset_mic_cache
from friday.voice.stt import calibrate_silence, get_model, listen
from friday.voice.tts.speaker import speak
from friday.voice.wake_word import create_wake_word_detector, listen_for_wake_word_timeout

# Set to wake Friday without the wake word (Enter key, push-to-talk, the app).
activated = threading.Event()
# Set to end the loop.
stop_requested = threading.Event()

# --- Gibberish / filler word filter ---
_FILLER_WORDS = frozenset({
    "a", "an", "the", "this", "that", "is", "it", "i", "my", "me", "we",
    "he", "she", "and", "or", "but", "to", "of", "in", "on", "for", "so",
    "um", "uh", "ah", "oh", "hmm", "huh", "ok", "okay", "yeah", "yes",
    "no", "not", "do", "does", "did", "was", "were", "are", "am", "be",
    "been", "has", "have", "had", "will", "would", "could", "should",
    "just", "like", "well", "you", "your", "its", "with", "from",
})
_MIN_MEANINGFUL_WORDS = 1


def _is_meaningful(text):
    """Return True if the transcription contains at least one meaningful word.
    Filters out pure filler / misheard gibberish like 'this is' or 'uh'."""
    words = text.lower().split()
    meaningful = [w for w in words if w.strip(".,!?'\"") not in _FILLER_WORDS]
    return len(meaningful) >= _MIN_MEANINGFUL_WORDS


def say(text):
    """Speak a line and show it as the current response."""
    status.set_state(STATE_SPEAKING)
    status.set_response(text)
    speak(text)


def startup_diagnostic():
    """Check the mic, calibrate silence and load the speech model."""
    print("\n--- Friday Startup ---")

    config = load_config()
    print(f"  ✅ Config loaded (wake_word: {config['assistant']['wake_word']})")

    device_idx, channels = find_working_mic(sample_rate=16000)
    mic_label = "system default" if device_idx is None else f"device [{device_idx}] ({channels}ch)"
    print(f"  🎙️  Mic: {mic_label}")
    status.set_mic_status(f"✅ {mic_label[:20]}")

    print("  🔇 Calibrating silence (1s)...")
    ambient, threshold = calibrate_silence()
    print(f"     Ambient: {ambient:.1f} | Threshold: {threshold}")
    status.set_calibration(ambient, threshold)
    if ambient > 200:
        print("     ⚠️  High ambient noise")
    elif ambient < 10:
        print("     ⚠️  Very low — check mic")

    print("  🧠 Loading speech model...")
    get_model()
    model_name = config.get("stt", {}).get("model", "base")
    status.set_model(f"whisper-{model_name}")
    print(f"  ✅ Whisper '{model_name}' loaded")

    print("--- Ready ---\n")
    return config


def shutdown():
    """Release the browser and microphone."""
    from friday.browser.controller import close_browser
    from friday.voice.wake_word import close_ww_stream
    for release in (close_browser, close_ww_stream):
        try:
            release()
        except Exception:
            pass


def handle_text(text):
    """Act on one command, whether it was spoken or typed."""
    status.set_heard(text)
    status.set_state(STATE_THINKING)
    process_command(text)
    status.add_history(text, "✅")


def run_voice_loop(greet=True, on_ready=None):
    """Run until stop_requested is set. Safe to call on a background thread.

    on_ready() is called once the mic and speech model are set up.
    """
    startup_diagnostic()
    if on_ready:
        on_ready()

    if greet:
        say(get_greeting())

    ww_model = create_wake_word_detector()
    activated.set()  # go straight to listening after the greeting
    first_activation = True

    while not stop_requested.is_set():
        try:
            status.set_state(STATE_IDLE)

            # Wait for the wake word, or for something else to set `activated`.
            if not first_activation:
                activated.clear()
            while not activated.is_set() and not stop_requested.is_set():
                if listen_for_wake_word_timeout(ww_model, timeout=1.0):
                    activated.set()
            if stop_requested.is_set():
                break

            if first_activation:
                first_activation = False
            else:
                say("Yes boss?")

            # Conversation mode — keep listening for follow-ups until two silences.
            silence_count = 0
            while silence_count < 2 and not stop_requested.is_set():
                status.set_state(STATE_LISTENING)
                text = listen()

                if not text:
                    silence_count += 1
                    if silence_count >= 2:
                        status.set_heard("")
                        status.set_response("")
                        clear_context()
                    continue

                if not _is_meaningful(text):
                    log.info(f"Filtered non-meaningful input: '{text}'")
                    speak("Didn't catch that, boss. Say that again?")
                    time.sleep(0.3)
                    continue

                silence_count = 0
                handle_text(text)
                time.sleep(0.4)  # let the tail of Friday's voice clear the mic

        except OSError as e:
            # Mic disconnected, audio device error, etc.
            log.error(f"Audio device error: {e}")
            status.set_mic_status("❌ disconnected")
            status.set_response("Audio device error. Reconnect mic.")
            speak("I lost the microphone connection. Trying to reconnect.")
            reset_mic_cache()
            time.sleep(3)
        except Exception as e:
            log.error(f"Main loop error: {e}", exc_info=True)
            status.set_response(f"Error: {e}")
            status.add_history("error", f"❌ {str(e)[:30]}")
            speak("I ran into an issue. Let's try again.")
            time.sleep(1)

    shutdown()


def _watch_enter_key():
    """Enter in the terminal works as push-to-talk."""
    if os.name == "nt":
        import msvcrt  # select() only works on sockets on Windows
        while True:
            try:
                if msvcrt.getwch() in ("\r", "\n"):
                    activated.set()
            except Exception:
                pass
    else:
        import select
        while True:
            try:
                if select.select([sys.stdin], [], [], 0.5)[0]:
                    sys.stdin.readline()
                    activated.set()
            except Exception:
                pass


def main():
    """Terminal mode: status screen, Enter to talk, Ctrl+C to quit."""
    from friday.ui.tui import FridayTUI
    tui = FridayTUI()

    def quit_friday(sig=None, frame=None):
        stop_requested.set()
        tui.stop()
        speak(get_farewell())
        shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, quit_friday)
    signal.signal(signal.SIGTERM, quit_friday)

    print("=" * 50)
    print("  FRIDAY — Voice Assistant")
    print("  Say 'Hey Jarvis' or press Enter to talk")
    print("  Press Ctrl+C to exit")
    print("=" * 50)

    status.attach_ui(tui)
    threading.Thread(target=_watch_enter_key, daemon=True).start()
    try:
        run_voice_loop(on_ready=tui.start)
    except KeyboardInterrupt:
        quit_friday()


if __name__ == "__main__":
    main()
