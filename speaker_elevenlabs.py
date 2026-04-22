# speaker_elevenlabs.py — ElevenLabs TTS integration
import os
import subprocess
import tempfile
from typing import Optional
from logger import log

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)  # Override any existing env vars with .env values
except ImportError:
    pass  # dotenv not installed, env vars must be set externally

try:
    from elevenlabs import ElevenLabs, VoiceSettings
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False
    log.warning("elevenlabs package not installed — falling back to Piper")


_client: Optional[ElevenLabs] = None
_voice_id: Optional[str] = None
_initialized = False


def _get_pause_duration() -> int:
    """Get pause duration between sentences in milliseconds (default 150ms)."""
    try:
        from config_loader import get as cfg
        pause = cfg("tts", "sentence_pause_ms")
        if pause is None:
            return 150  # Default: 150ms for F.R.I.D.A.Y. clipped delivery
        return int(pause)
    except Exception:
        return 150


def _init_elevenlabs():
    """Initialize ElevenLabs client with credentials from environment."""
    global _client, _voice_id, _initialized
    
    if _initialized:
        return _client is not None
    
    _initialized = True
    
    if not ELEVENLABS_AVAILABLE:
        return False
    
    api_key = os.getenv("ELEVEN_LABS")
    voice = os.getenv("VOICE")
    
    if not api_key:
        log.warning("ELEVEN_LABS env var not set — ElevenLabs disabled")
        return False
    
    if not voice:
        log.warning("VOICE env var not set — ElevenLabs disabled")
        return False
    
    try:
        _client = ElevenLabs(api_key=api_key)
        _voice_id = voice
        log.info(f"ElevenLabs initialized with voice {_voice_id[:8]}...")
        return True
    except Exception as e:
        log.error(f"Failed to initialize ElevenLabs: {e}")
        _client = None
        _voice_id = None
        return False


def is_available() -> bool:
    """Check if ElevenLabs is available and configured."""
    return _init_elevenlabs()


def _get_friday_speed() -> float:
    """Get F.R.I.D.A.Y. playback speed from config (default 0.9)."""
    try:
        from config_loader import get as cfg
        speed = cfg("tts", "friday_speed")
        if speed is None:
            return 0.9  # Default: 10% slower for AI feel
        return float(speed)
    except Exception:
        return 0.9


