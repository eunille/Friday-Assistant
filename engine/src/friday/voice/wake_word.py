# wake_word.py — OpenWakeWord-based wake word detection (cross-platform, onnx)
import numpy as np
from openwakeword.model import Model
from friday.voice.audio import open_mic_stream, stereo_to_mono
from friday.core.config import get as cfg

SAMPLE_RATE = 16000
CHUNK_SIZE = 1280  # 80ms chunks at 16kHz


def _wake_word_model():
    return cfg("assistant", "wake_word") or "hey_jarvis"


def _sensitivity():
    return cfg("wake_word", "sensitivity") or 0.5


def _score(prediction):
    """Get the score for the configured wake word.
    Matches key prefixes so 'hey_jarvis' also matches 'hey_jarvis_v0.1'."""
    ww = _wake_word_model()
    return max((v for k, v in prediction.items() if k.startswith(ww)), default=0)


def create_wake_word_detector():
    """Initialize the wake word detection model.
    Uses onnx inference (works on Windows and Linux) and downloads the
    pretrained model files on first run."""
    ww = _wake_word_model()
    print(f"Loading wake word model: '{ww}'...")

    try:
        from openwakeword.utils import download_models
        download_models(model_names=[ww])
    except Exception:
        pass  # Already downloaded or offline — Model() errors if truly missing

    try:
        model = Model(wakeword_models=[ww], inference_framework="onnx")
    except Exception:
        # Older openwakeword versions / tflite systems
        model = Model(wakeword_models=[ww])

    print("Wake word model loaded. Available:", list(model.models.keys()))
    return model


def listen_for_wake_word(model):
    """Block until wake word is detected. Returns confidence score."""
    stream = open_mic_stream(sample_rate=SAMPLE_RATE, chunk_size=CHUNK_SIZE)
    try:
        while True:
            raw_data = stream.read(CHUNK_SIZE)
            if stream.channels == 2:
                raw_data = stereo_to_mono(raw_data)
            audio_data = np.frombuffer(raw_data, dtype=np.int16)
            prediction = model.predict(audio_data)

            score = _score(prediction)
            if score > _sensitivity():
                return score
    finally:
        stream.close()


def listen_for_wake_word_timeout(model, timeout=1.0):
    """Listen for wake word for up to `timeout` seconds. Returns score or None.

    Reuses a module-level audio stream to avoid resource leaks.
    """
    import time as _time

    _ensure_ww_stream()

    deadline = _time.monotonic() + timeout
    try:
        while _time.monotonic() < deadline:
            raw_data = _ww_stream.read(CHUNK_SIZE)
            if _ww_stream.channels == 2:
                raw_data = stereo_to_mono(raw_data)
            audio_data = np.frombuffer(raw_data, dtype=np.int16)
            prediction = model.predict(audio_data)

            score = _score(prediction)
            if score > _sensitivity():
                return score
        return None
    except OSError:
        # Mic disconnected — reset stream for next call
        close_ww_stream()
        raise


# Module-level reusable audio stream for wake word detection
_ww_stream = None


def _ensure_ww_stream():
    """Create the wake word audio stream if it doesn't exist."""
    global _ww_stream
    if _ww_stream is None:
        _ww_stream = open_mic_stream(sample_rate=SAMPLE_RATE, chunk_size=CHUNK_SIZE)


def close_ww_stream():
    """Close the reusable wake word stream."""
    global _ww_stream
    if _ww_stream:
        _ww_stream.close()
        _ww_stream = None
