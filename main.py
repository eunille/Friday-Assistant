# main.py — Friday Voice Assistant entry point
import signal
import sys
import time
import threading

from config_loader import load_config
from wake_word import create_wake_word_detector, listen_for_wake_word, listen_for_wake_word_timeout
from listener import listen, calibrate_silence, get_model
from speaker import speak
from personality import get_greeting, get_farewell
from commands import process_command
from audio_utils import find_working_mic, reset_mic_cache
from context import clear_context
from tui import FridayTUI, STATE_IDLE, STATE_LISTENING, STATE_THINKING, STATE_SPEAKING
from logger import log

# Global TUI instance
tui = FridayTUI()

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


def signal_handler(sig, frame):
    """Graceful shutdown on Ctrl+C or SIGTERM."""
    tui.stop()
    speak(get_farewell())
    
    # Clean up resources
    from browser import close_browser
    from wake_word import close_ww_stream
    try:
        close_browser()
    except Exception:
        pass
    try:
        close_ww_stream()
    except Exception:
        pass
    
    sys.exit(0)


def startup_diagnostic():
    """Run mic and model diagnostics at startup."""
    print("\n--- Friday Startup ---")

    # 1. Load config
    config = load_config()
    print(f"  ✅ Config loaded (wake_word: {config['assistant']['wake_word']})")

    # 2. Detect mic
    device_idx, channels = find_working_mic(sample_rate=16000)
    if device_idx is None:
        mic_label = "system default (PipeWire)"
    else:
        mic_label = f"device [{device_idx}] ({channels}ch)"
    print(f"  🎙️  Mic: {mic_label}")
    tui.set_mic_status(f"✅ {mic_label[:20]}")

    # 3. Calibrate silence threshold
    print("  🔇 Calibrating silence (1s)...")
    ambient, threshold = calibrate_silence()
    print(f"     Ambient: {ambient:.1f} | Threshold: {threshold}")
    tui.set_calibration(ambient, threshold)

    if ambient > 200:
        print("     ⚠️  High ambient noise")
    elif ambient < 10:
        print("     ⚠️  Very low — check mic")

    # 4. Load Whisper model
    print("  🧠 Loading speech model...")
    model = get_model()
    model_name = config.get("stt", {}).get("model", "base")
    tui.set_model(f"whisper-{model_name}")
    print(f"  ✅ Whisper '{model_name}' loaded")

    print("--- Ready ---\n")
    return config


def main():
    """Main loop: wake → listen → process → repeat."""
    # Register signal handlers for clean exit
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("=" * 50)
    print("  FRIDAY — Voice Assistant v0.2")
    print("  Say 'Hey Jarvis' to activate")
    print("  Press Ctrl+C to exit")
    print("=" * 50)

    # Run startup diagnostics (mic check, calibration, model load)
    config = startup_diagnostic()

    # Start TUI
    tui.start()

    # Startup greeting
    greeting = get_greeting()
    tui.set_state(STATE_SPEAKING)
    tui.set_response(greeting)
    speak(greeting)

    # Load wake word model
    ww_model = create_wake_word_detector()

    # Push-to-talk: background thread monitors for Enter key
    _activated = threading.Event()
    _activated.set()  # Skip first wake word — go straight to listening after greeting

    def _keyboard_listener():
        """Listen for Enter key as push-to-talk alternative."""
        import select
        import sys
        while True:
            try:
                if select.select([sys.stdin], [], [], 0.5)[0]:
                    sys.stdin.readline()
                    _activated.set()
            except Exception:
                pass

    kb_thread = threading.Thread(target=_keyboard_listener, daemon=True)
    kb_thread.start()

    _first_activation = True  # Skip "Yes boss?" on first loop (greeting already prompted)

    # Main loop
    while True:
        try:
            tui.set_state(STATE_IDLE)

            # Wait for either wake word or Enter key
            if not _first_activation:
                _activated.clear()
            while not _activated.is_set():
                detected = listen_for_wake_word_timeout(ww_model, timeout=1.0)
                if detected:
                    _activated.set()

            if _first_activation:
                _first_activation = False
            else:
                tui.set_state(STATE_SPEAKING)
                tui.set_response("Yes boss?")
                speak("Yes boss?")

            # Conversation mode — keep listening for follow-ups
            silence_count = 0
            while silence_count < 2:
                tui.set_state(STATE_LISTENING)
                text = listen()

                if text:
                    # Filter gibberish / filler-only transcriptions
                    if not _is_meaningful(text):
                        log.info(f"Filtered non-meaningful input: '{text}'")
                        speak("Didn't catch that, boss. Say that again?")
                        time.sleep(0.3)  # Brief pause before re-listening
                        continue

                    silence_count = 0
                    tui.set_heard(text)
                    tui.set_state(STATE_THINKING)
                    process_command(text)
                    tui.add_history(text, "\u2705")

                    # Brief pause after speaking to prevent mic picking up tail audio
                    time.sleep(0.4)

                    # Stay in conversation mode — listen silently
                    tui.set_state(STATE_LISTENING)
                else:
                    silence_count += 1
                    if silence_count < 2:
                        # First silence — keep listening quietly
                        pass
                    else:
                        # Second silence — exit conversation mode
                        tui.set_heard("")
                        tui.set_response("")
                        clear_context()

        except KeyboardInterrupt:
            signal_handler(None, None)
        except OSError as e:
            # Mic disconnected, audio device error, etc.
            log.error(f"Audio device error: {e}")
            tui.set_mic_status("❌ disconnected")
            tui.set_response("Audio device error. Reconnect mic.")
            speak("I lost the microphone connection. Trying to reconnect.")
            reset_mic_cache()
            time.sleep(3)
            continue
        except Exception as e:
            log.error(f"Main loop error: {e}", exc_info=True)
            tui.set_response(f"Error: {e}")
            tui.add_history("error", f"❌ {str(e)[:30]}")
            speak("I ran into an issue. Let's try again.")
            time.sleep(1)
            continue


if __name__ == "__main__":
    main()
