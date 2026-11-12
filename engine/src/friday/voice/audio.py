"""Cross-platform audio I/O built on sounddevice (PortAudio).

Works on Windows (WASAPI/MME) and Linux (PipeWire/ALSA) with no system deps.
"""
import threading
import wave
import numpy as np
import sounddevice as sd

from friday.voice import levels

_CACHED_RESULT = None  # (device_index, channels)
_playback_lock = threading.Lock()  # One sound at a time
_stop_requested = threading.Event()


def reset_mic_cache():
    """Clear the cached mic result so next call re-detects."""
    global _CACHED_RESULT
    _CACHED_RESULT = None


def find_working_mic(sample_rate=16000):
    """Find a working microphone. Tries the system default first,
    then falls back to scanning individual input devices.

    Returns (device_index, channels) tuple. device_index=None means system default.
    Result is cached after first successful detection.
    """
    global _CACHED_RESULT
    if _CACHED_RESULT is not None:
        return _CACHED_RESULT

    # Try system default first — host API handles resampling/mixing
    try:
        sd.check_input_settings(samplerate=sample_rate, channels=1, dtype="int16")
        _CACHED_RESULT = (None, 1)
        print("🎙️ Using system default mic")
        return _CACHED_RESULT
    except Exception:
        pass

    # Fallback: scan individual devices
    skip_names = ("monitor", "hdmi", "displayport", "speaker", "output",
                  "loopback", "stereo mix", "virtual")
    try:
        devices = sd.query_devices()
    except Exception:
        devices = []

    for i, info in enumerate(devices):
        if info.get("max_input_channels", 0) < 1:
            continue
        name = info.get("name", "").lower()
        if any(skip in name for skip in skip_names):
            continue
        for ch in (1, 2):
            if info["max_input_channels"] < ch:
                continue
            try:
                sd.check_input_settings(device=i, samplerate=sample_rate,
                                        channels=ch, dtype="int16")
                ch_label = "mono" if ch == 1 else "stereo→mono"
                _CACHED_RESULT = (i, ch)
                print(f"🎙️ Using mic device [{i}] {info['name']} ({ch_label})")
                return _CACHED_RESULT
            except Exception:
                continue

    _CACHED_RESULT = (None, 1)
    print("⚠️ No good mic found — using system default")
    return _CACHED_RESULT


class MicStream:
    """Thin wrapper around sounddevice.RawInputStream with a PyAudio-like
    read(frames) -> bytes interface, so callers stay simple."""

    def __init__(self, sample_rate=16000, chunk_size=1024, device=None, channels=1):
        self.channels = channels
        self._stream = sd.RawInputStream(
            samplerate=sample_rate,
            blocksize=chunk_size,
            device=device,
            channels=channels,
            dtype="int16",
        )
        self._stream.start()

    def read(self, frames):
        """Read `frames` frames as raw int16 bytes (blocks until available)."""
        data, _overflowed = self._stream.read(frames)
        return bytes(data)

    def close(self):
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass


def open_mic_stream(sample_rate=16000, chunk_size=1024):
    """Open a MicStream on the detected working mic."""
    device_idx, channels = find_working_mic(sample_rate=sample_rate)
    return MicStream(sample_rate=sample_rate, chunk_size=chunk_size,
                     device=device_idx, channels=channels)


def stereo_to_mono(data):
    """Convert interleaved stereo int16 audio to mono by averaging channels."""
    stereo = np.frombuffer(data, dtype=np.int16)
    mono = stereo.reshape(-1, 2).mean(axis=1).astype(np.int16)
    return mono.tobytes()


def play_pcm(samples, sample_rate):
    """Play an int16 numpy array through the default output device (blocking).

    Written in short blocks so the visualiser gets live levels and
    stop_playback() takes effect within about 50 ms.
    """
    if samples is None or len(samples) == 0:
        return
    data = np.asarray(samples)
    channels = 1 if data.ndim == 1 else data.shape[1]
    block = max(1, sample_rate // 20)
    with _playback_lock:
        _stop_requested.clear()
        with sd.OutputStream(samplerate=sample_rate, channels=channels, dtype=data.dtype) as out:
            for start in range(0, len(data), block):
                if _stop_requested.is_set():
                    break
                chunk = data[start:start + block]
                levels.report("voice", chunk, sample_rate)
                out.write(chunk)


def play_wav(source):
    """Play a WAV file (path or file-like object) through the default output (blocking)."""
    with wave.open(source, "rb") as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16)
    if channels > 1:
        samples = samples.reshape(-1, channels)
    play_pcm(samples, sample_rate)


def stop_playback():
    """Stop any currently playing audio immediately."""
    _stop_requested.set()
    try:
        sd.stop()
    except Exception:
        pass
