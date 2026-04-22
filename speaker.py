# speaker.py — Text-to-speech using ElevenLabs (primary) or Piper TTS (fallback)
import subprocess
import tempfile
import os
import threading
import wave
from config_loader import get as cfg
from logger import log
import speaker_elevenlabs

PIPER_VOICE = None
SPEECH_SPEED = None
_piper_voice_obj = None  # Cached PiperVoice instance (voice_path, PiperVoice)
_speaking_lock = threading.Lock()
_is_speaking = False


def _voice():
    return PIPER_VOICE or cfg("tts", "voice") or "en_US-ryan-medium.onnx"


def _speed():
    return SPEECH_SPEED or cfg("tts", "speed") or 1.0


def _provider():
    """Get configured TTS provider: 'elevenlabs', 'piper', or 'auto'."""
    return cfg("tts", "provider") or "auto"


def is_speaking():
    """Check if TTS is currently playing audio."""
    with _speaking_lock:
        return _is_speaking


def _get_piper_voice(voice):
    """Load PiperVoice model, cached after first call. Auto-resolves .onnx extension."""
    global _piper_voice_obj
    if _piper_voice_obj is None or _piper_voice_obj[0] != voice:
        from piper import PiperVoice
        model_path = voice
        if not os.path.isfile(model_path) and not model_path.endswith(".onnx"):
            model_path = f"{voice}.onnx"
        config_path = f"{model_path}.json"
        if not os.path.isfile(config_path):
            config_path = None
        _piper_voice_obj = (voice, PiperVoice.load(model_path, config_path=config_path))
    return _piper_voice_obj[1]


def _split_sentences(text):
    """Split text into sentences for reliable TTS synthesis.
    Piper can truncate very long input; chunking prevents this."""
    import re
    # Split on sentence-ending punctuation followed by whitespace
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    # Merge very short fragments back with previous sentence
    merged = []
    for part in parts:
        if merged and len(merged[-1]) < 20:
            merged[-1] = merged[-1] + " " + part
        else:
            merged.append(part)
    return merged if merged else [text]


def _speak_sync(text, voice, speed):
    """Internal synchronous speak — runs in thread.
    Tries ElevenLabs first (if configured), falls back to Piper on failure.
    Lock serializes all speech to prevent overlapping audio."""
    global _is_speaking

    with _speaking_lock:
        _is_speaking = True
        provider = _provider()
        success = False

        try:
            # Try ElevenLabs first (if not explicitly disabled)
            if provider in ("auto", "elevenlabs"):
                log.info("Attempting ElevenLabs TTS...")
                success = speaker_elevenlabs.speak_elevenlabs(text)
                
                if success:
                    log.info("✓ ElevenLabs TTS successful")
                elif provider == "elevenlabs":
                    # User explicitly wants ElevenLabs only — don't fall back
                    log.warning("ElevenLabs failed and provider=elevenlabs — no fallback")
                    return
                else:
                    # Auto mode — fall back to Piper
                    log.warning("ElevenLabs failed — falling back to Piper")
            
            # Use Piper if ElevenLabs failed or provider is "piper"
            if not success:
                log.info("Using Piper TTS...")
                sentences = _split_sentences(text)
                piper_voice = _get_piper_voice(voice)
                from piper.config import SynthesisConfig
                syn_config = SynthesisConfig(
                    length_scale=1.0 / speed if speed != 1.0 else None,
                )

                for sentence in sentences:
                    if not sentence.strip():
                        continue
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                        tmp_path = tmp.name
                    try:
                        with wave.open(tmp_path, "wb") as wav_file:
                            piper_voice.synthesize_wav(sentence, wav_file, syn_config=syn_config)
                        subprocess.run(["paplay", tmp_path], check=True, capture_output=True)
                    finally:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                
                log.info("✓ Piper TTS successful")
                
        except FileNotFoundError as e:
            log.error(f"Missing dependency: {e}")
        except Exception as e:
            log.error(f"Speech error: {e}")
        finally:
            _is_speaking = False


def speak(text, voice=None, speed=None, blocking=True):
    """Convert text to speech and play through PipeWire.
    
    Args:
        blocking: If True (default), waits until speech finishes.
                  If False, returns immediately while audio plays.
    """
    voice = voice or _voice()
    speed = speed or _speed()
    log.info(f"Speaking: {text[:80]}...")

    if blocking:
        _speak_sync(text, voice, speed)
    else:
        thread = threading.Thread(target=_speak_sync, args=(text, voice, speed), daemon=True)
        thread.start()


def speak_greeting():
    """Friday's startup greeting."""
    speak("Systems online. Friday at your service, boss.")


def speak_acknowledgment():
    """Quick acknowledgment while processing."""
    speak("On it.")
