#!/usr/bin/env python3
# list_elevenlabs_voices.py — List available ElevenLabs voices
import os
from elevenlabs import ElevenLabs

api_key = os.getenv("ELEVEN_LABS")
if not api_key:
    print("❌ ELEVEN_LABS env var not set")
    exit(1)

client = ElevenLabs(api_key=api_key)

print("Fetching available voices...\n")

try:
    voices = client.voices.get_all()
    
    print(f"Found {len(voices.voices)} voices:\n")
    print(f"{'Name':<20} {'Voice ID':<25} {'Category':<15} {'Labels'}")
    print("=" * 80)
    
    free_voices = []
    
    for voice in voices.voices:
        # Free voices typically have category "premade" or "generated"
        # Library/cloned voices require paid plan
        category = getattr(voice, 'category', 'unknown')
        labels_dict = getattr(voice, 'labels', {})
        labels = ", ".join(f"{k}:{v}" for k, v in labels_dict.items()) if labels_dict else "none"
        
        print(f"{voice.name:<20} {voice.voice_id:<25} {category:<15} {labels}")
        
        if category in ("premade", "generated"):
            free_voices.append((voice.name, voice.voice_id))
    
    print("\n" + "=" * 80)
    print(f"\n✅ {len(free_voices)} FREE voices available (premade/generated):\n")
    
    for name, vid in free_voices:
        print(f"  {name:<20} → {vid}")
    
    print("\nTo use a free voice, update your .env file:")
    print(f"  VOICE=<voice_id>")
    
except Exception as e:
    print(f"❌ Error: {e}")
