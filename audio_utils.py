# audio_utils.py — Shared audio device detection for PipeWire/ALSA
import ctypes
import ctypes.util
import pyaudio
import numpy as np

# Suppress ALSA error spam (PipeWire compatibility layer noise)
_ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int,
                                        ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)

def _alsa_error_handler(filename, line, function, err, fmt):
    pass

_c_error_handler = _ERROR_HANDLER_FUNC(_alsa_error_handler)

try:
    _asound = ctypes.cdll.LoadLibrary(ctypes.util.find_library("asound") or "libasound.so.2")
    _asound.snd_lib_error_set_handler(_c_error_handler)
except OSError:
    pass

_CACHED_RESULT = None  # (device_index, channels)


def reset_mic_cache():
    """Clear the cached mic result so next call re-detects."""
    global _CACHED_RESULT
    _CACHED_RESULT = None


def find_working_mic(sample_rate=16000):
    """Find a working microphone. Tries the system default first (best for PipeWire),
    then falls back to scanning individual devices.
    
    Returns (device_index, channels) tuple. device_index=None means system default.
    Result is cached after first successful detection.
    """
    global _CACHED_RESULT
    if _CACHED_RESULT is not None:
        return _CACHED_RESULT

    chunk_size = int(sample_rate * 0.08)  # 80ms chunks

    # Try system default first — PipeWire handles resampling/channel mixing
    audio = pyaudio.PyAudio()
    try:
        stream = audio.open(
            format=pyaudio.paInt16, channels=1, rate=sample_rate,
            input=True, frames_per_buffer=chunk_size,
        )
        stream.read(chunk_size, exception_on_overflow=False)
        stream.stop_stream()
        stream.close()
        _CACHED_RESULT = (None, 1)
        print("🎙️ Using system default mic (PipeWire)")
        return _CACHED_RESULT
    except Exception:
        pass
    finally:
        audio.terminate()

    # Fallback: scan individual devices
    audio = pyaudio.PyAudio()
    try:
        for i in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(i)
            if info["maxInputChannels"] < 1:
                continue
            name = info["name"].lower()
            if any(skip in name for skip in ("monitor", "hdmi", "displayport", "speaker")):
                continue

            for ch in (1, 2):
                if info["maxInputChannels"] < ch:
                    continue
                try:
                    stream = audio.open(
                        format=pyaudio.paInt16, channels=ch, rate=sample_rate,
                        input=True, frames_per_buffer=chunk_size,
                        input_device_index=i,
                    )
                    stream.read(chunk_size, exception_on_overflow=False)
                    stream.stop_stream()
                    stream.close()
                    ch_label = "mono" if ch == 1 else "stereo→mono"
                    _CACHED_RESULT = (i, ch)
                    print(f"🎙️ Using mic device [{i}] ({ch_label})")
                    return _CACHED_RESULT
                except Exception:
                    continue
    finally:
        audio.terminate()

    _CACHED_RESULT = (None, 1)
    print("⚠️ No good mic found — using system default")
    return _CACHED_RESULT


def stereo_to_mono(data):
    """Convert interleaved stereo int16 audio to mono by averaging channels."""
    stereo = np.frombuffer(data, dtype=np.int16)
    mono = stereo.reshape(-1, 2).mean(axis=1).astype(np.int16)
    return mono.tobytes()
