#!/usr/bin/env python3
"""Mic diagnostic — records 5s, saves WAV, prints energy levels."""
import wave
import numpy as np
import sounddevice as sd

RATE = 16000
DURATION = 5

print(f"Recording {DURATION}s at {RATE}Hz — SPEAK NOW!", flush=True)
print("(Say 'Hey Jarvis' a few times)", flush=True)

recording = sd.rec(int(DURATION * RATE), samplerate=RATE, channels=1, dtype='int16')
sd.wait()
arr = recording.flatten()

# Save to WAV for manual inspection
with wave.open("test_recording.wav", "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(RATE)
    wf.writeframes(arr.tobytes())

print(f"\nSaved to test_recording.wav", flush=True)
print(f"Overall: energy={np.abs(arr).mean():.1f}, peak={np.abs(arr).max()}", flush=True)

# Per-second breakdown
for sec in range(DURATION):
    chunk = arr[sec * RATE:(sec + 1) * RATE]
    e = np.abs(chunk).mean()
    p = np.abs(chunk).max()
    bar = "#" * min(50, int(e / 10))
    print(f"  Second {sec}: energy={e:7.1f} peak={p:6d} {bar}", flush=True)

if np.abs(arr).max() > 500:
    print("\n✅ MIC IS WORKING — speech detected", flush=True)
elif np.abs(arr).max() > 50:
    print("\n⚠️ LOW SIGNAL — mic captures some audio but very quiet", flush=True)
else:
    print("\n❌ NO SPEECH — mic not capturing voice audio", flush=True)
    print("   Try: pactl list sources short  — to check source routing", flush=True)
