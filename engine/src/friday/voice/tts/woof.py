"""Underdog Woof TTS (local, numpy only, ~41 MB).

Licence: non-commercial, and the app must credit "Voice by Underdog Woof".

On a laptop CPU Woof generates speech at roughly the speed it is spoken, so a
sentence is synthesised on a worker thread while the previous one plays.
"""
import queue
import sys
import threading

import numpy as np

from friday.core.config import get as cfg
from friday.core.log import log
from friday.core.paths import MODELS_DIR
from friday.voice.audio import play_pcm

REPO = "ConwayResearch/Underdog-Woof"
MODEL_DIR = MODELS_DIR / "woof"
SAMPLE_RATE = 24000
VOICES = ("juno", "mira")
CREDIT = "Voice by Underdog Woof"

_tts = None  # (voice name, Woof instance)
_lock = threading.Lock()


def models_present():
    return (MODEL_DIR / "woof_int8.npz").is_file() and (MODEL_DIR / "underdog_woof").is_dir()


def download():
    """Fetch the model and its small Python runtime (about 45 MB, once)."""
    from huggingface_hub import snapshot_download
    log.info(f"Downloading {REPO} to {MODEL_DIR}")
    snapshot_download(REPO, local_dir=str(MODEL_DIR),
                      allow_patterns=["*.npz", "underdog_woof/*", "LICENSE", "NOTICE"])


def _voice():
    voice = (cfg("tts", "woof_voice") or "juno").lower()
    return voice if voice in VOICES else "juno"


def _get():
    global _tts
    with _lock:
        voice = _voice()
        if _tts is None or _tts[0] != voice:
            if not models_present():
                download()
            if str(MODEL_DIR) not in sys.path:
                sys.path.insert(0, str(MODEL_DIR))
            from underdog_woof import Woof
            _tts = (voice, Woof(voice=voice))
        return _tts[1]


def to_int16(audio):
    """Woof's float32 [-1, 1] audio -> int16 for playback."""
    return (np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0) * 32767).astype(np.int16)


def speak_woof(text, split=None, play=play_pcm) -> bool:
    """Speak text. Returns False if Woof couldn't be used, so the caller can fall back."""
    try:
        tts = _get()
    except Exception as e:
        log.error(f"Woof unavailable: {e}")
        return False

    sentences = [s for s in (split(text) if split else [text]) if s.strip()]
    if not sentences:
        return True

    ready = queue.Queue(maxsize=2)

    def synthesise():
        try:
            for sentence in sentences:
                ready.put(to_int16(tts(sentence, seed=0)))
        except Exception as e:
            log.error(f"Woof synthesis failed: {e}")
            ready.put(e)
        ready.put(None)

    threading.Thread(target=synthesise, daemon=True).start()
    spoke_something = False
    while True:
        item = ready.get()
        if item is None:
            return True
        if isinstance(item, Exception):
            return spoke_something  # fall back only if nothing was said yet
        play(item, SAMPLE_RATE)
        spoke_something = True
