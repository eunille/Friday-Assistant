#!/usr/bin/env python3
# test_friday_voice.py — Test Friday with ElevenLabs voice
import os
import sys

# Load env vars
with open('.env') as f:
    for line in f:
        if line.strip() and not line.startswith('#'):
            key, value = line.strip().split('=', 1)
            os.environ[key] = value

# Import speaker module
from speaker import speak

print("Testing Friday Assistant with ElevenLabs voice...")
print(f"Voice ID: {os.getenv('VOICE')}")
print("\nTest 1: Startup greeting")
speak("Systems online. Friday at your service, boss.")

print("\nTest 2: Status report")
speak("All systems operational. Ready for your commands.")

print("\nTest 3: Personality test")
speak("Alright, boss. Running diagnostics now. That's the latest. You're all caught up.")

print("\n✅ Voice test complete!")
