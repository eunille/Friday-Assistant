# wake_word.py — OpenWakeWord-based wake word detection
import pyaudio
import numpy as np
from openwakeword.model import Model
from audio_utils import find_working_mic, stereo_to_mono
from config_loader import get as cfg

SAMPLE_RATE = 16000
CHUNK_SIZE = 1280  # 80ms chunks at 16kHz


def _wake_word_model():
    return cfg("assistant", "wake_word") or "hey_jarvis"


def _sensitivity():
    return cfg("wake_word", "sensitivity") or 0.5


def create_wake_word_detector():
    """Initialize the wake word detection model."""
    ww = _wake_word_model()
    print(f"Loading wake word model: '{ww}'...")
    model = Model()
    print("Wake word model loaded. Available:", list(model.models.keys()))
    return model


def listen_for_wake_word(model):
    """Block until wake word is detected. Returns confidence score."""
    device_idx, channels = find_working_mic(sample_rate=SAMPLE_RATE)
    audio = pyaudio.PyAudio()
    stream_kwargs = dict(
        format=pyaudio.paInt16,
        channels=channels,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
    )
    if device_idx is not None:
        stream_kwargs["input_device_index"] = device_idx
    stream = audio.open(**stream_kwargs)

    try:
        while True:
            raw_data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            if channels == 2:
                raw_data = stereo_to_mono(raw_data)
            audio_data = np.frombuffer(raw_data, dtype=np.int16)
            prediction = model.predict(audio_data)

            ww = _wake_word_model()
            score = prediction.get(ww, 0)
            if score > _sensitivity():
                return score
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()


def listen_for_wake_word_timeout(model, timeout=1.0):
    """Listen for wake word for up to `timeout` seconds. Returns score or None.
    
    Reuses a module-level audio stream to avoid resource leaks.
    """
    import time as _time

    _ensure_ww_stream()

    deadline = _time.monotonic() + timeout
    try:
        while _time.monotonic() < deadline:
            raw_data = _ww_stream.read(CHUNK_SIZE, exception_on_overflow=False)
            if _ww_channels == 2:
                raw_data = stereo_to_mono(raw_data)
            audio_data = np.frombuffer(raw_data, dtype=np.int16)
            prediction = model.predict(audio_data)

            ww = _wake_word_model()
            score = prediction.get(ww, 0)
            if score > _sensitivity():
                return score
        return None
    except OSError:
        # Mic disconnected — reset stream for next call
        close_ww_stream()
        raise


# Module-level reusable audio stream for wake word detection
_ww_audio = None
_ww_stream = None
_ww_channels = 1


def _ensure_ww_stream():
    """Create the wake word audio stream if it doesn't exist."""
    global _ww_audio, _ww_stream, _ww_channels

    if _ww_stream is not None:
        return

    device_idx, channels = find_working_mic(sample_rate=SAMPLE_RATE)
    _ww_channels = channels
    _ww_audio = pyaudio.PyAudio()
    stream_kwargs = dict(
        format=pyaudio.paInt16,
        channels=channels,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
    )
    if device_idx is not None:
        stream_kwargs["input_device_index"] = device_idx
    _ww_stream = _ww_audio.open(**stream_kwargs)


def close_ww_stream():
    """Close the reusable wake word stream."""
    global _ww_audio, _ww_stream
    if _ww_stream:
        _ww_stream.stop_stream()
        _ww_stream.close()
        _ww_stream = None
    if _ww_audio:
        _ww_audio.terminate()
        _ww_audio = None
