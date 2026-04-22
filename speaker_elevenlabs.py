# speaker_elevenlabs.py — ElevenLabs TTS integration
import os
import subprocess
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
        
        # Generate audio from ElevenLabs API
        audio_generator = _client.text_to_speech.convert(
            text=text,
            voice_id=_voice_id,
            model_id="eleven_multilingual_v2",  # High quality, supports multiple languages
            voice_settings=VoiceSettings(
                stability=stability,
                similarity_boost=similarity_boost,
                style=0.15,  # Slight dramatic flair for AI assistant persona
                use_speaker_boost=True  # Enhance clarity
            ),
            output_format="mp3_44100_128"  # High quality MP3
        )
        
        # Collect all chunks into a temporary MP3 file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
            
        try:
            # Write all audio chunks to file
            with open(tmp_path, 'wb') as f:
                for chunk in audio_generator:
                    if chunk:
                        f.write(chunk)
            
            # Apply F.R.I.D.A.Y. speed adjustment if configured
            playback_path = tmp_path
            friday_speed = _get_friday_speed()
            
            if friday_speed != 1.0:
                log.info(f"Applying F.R.I.D.A.Y. speed: {friday_speed}x")
                speed_path = tmp_path.replace(".mp3", "_speed.mp3")
                
                # Use ffmpeg atempo filter to adjust speed without pitch change
                result = subprocess.run(
                    [
                        "ffmpeg", "-i", tmp_path,
                        "-filter:a", f"atempo={friday_speed}",
                        "-y",  # Overwrite output
                        speed_path
                    ],
                    capture_output=True,
                    timeout=15
                )
                
                if result.returncode == 0 and os.path.exists(speed_path):
                    playback_path = speed_path
                else:
                    log.warning(f"Speed adjustment failed, using normal speed")
            
            # Play MP3 via paplay (supports MP3 natively)
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
            
        finally:
            # Clean up temp files
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            speed_path = tmp_path.replace(".mp3", "_speed.mp3")
            if os.path.exists(speed_path):
                os.unlink(speed_path)
            
    except subprocess.TimeoutExpired:
        log.error("ElevenLabs playback timeout")
        return False
    except Exception as e:
        log.error(f"ElevenLabs TTS failed: {e}")
        return False


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