def speak_elevenlabs(text: str, stability: float = 0.35, similarity_boost: float = 0.85) -> bool:
    """
    Synthesize speech using ElevenLabs and play via paplay.
    Uses F.R.I.D.A.Y.-style sentence pacing with pauses between sentences.
    
    Args:
        text: Text to synthesize
        stability: Voice stability (0.0-1.0, lower = more natural variation)
                   Default 0.35 for F.R.I.D.A.Y.-style natural AI feel
        similarity_boost: Voice clarity/similarity (0.0-1.0, higher = more consistent)
                          Default 0.85 for consistent AI assistant delivery
    
    Returns:
        True if successful, False if failed (caller should fall back to Piper)
    """
    if not is_available():
        return False
    
    try:
        log.info(f"ElevenLabs synthesizing: {text[:60]}...")
        
        # Split into F.R.I.D.A.Y.-style bite-sized sentences (max 15 words)
        # Import dynamically to avoid circular dependency
        import importlib.util
        spec = importlib.util.find_spec("speaker")
        if spec and spec.loader:
            speaker = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(speaker)
            sentences = speaker._split_sentences(text, max_words=15)
        else:
            # Fallback: simple split if import fails
            import re
            sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        
        log.info(f"Split into {len(sentences)} sentence(s) for clipped delivery")
        
        # Synthesize each sentence and collect audio files
        audio_files = []
        
        for i, sentence in enumerate(sentences):
            if not sentence.strip():
                continue
                
            # Generate audio from ElevenLabs API
            audio_generator = _client.text_to_speech.convert(
                text=sentence,
                voice_id=_voice_id,
                model_id="eleven_multilingual_v2",
                voice_settings=VoiceSettings(
                    stability=stability,
                    similarity_boost=similarity_boost,
                    style=0.15,
                    use_speaker_boost=True
                ),
                output_format="mp3_44100_128"
            )
            
            # Save sentence audio to temp file
            with tempfile.NamedTemporaryFile(suffix=f"_s{i}.mp3", delete=False) as tmp:
                sentence_path = tmp.name
                with open(sentence_path, 'wb') as f:
                    for chunk in audio_generator:
                        if chunk:
                            f.write(chunk)
                audio_files.append(sentence_path)
        
        if not audio_files:
            log.warning("No audio generated")
            return False
        
        # Concatenate all sentences with pauses using ffmpeg
        final_path = tempfile.mktemp(suffix="_final.mp3")
        pause_ms = _get_pause_duration()
        
        if len(audio_files) == 1:
            # Single sentence - no concatenation needed
            final_path = audio_files[0]
        else:
            # Multiple sentences - add pauses between them
            log.info(f"Adding {pause_ms}ms pauses between {len(audio_files)} sentences")
            _concatenate_with_pauses(audio_files, final_path, pause_ms)
        
        # Apply F.R.I.D.A.Y. speed adjustment if configured
        playback_path = final_path
        friday_speed = _get_friday_speed()
        
        if friday_speed != 1.0:
            log.info(f"Applying F.R.I.D.A.Y. speed: {friday_speed}x")
            speed_path = final_path.replace(".mp3", "_speed.mp3")
            
            result = subprocess.run(
                [
                    "ffmpeg", "-i", final_path,
                    "-filter:a", f"atempo={friday_speed}",
                    "-y", speed_path
                ],
                capture_output=True,
                timeout=15
            )
            
            if result.returncode == 0 and os.path.exists(speed_path):
                playback_path = speed_path
            else:
                log.warning(f"Speed adjustment failed, using normal speed")
        
        # Play final audio
        result = subprocess.run(
            ["paplay", playback_path],
            check=True,
            capture_output=True,
            timeout=30
        )
        
        if result.returncode != 0:
            log.warning(f"paplay error (code {result.returncode})")
            return False
        
        log.info("ElevenLabs synthesis complete")
        return True
        
    except subprocess.TimeoutExpired:
        log.error("ElevenLabs playback timeout")
        return False
    except Exception as e:
        log.error(f"ElevenLabs TTS failed: {e}")
        return False
    finally:
        # Clean up temp files
        for f in audio_files if 'audio_files' in locals() else []:
            if os.path.exists(f):
                os.unlink(f)
        if 'final_path' in locals() and os.path.exists(final_path):
            os.unlink(final_path)
        if 'speed_path' in locals() and os.path.exists(speed_path):
            os.unlink(speed_path)


def _concatenate_with_pauses(audio_files: list, output_path: str, pause_ms: int):
    """Concatenate audio files with silence pauses between them using ffmpeg."""
    # Create filter complex for concatenation with silence
    # Format: [0][silence1][1][silence2][2]...concat
    filter_parts = []
    inputs = []
    
    for i, audio_file in enumerate(audio_files):
        inputs.extend(["-i", audio_file])
        filter_parts.append(f"[{i}:a]")
        
        if i < len(audio_files) - 1:
            # Add silence between sentences (except after last one)
            filter_parts.append(f"[silence{i}]")
    
    # Generate silence segments
    silence_filters = []
    for i in range(len(audio_files) - 1):
        silence_filters.append(f"aevalsrc=0:d={pause_ms/1000}[silence{i}]")
    
    # Build concat filter
    concat_filter = "".join(filter_parts) + f"concat=n={len(filter_parts)}:v=0:a=1[out]"
    
    # Combine all filters
    if silence_filters:
        full_filter = ";".join(silence_filters) + ";" + concat_filter
    else:
        full_filter = concat_filter
    
    # Run ffmpeg
    cmd = ["ffmpeg"] + inputs + [
        "-filter_complex", full_filter,
        "-map", "[out]",
        "-y", output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    
    if result.returncode != 0:
        log.error(f"Audio concatenation failed: {result.stderr.decode('utf-8', errors='ignore')}")
        # Fallback: just use first audio file
        import shutil
        shutil.copy(audio_files[0], output_path)


def test_elevenlabs():
    """Test ElevenLabs connection and voice synthesis."""
    if not is_available():
        print("❌ ElevenLabs not available")
        return False
    
    print(f"✅ ElevenLabs configured with voice {_voice_id}")
    print("Testing synthesis...")
    
    success = speak_elevenlabs("This is a test of ElevenLabs text to speech.")
    
    if success:
        print("✅ Test successful")
    else:
        print("❌ Test failed")
    
    return success


if __name__ == "__main__":
    # Run test when executed directly
    test_elevenlabs()
