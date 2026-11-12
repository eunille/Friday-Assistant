"""Text-to-speech: Woof, Kokoro or Piper, all local.

Cross-platform playback via sounddevice.
"""
import io
import os
import threading
import wave
from friday.core.config import get as cfg
from friday.core.events import bus
from friday.core.log import log
from friday.core.paths import MODELS_DIR
from friday.voice.audio import play_wav
from friday.voice.tts import kokoro as speaker_kokoro
from friday.voice.tts import woof as speaker_woof

PIPER_VOICE = None
SPEECH_SPEED = None
_piper_voice_obj = None  # Cached PiperVoice instance (voice_path, PiperVoice)
_speaking_lock = threading.Lock()  # Protects _is_speaking flag only
_playback_lock = threading.Lock()  # Serializes actual audio playback
_is_speaking = False


def _voice():
    return PIPER_VOICE or cfg("tts", "voice") or "en_US-ryan-medium.onnx"


def _speed():
    return SPEECH_SPEED or cfg("tts", "speed") or 1.0


def _provider():
    """Get configured TTS provider: 'woof', 'kokoro', 'piper', or 'auto'."""
    return cfg("tts", "provider") or "auto"


def is_speaking():
    """Check if TTS is currently playing audio.
    Uses non-blocking lock acquisition to avoid deadlock during long audio playback.
    """
    # Try to acquire lock without blocking
    acquired = _speaking_lock.acquire(blocking=False)
    if not acquired:
        # Lock is held by another thread — someone is speaking
        return True
    try:
        return _is_speaking
    finally:
        _speaking_lock.release()


def _get_piper_voice(voice):
    """Load PiperVoice model, cached after first call. Auto-resolves .onnx extension."""
    global _piper_voice_obj
    if _piper_voice_obj is None or _piper_voice_obj[0] != voice:
        from piper import PiperVoice
        model_path = voice if voice.endswith(".onnx") else f"{voice}.onnx"
        if not os.path.isfile(model_path):
            # Bare voice names resolve to the shared models folder.
            model_path = str(MODELS_DIR / "piper" / os.path.basename(model_path))
        config_path = f"{model_path}.json"
        if not os.path.isfile(config_path):
            config_path = None
        _piper_voice_obj = (voice, PiperVoice.load(model_path, config_path=config_path))
    return _piper_voice_obj[1]


def _split_sentences(text, max_words=15):
    """Split text into sentences for F.R.I.D.A.Y.-style clipped delivery.
    
    Args:
        text: Text to split
        max_words: Maximum words per chunk (default 15 for bite-sized delivery)
    
    Returns:
        List of sentence chunks
    """
    import re
    # Split on sentence-ending punctuation followed by whitespace
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    
    # Further split long sentences at commas or conjunctions
    refined = []
    for part in parts:
        words = part.split()
        if len(words) <= max_words:
            refined.append(part)
        else:
            # Split at commas for natural breaks
            comma_parts = re.split(r',\s+', part)
            for cp in comma_parts:
                if len(cp.split()) <= max_words:
                    refined.append(cp)
                else:
                    # Still too long - split at conjunctions (and, but, or)
                    conj_parts = re.split(r'\s+(and|but|or)\s+', cp, flags=re.IGNORECASE)
                    current = ""
                    for i, p in enumerate(conj_parts):
                        if p.lower() in ('and', 'but', 'or'):
                            current += f" {p}"
                        else:
                            if current:
                                refined.append(current.strip())
                            current = p
                    if current:
                        refined.append(current.strip())
    
    # Merge very short fragments (< 3 words) with previous chunk
    merged = []
    for part in refined:
        if merged and len(merged[-1].split()) + len(part.split()) <= max_words and len(part.split()) < 3:
            merged[-1] = merged[-1] + " " + part
        else:
            merged.append(part)
    
    return merged if merged else [text]


def _speak_sync(text, voice, speed):
    """Internal synchronous speak — runs in thread.
    Tries Woof, then Kokoro (each if selected, or already downloaded in 'auto'), then Piper.
    Uses separate locks: _speaking_lock for flag, _playback_lock for audio serialization.
    """
    global _is_speaking

    # Serialize audio playback (only one audio plays at a time)
    with _playback_lock:
        # Set speaking flag (quick operation)
        with _speaking_lock:
            _is_speaking = True
        bus.publish("speech_start", text=text)

        try:
            provider = _provider()
            success = False

            try:
                # Woof (local, numpy only) — provider 'woof', or in 'auto' if downloaded
                if provider == "woof" or (provider == "auto" and speaker_woof.models_present()):
                    success = speaker_woof.speak_woof(text, split=lambda t: _split_sentences(t, max_words=10))
                    if not success:
                        log.warning("Woof failed — falling back")

                # Kokoro (local neural) — provider 'kokoro', or in 'auto' if the
                # model files are already downloaded (no surprise 330 MB download)
                if not success and provider == "kokoro":
                    success = speaker_kokoro.speak_kokoro(text)
                    if not success:
                        log.warning("Kokoro failed — falling back to Piper")
                elif not success and provider == "auto" and speaker_kokoro.models_present():
                    success = speaker_kokoro.speak_kokoro(text)

                # Piper (local, lightweight) — final fallback / provider 'piper'
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
                        buf = io.BytesIO()
                        with wave.open(buf, "wb") as wav_file:
                            piper_voice.synthesize_wav(sentence, wav_file, syn_config=syn_config)
                        buf.seek(0)
                        play_wav(buf)

                    log.info("✓ Piper TTS successful")

            except FileNotFoundError as e:
                log.error(f"Missing dependency: {e}")
            except Exception as e:
                log.error(f"Speech error: {e}")
        finally:
            # Clear speaking flag (quick operation)
            with _speaking_lock:
                _is_speaking = False
            bus.publish("speech_end")


def speak(text, voice=None, speed=None, blocking=True):
    """Convert text to speech and play through the default audio output.

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
