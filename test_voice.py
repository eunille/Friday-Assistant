#!/usr/bin/env python3
# test_voice.py — Test a specific ElevenLabs voice
import os
import sys
from elevenlabs import ElevenLabs

if len(sys.argv) < 2:
    print("Usage: python3 test_voice.py <voice_id>")
    exit(1)

voice_id = sys.argv[1]
api_key = os.getenv("ELEVEN_LABS")

if not api_key:
    print("❌ ELEVEN_LABS env var not set")
    exit(1)

client = ElevenLabs(api_key=api_key)

print(f"Testing voice ID: {voice_id}")

try:
    # Get voice info
    voices = client.voices.get_all()
    voice_info = None
    
    for v in voices.voices:
        if v.voice_id == voice_id:
            voice_info = v
            break
    
    if voice_info:
        print(f"\n✅ Voice found:")
        print(f"  Name: {voice_info.name}")
        print(f"  Category: {getattr(voice_info, 'category', 'unknown')}")
        labels = getattr(voice_info, 'labels', {})
        if labels:
            print(f"  Labels: {labels}")
        
        # Check if it's free
        category = getattr(voice_info, 'category', 'unknown')
        if category in ('premade', 'generated'):
            print(f"  ✅ FREE tier compatible")
        else:
            print(f"  ⚠️  Requires paid plan (category: {category})")
    else:
        print(f"\n❌ Voice ID not found in your account")
        print(f"   This might be a voice from another account or an invalid ID")
        exit(1)
    
    # Try to synthesize test audio
    print(f"\nAttempting synthesis...")
    
    from elevenlabs import VoiceSettings
    import tempfile
    import subprocess
    
    audio_generator = client.text_to_speech.convert(
        text="Hello. This is a test of the ElevenLabs voice system.",
        voice_id=voice_id,
        model_id="eleven_multilingual_v2",
        voice_settings=VoiceSettings(
            stability=0.5,
            similarity_boost=0.75,
            style=0.0,
            use_speaker_boost=True
        ),
        output_format="mp3_44100_128"
    )
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name
        with open(tmp_path, 'wb') as f:
            for chunk in audio_generator:
                if chunk:
                    f.write(chunk)
    
    print(f"✅ Synthesis successful")
    print(f"Playing audio...")
    
    subprocess.run(["paplay", tmp_path], check=True, timeout=30)
    
    os.unlink(tmp_path)
    print(f"\n✅ Voice test complete!")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    exit(1)
