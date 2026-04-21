#!/usr/bin/env python3
"""Test parecord-based mic input at 48kHz stereo, downsample to 16kHz mono."""
import subprocess
import numpy as np
import sys

NATIVE_RATE = 48000
TARGET_RATE = 16000
CHANNELS = 2
DURATION = 3
BYTES_NEEDED = NATIVE_RATE * CHANNELS * 2 * DURATION  # 576000

print(f"Recording {DURATION}s via parecord at {NATIVE_RATE}Hz stereo...", flush=True)
print(">>> SPEAK NOW — say 'Hey Jarvis' <<<", flush=True)

proc = subprocess.Popen(
    ["parecord", f"--rate={NATIVE_RATE}", f"--channels={CHANNELS}", "--format=s16le", "--raw"],
    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
)

raw = proc.stdout.read(BYTES_NEEDED)
proc.terminate()
proc.wait()

if len(raw) < BYTES_NEEDED:
    print(f"ERROR: Only got {len(raw)} bytes, expected {BYTES_NEEDED}", flush=True)
    sys.exit(1)

# Convert stereo→mono, 48kHz→16kHz
stereo = np.frombuffer(raw, dtype=np.int16).reshape(-1, 2)
mono48 = stereo.mean(axis=1).astype(np.int16)
# Simple 3:1 decimation (48000/16000=3)
mono16 = mono48[::3]

energy = np.abs(mono16).mean()
peak = int(np.abs(mono16).max())

print(f"\nResult: {len(mono16)} samples at 16kHz mono")
print(f"Energy: {energy:.1f}")
print(f"Peak: {peak}")

for sec in range(DURATION):
    chunk = mono16[sec * TARGET_RATE:(sec + 1) * TARGET_RATE]
    e = np.abs(chunk).mean()
    p = int(np.abs(chunk).max())
    bar = "#" * min(50, int(e / 20))
    print(f"  Sec {sec}: energy={e:7.1f} peak={p:6d} {bar}")

if peak > 500:
    print("\n✅ SPEECH DETECTED — parecord pipeline works!")
elif peak > 50:
    print("\n⚠️ LOW SIGNAL")
else:
    print("\n❌ NO SPEECH")
