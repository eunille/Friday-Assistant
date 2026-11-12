"""Speech-to-text using faster-whisper with Silero VAD."""
import io
import wave
import numpy as np
from faster_whisper import WhisperModel
from friday.voice.audio import open_mic_stream, stereo_to_mono
from friday.voice import levels
from friday.core.config import get as cfg
from friday.core.log import log

# Model loads once, reused for all transcriptions
STT_MODEL = None
SAMPLE_RATE = 16000
CHUNK_SIZE = 1024
SILENCE_THRESHOLD = None  # Set dynamically via calibrate_silence()


def calibrate_silence(duration=1.0):
    """Measure ambient noise for 1 second and set silence threshold."""
    global SILENCE_THRESHOLD
    stream = open_mic_stream(sample_rate=SAMPLE_RATE, chunk_size=CHUNK_SIZE)

    energies = []
    num_chunks = int(duration * SAMPLE_RATE / CHUNK_SIZE)
    try:
        for _ in range(num_chunks):
            raw_data = stream.read(CHUNK_SIZE)
            data = stereo_to_mono(raw_data) if stream.channels == 2 else raw_data
            audio_array = np.frombuffer(data, dtype=np.int16)
            energies.append(np.abs(audio_array).mean())
    finally:
        stream.close()

    ambient = np.mean(energies) if energies else 100
    # Threshold = 3x ambient noise (catches speech well above noise floor)
    SILENCE_THRESHOLD = max(int(ambient * 3), 80)
    return ambient, SILENCE_THRESHOLD


def get_model(model_size=None):
    """Load Whisper model (cached after first call)."""
    global STT_MODEL
    model_size = model_size or cfg("stt", "model") or "base"
    if STT_MODEL is None:
        print(f"Loading Whisper '{model_size}' model (first run downloads ~140 MB)...")
        STT_MODEL = WhisperModel(
            model_size,
            device="cpu",       # Change to "cuda" if you have NVIDIA GPU
            compute_type="int8"  # Fastest on CPU; use "float16" for GPU
        )
        print("Whisper model loaded.")
    return STT_MODEL


def record_command(silence_timeout=None, max_duration=10.0):
    """Record audio until silence is detected or max duration reached."""
    silence_timeout = silence_timeout or cfg("stt", "silence_timeout") or 2.0
    stream = open_mic_stream(sample_rate=SAMPLE_RATE, chunk_size=CHUNK_SIZE)

    # Auto-calibrate if not done yet
    if SILENCE_THRESHOLD is None:
        calibrate_silence()

    frames = []
    silent_chunks = 0
    max_silent = int(silence_timeout * SAMPLE_RATE / CHUNK_SIZE)
    max_chunks = int(max_duration * SAMPLE_RATE / CHUNK_SIZE)

    print("🎤 Listening...")

    try:
        for _ in range(max_chunks):
            raw_data = stream.read(CHUNK_SIZE)
            data = stereo_to_mono(raw_data) if stream.channels == 2 else raw_data
            frames.append(data)

            # Simple energy-based silence detection
            audio_array = np.frombuffer(data, dtype=np.int16)
            levels.report("mic", audio_array, SAMPLE_RATE)
            energy = np.abs(audio_array).mean()

            if energy < SILENCE_THRESHOLD:
                silent_chunks += 1
            else:
                silent_chunks = 0

            if silent_chunks > max_silent and len(frames) > max_silent:
                break
    finally:
        stream.close()

    # Convert frames to WAV bytes in-memory
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(frames))
    buf.seek(0)
    return buf


def transcribe(audio_buffer, model_size=None):
    """Transcribe audio buffer to text using faster-whisper."""
    model = get_model(model_size)
    segments, _info = model.transcribe(
        audio_buffer,
        language=cfg("stt", "language") or "en",
        vad_filter=cfg("stt", "vad_filter") if cfg("stt", "vad_filter") is not None else True,
        beam_size=cfg("stt", "beam_size") or 1,
        condition_on_previous_text=False,
        without_timestamps=True,
    )

    text = " ".join(segment.text for segment in segments).strip().lower()
    if text:
        log.info(f'Heard: "{text}"')
    return text


def listen():
    """Record and transcribe a single command. Returns text."""
    audio = record_command()
    return transcribe(audio)
