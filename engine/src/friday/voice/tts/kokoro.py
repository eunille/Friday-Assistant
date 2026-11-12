"""Kokoro TTS (local neural voice, kokoro-onnx).

High-quality offline TTS. Model files (~330 MB) auto-download on first use.
"""
import os
import numpy as np
from friday.core.log import log
from friday.core.config import get as cfg
from friday.core.paths import MODELS_DIR
from friday.voice.audio import play_pcm

MODEL_DIR = str(MODELS_DIR / "kokoro")
MODEL_PATH = os.path.join(MODEL_DIR, "kokoro-v1.0.onnx")
VOICES_PATH = os.path.join(MODEL_DIR, "voices-v1.0.bin")

_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
MODEL_URL = f"{_RELEASE}/kokoro-v1.0.onnx"
VOICES_URL = f"{_RELEASE}/voices-v1.0.bin"

_kokoro = None


def models_present():
    """True if the Kokoro model files are already downloaded."""
    return os.path.isfile(MODEL_PATH) and os.path.isfile(VOICES_PATH)


def _download(url, dest):
    """Stream-download a file with a simple progress printout."""
    import requests
    tmp = dest + ".part"
    log.info(f"Downloading {url} -> {dest}")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  Kokoro download: {done / 1e6:.0f}/{total / 1e6:.0f} MB", end="")
    print()
    os.replace(tmp, dest)


def download_models():
    """Download Kokoro model + voices (~330 MB total) if missing."""
    os.makedirs(MODEL_DIR, exist_ok=True)
    if not os.path.isfile(MODEL_PATH):
        _download(MODEL_URL, MODEL_PATH)
    if not os.path.isfile(VOICES_PATH):
        _download(VOICES_URL, VOICES_PATH)


def _get_kokoro():
    """Load the Kokoro engine (cached). Downloads model files on first use."""
    global _kokoro
    if _kokoro is None:
        if not models_present():
            print("First run: downloading Kokoro TTS model (~330 MB, one time)...")
            download_models()
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(MODEL_PATH, VOICES_PATH)
        log.info("Kokoro TTS loaded")
    return _kokoro


def is_available():
    """True if kokoro-onnx is importable (models download lazily)."""
    try:
        import kokoro_onnx  # noqa: F401
        return True
    except ImportError:
        return False


def speak_kokoro(text):
    """Synthesize and play text with Kokoro. Returns True on success.

    Voice options (config tts.kokoro_voice): af_heart, af_bella, af_sky,
    bf_emma, bf_isabella (British female — closest to F.R.I.D.A.Y.),
    am_michael, bm_george, and more.
    """
    try:
        kokoro = _get_kokoro()
        voice = cfg("tts", "kokoro_voice") or "af_heart"
        speed = float(cfg("tts", "kokoro_speed") or 1.0)
        samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
        play_pcm(pcm, sample_rate)
        return True
    except Exception as e:
        log.error(f"Kokoro TTS failed: {e}")
        return False


if __name__ == "__main__":
    print("Testing Kokoro TTS...")
    ok = speak_kokoro("Systems online. Kokoro voice ready, boss.")
    print("✅ OK" if ok else "❌ Failed")
