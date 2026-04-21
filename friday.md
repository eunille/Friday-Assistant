# Friday — Your Personal Iron Man Voice Assistant

**Fedora KDE Linux 2026 Build Guide**

---

## Project Goal

Build a hybrid voice assistant named **Friday** that runs on your Fedora KDE desktop — like Tony Stark's Friday.

**"Hey Friday"** → wakes up → listens → replies with personality → executes real actions:

- Open any website or application
- Check live stock prices (Tesla, Apple, etc.)
- Show latest news headlines
- Control volume (up, down, mute)
- Search the web
- Take screenshots
- Basic PC commands

**Hybrid Approach:**

- Voice listening, wake word, and TTS run **locally** (fast & private)
- Internet-dependent tasks (stocks, news, browsing) use the network when needed

---

## How to Use This Guide

1. Follow **one phase at a time** in order
2. Each phase includes: Goal, Steps, Commands, Success Criteria, and Troubleshooting
3. Copy-paste terminal commands exactly in **Konsole**
4. Total estimated time for working MVP: **6–10 hours**

---

## Project Structure

```
~/Friday-Assistant/
├── config.yaml              # All settings, API keys, model paths
├── main.py                  # Entry point — main loop
├── wake_word.py             # Wake word detection (OpenWakeWord)
├── listener.py              # Speech-to-text (faster-whisper + VAD)
├── speaker.py               # Text-to-speech (Piper TTS)
├── commands.py              # Command processor (the brain)
├── personality.py           # Iron Man style responses & templates
├── utils.py                 # Shared helpers (audio, logging, system)
├── models/                  # Downloaded voice & wake word models
│   ├── piper/               # Piper TTS voice model files
│   └── whisper/             # Cached faster-whisper models
├── logs/                    # Runtime logs
├── tests/                   # Unit & integration tests
│   ├── test_wake_word.py
│   ├── test_listener.py
│   ├── test_speaker.py
│   └── test_commands.py
└── venv/                    # Python virtual environment
```

---

## Recommended Tech Stack (Fedora KDE Optimized)

### Local Voice Layer

| Component | Tool | Why |
|-----------|------|-----|
| Wake-word detection | **OpenWakeWord** | Free, open-source (Apache 2.0), no API key, custom trainable |
| Speech-to-Text | **faster-whisper** | Fast local Whisper with built-in Silero VAD |
| Text-to-Speech | **Piper TTS** | Natural neural voices, low resource, fully offline |
| Language | **Python 3.11+** | Native Fedora support |

### Online Task Layer

| Task | Tool | Notes |
|------|------|-------|
| Stock data | **yfinance** | Free, no API key |
| News headlines | **feedparser** (RSS) | No API key needed, parses any RSS feed |
| Browser control | **xdg-open** | Native Fedora/Linux |
| Volume control | **pactl** | PipeWire compatible (default on Fedora KDE) |
| Screenshots | **spectacle** | KDE's built-in screenshot tool |
| App launching | **subprocess** | Launch any installed application |

### Why This Stack Works on Fedora KDE

- All tools install cleanly via pip + dnf
- Native PipeWire audio pipeline (no PulseAudio hacks)
- Wayland-safe (no X11 dependencies)
- OpenWakeWord eliminates proprietary API key requirement

> **Alternative:** If you prefer Porcupine (Picovoice) for wake word detection, it works well too — requires a free API key from [console.picovoice.ai](https://console.picovoice.ai). Install with `pip install pvporcupine`.

---

## Configuration Template

Create `~/Friday-Assistant/config.yaml`:

```yaml
# Friday Assistant Configuration
assistant:
  name: "Friday"
  wake_word: "hey_friday"
  personality: "iron_man"  # witty, confident, helpful

# Speech-to-Text
stt:
  model: "base"            # tiny | base | small | medium | large-v3
  language: "en"
  vad_filter: true          # Silero VAD — detects when you stop speaking
  beam_size: 1              # 1 = fast (greedy), 5 = accurate (beam search)
  silence_timeout: 2.0      # seconds of silence before processing

# Text-to-Speech
tts:
  voice: "en_US-ryan-medium"  # Piper voice model
  speed: 1.0                   # 0.5 = slow, 1.0 = normal, 1.5 = fast

# Wake Word
wake_word:
  engine: "openwakeword"    # openwakeword | porcupine
  sensitivity: 0.5          # 0.0–1.0 (higher = more sensitive, more false positives)
  # porcupine_access_key: ""  # Only if using Porcupine

# Online Services
services:
  news_feeds:
    - "https://feeds.bbci.co.uk/news/rss.xml"
    - "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"
  stock_default_symbols:
    - "TSLA"
    - "AAPL"
    - "GOOGL"

# System
system:
  log_level: "INFO"         # DEBUG | INFO | WARNING | ERROR
  log_file: "logs/friday.log"
  audio_device: null         # null = system default mic
```

---

## Prerequisites (Check Before Starting)

### Hardware Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| RAM | 8 GB | 16 GB |
| CPU | Any x86_64 | Multi-core (4+) |
| GPU | Not required | NVIDIA (for faster Whisper) |
| Microphone | Any USB/built-in | Dedicated USB mic |
| Speakers | Any | Headphones (avoids wake word echo) |

### System Preparation

Open Konsole and run:

```bash
# Update system
sudo dnf update -y

# Verify Fedora version and audio
cat /etc/fedora-release
pactl info | grep "Server Name"
# Expected: PipeWire

# Test microphone access
arecord -d 3 -f cd /tmp/test_mic.wav && aplay /tmp/test_mic.wav
# You should hear your 3-second recording played back
```

**Troubleshooting prerequisites:**

- **No PipeWire?** → `sudo dnf install pipewire pipewire-pulseaudio -y && systemctl --user restart pipewire`
- **No mic sound?** → Check KDE System Settings → Audio → Input Devices → verify correct mic selected
- **Permission denied?** → Add your user to `audio` group: `sudo usermod -aG audio $USER` then log out/in

---

## Phase 1: Project Setup & Environment

**Goal:** Create a clean, isolated project folder and virtual environment.

### Steps

1. Open Konsole

2. Install system dependencies:

```bash
sudo dnf install -y \
  python3-pip \
  python3-devel \
  python3-venv \
  portaudio-devel \
  espeak-ng \
  gcc \
  gcc-c++ \
  spectacle
```

3. Create project directory:

```bash
mkdir -p ~/Friday-Assistant/{models/piper,models/whisper,logs,tests}
cd ~/Friday-Assistant
```

4. Create and activate virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

5. Verify:

```bash
echo $VIRTUAL_ENV
# Should print: /home/<username>/Friday-Assistant/venv
```

### Success Criteria

- `(venv)` appears at the start of your Konsole prompt
- All system packages installed without errors
- Project directory structure exists

### Troubleshooting

- **`python3-venv` not found?** → `sudo dnf install python3-venv -y`
- **`portaudio.h` missing later?** → Verify `portaudio-devel` installed: `rpm -q portaudio-devel`
- **Wrong Python version?** → Check: `python3 --version` (need 3.11+)

---

## Phase 2: Install Dependencies

**Goal:** Install all required Python libraries.

### Steps

1. Ensure venv is active (you see `(venv)` in prompt):

```bash
cd ~/Friday-Assistant && source venv/bin/activate
```

2. Upgrade pip:

```bash
pip install --upgrade pip setuptools wheel
```

3. Install core libraries:

```bash
pip install \
  faster-whisper \
  openwakeword \
  piper-tts \
  pyaudio \
  numpy \
  requests \
  pyyaml \
  psutil \
  yfinance \
  feedparser \
  sounddevice
```

4. Verify all imports work:

```bash
python3 -c "
import faster_whisper
import openwakeword
import pyaudio
import numpy
import yaml
import yfinance
import feedparser
print('All core libraries ready!')
"
```

5. Verify Piper TTS:

```bash
echo "Friday is online and ready to assist." | \
  python3 -m piper --model en_US-ryan-medium --output_file /tmp/test_tts.wav && \
  aplay /tmp/test_tts.wav
```

> **Note:** The first run of Piper will download the voice model (~50 MB). This is expected.

### Success Criteria

- All imports succeed with no errors
- Piper TTS speaks the test sentence through your speakers
- No compilation errors during pip install

### Troubleshooting

- **`pyaudio` build fails?** → Ensure `portaudio-devel` and `gcc` are installed (Phase 1 step 2)
- **`espeak-ng` not found by Piper?** → `sudo dnf install espeak-ng espeak-ng-devel -y`
- **Piper voice download fails?** → Manual download: `python3 -m piper --list-voices` to see available voices

---

## Phase 3: Wake Word Detection

**Goal:** Make Friday wake only when you say "Hey Friday".

### About OpenWakeWord

OpenWakeWord is a free, open-source wake word engine (Apache 2.0 license). It includes pre-trained models and supports custom wake word training — no API key required.

### Steps

1. Test with a built-in wake word first (to verify audio pipeline works):

```bash
cd ~/Friday-Assistant && source venv/bin/activate
```

Create `test_wakeword.py`:

```python
# test_wakeword.py — save this file and run it
import pyaudio
import numpy as np
from openwakeword.model import Model

# Load pre-trained model (downloads on first run)
model = Model(wakeword_models=["hey_jarvis"])

# Audio stream setup
audio = pyaudio.PyAudio()
stream = audio.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=16000,
    input=True,
    frames_per_buffer=1280  # 80ms chunks at 16kHz
)

print("Listening for 'Hey Jarvis'... (say it to test, Ctrl+C to stop)")

try:
    while True:
        audio_data = np.frombuffer(stream.read(1280), dtype=np.int16)
        prediction = model.predict(audio_data)

        for model_name, score in prediction.items():
            if score > 0.5:
                print(f"✅ Wake word detected! (confidence: {score:.2f})")
except KeyboardInterrupt:
    print("\nStopped.")
finally:
    stream.stop_stream()
    stream.close()
    audio.terminate()
```

Run it:

```bash
python3 test_wakeword.py
```

2. Train a custom "Hey Friday" wake word:

> OpenWakeWord supports custom wake word training via Google Colab. Follow these steps:
>
> a. Go to the [OpenWakeWord training notebook](https://github.com/dscripka/openWakeWord#training-new-models)
>
> b. Generate synthetic training clips for "Hey Friday"
>
> c. Train (takes ~30–60 minutes on Colab free tier)
>
> d. Download the resulting `.onnx` model file
>
> e. Place it at `~/Friday-Assistant/models/hey_friday.onnx`

3. Once you have the custom model, create `wake_word.py`:

```python
# wake_word.py
import pyaudio
import numpy as np
from openwakeword.model import Model

WAKE_WORD_MODEL = "models/hey_friday.onnx"  # Custom trained model
SENSITIVITY = 0.5

def create_wake_word_detector():
    """Initialize the wake word detection model."""
    return Model(wakeword_models=[WAKE_WORD_MODEL])

def listen_for_wake_word(model):
    """Block until wake word is detected. Returns confidence score."""
    audio = pyaudio.PyAudio()
    stream = audio.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=16000,
        input=True,
        frames_per_buffer=1280
    )

    try:
        while True:
            audio_data = np.frombuffer(stream.read(1280), dtype=np.int16)
            prediction = model.predict(audio_data)

            for model_name, score in prediction.items():
                if score > SENSITIVITY:
                    return score
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()
```

> **Quick start alternative:** While training a custom model, use `"hey_jarvis"` as a temporary wake word — it's built-in and sounds close enough to "Hey Friday" for testing.

### Success Criteria

- Saying "Hey Jarvis" (or your custom "Hey Friday") prints a detection message
- No false positives during 30 seconds of silence
- Detection latency under 500ms

### Troubleshooting

- **No microphone input?** → `pactl list sources short` to check available mics, then set the correct device in PyAudio
- **Too many false positives?** → Increase sensitivity threshold from 0.5 to 0.7
- **Never triggers?** → Lower sensitivity to 0.3, speak clearly within 1 meter of mic
- **Model download fails?** → Check internet connection; models are ~2 MB each

---

## Phase 4: Speech-to-Text (Listening)

**Goal:** Convert spoken commands into clean text after wake word, with automatic silence detection.

### Key Concept: Voice Activity Detection (VAD)

faster-whisper includes **Silero VAD** built-in. When enabled (`vad_filter=True`), it automatically:

- Detects when you START speaking
- Detects when you STOP speaking (silence timeout)
- Only transcribes actual speech segments

This is critical — without VAD, the assistant wouldn't know when you're done talking.

### Model Size Guide

| Model | Download | RAM Usage | Speed (CPU) | Accuracy | Best For |
|-------|----------|-----------|-------------|----------|----------|
| `tiny` | 39 MB | ~500 MB | Fastest | Good | Quick commands |
| `base` | 140 MB | ~1 GB | Fast | Better | **Recommended start** |
| `small` | 460 MB | ~2 GB | Medium | Great | 16 GB+ RAM |
| `medium` | 1.5 GB | ~5 GB | Slow | Excellent | 32 GB+ RAM |

### Steps

1. Create `listener.py`:

```python
# listener.py
import io
import wave
import pyaudio
import numpy as np
from faster_whisper import WhisperModel

# Model loads once, reused for all transcriptions
STT_MODEL = None

def get_model(model_size="base"):
    """Load Whisper model (cached after first call)."""
    global STT_MODEL
    if STT_MODEL is None:
        print(f"Loading Whisper '{model_size}' model (first run downloads ~140 MB)...")
        STT_MODEL = WhisperModel(
            model_size,
            device="cpu",         # Change to "cuda" if you have NVIDIA GPU
            compute_type="int8"   # Fastest on CPU; use "float16" for GPU
        )
    return STT_MODEL

def record_command(silence_timeout=2.0, max_duration=10.0, sample_rate=16000):
    """Record audio until silence is detected or max duration reached."""
    audio = pyaudio.PyAudio()
    stream = audio.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=sample_rate,
        input=True,
        frames_per_buffer=1024
    )

    frames = []
    silent_chunks = 0
    max_silent = int(silence_timeout * sample_rate / 1024)
    max_chunks = int(max_duration * sample_rate / 1024)

    print("🎤 Listening...")

    try:
        for i in range(max_chunks):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)

            # Simple energy-based silence detection
            audio_array = np.frombuffer(data, dtype=np.int16)
            energy = np.abs(audio_array).mean()

            if energy < 500:  # Silence threshold (adjust per environment)
                silent_chunks += 1
            else:
                silent_chunks = 0

            if silent_chunks > max_silent and len(frames) > max_silent:
                break
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()

    # Convert frames to WAV bytes
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b''.join(frames))
    buf.seek(0)
    return buf

def transcribe(audio_buffer, model_size="base"):
    """Transcribe audio buffer to text using faster-whisper."""
    model = get_model(model_size)
    segments, info = model.transcribe(
        audio_buffer,
        language="en",
        vad_filter=True,         # Silero VAD — filters out non-speech
        beam_size=1              # Greedy decoding — fastest
    )

    text = " ".join(segment.text for segment in segments).strip().lower()
    print(f"📝 Heard: \"{text}\"")
    return text

def listen():
    """Record and transcribe a single command. Returns text."""
    audio = record_command()
    return transcribe(audio)
```

2. Test it:

```bash
python3 -c "
from listener import listen
print('Say something after the beep...')
text = listen()
print(f'You said: {text}')
"
```

### Success Criteria

- Spoken commands appear as accurate lowercase text
- Recording stops automatically after 2 seconds of silence
- Transcription completes in under 3 seconds (base model, CPU)
- No crashes on background noise

### Troubleshooting

- **Slow first run?** → Model download is one-time (~140 MB for base). Subsequent runs are instant.
- **Poor accuracy?** → Upgrade model from `base` to `small` in config.yaml
- **Cuts off too early?** → Increase `silence_timeout` to 3.0 seconds
- **Gibberish output?** → Check mic levels in KDE audio settings, speak closer to mic
- **NVIDIA GPU available?** → Change `device="cuda"`, `compute_type="float16"` for 4x speedup

---

## Phase 5: Text-to-Speech (Friday Speaks)

**Goal:** Give Friday a natural, confident voice using Piper TTS.

### Steps

1. Download and test a voice model:

```bash
cd ~/Friday-Assistant && source venv/bin/activate

# List available voices
python3 -m piper --list-voices 2>/dev/null | grep "en_US" | head -20

# Test the recommended voice
echo "Systems online. Friday at your service, boss." | \
  python3 -m piper --model en_US-ryan-medium --output_file /tmp/friday_test.wav
aplay /tmp/friday_test.wav
```

> **Voice options:** Try `en_US-ryan-medium` (confident male), `en_US-joe-medium` (casual), or `en_US-lessac-medium` (clear female). Pick whichever sounds most "Friday" to you.

2. Create `speaker.py`:

```python
# speaker.py
import subprocess
import tempfile
import os

PIPER_VOICE = "en_US-ryan-medium"
SPEECH_SPEED = 1.0

def speak(text, voice=None, speed=None):
    """Convert text to speech and play it through PipeWire."""
    voice = voice or PIPER_VOICE
    speed = speed or SPEECH_SPEED

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Generate speech with Piper (pipe via stdin to avoid shell injection)
        piper_proc = subprocess.Popen(
            ["python3", "-m", "piper", "--model", voice, "--output_file", tmp_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        piper_proc.communicate(input=text.encode("utf-8"))

        if speed != 1.0:
            # Adjust speed if needed (requires length-scale flag in Piper)
            pass

        # Play through PipeWire/PulseAudio
        subprocess.run(["paplay", tmp_path], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Speech error: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

def speak_greeting():
    """Friday's startup greeting."""
    speak("Systems online. Friday at your service, boss.")

def speak_acknowledgment():
    """Quick acknowledgment while processing."""
    speak("On it.")
```

3. Test:

```bash
python3 -c "
from speaker import speak, speak_greeting
speak_greeting()
speak('The current temperature in Manila is 34 degrees.')
"
```

### Success Criteria

- Friday speaks test sentences clearly through speakers/headphones
- Audio plays without crackling or distortion
- Speech generation completes in under 2 seconds per sentence

### Troubleshooting

- **`paplay` not found?** → `sudo dnf install pulseaudio-utils -y` (works with PipeWire)
- **No sound?** → Check: `pactl list sinks short` — verify default output device
- **Voice model download fails?** → Piper downloads models on first use. Check internet connection.
- **Robotic voice?** → Try a different voice model: `en_US-lessac-medium` or `en_US-joe-medium`

---

## Phase 6: Command Processor (The Brain)

**Goal:** Understand transcribed commands and execute the right actions.

### Command Architecture

```
User speaks → text → Command Processor
                      ├── "open youtube"     → xdg-open https://youtube.com
                      ├── "tesla stock"      → yfinance lookup → speak price
                      ├── "latest news"      → RSS feed parse → speak headlines
                      ├── "volume up"        → pactl set-sink-volume +10%
                      ├── "mute"             → pactl set-sink-mute toggle
                      ├── "take screenshot"  → spectacle --background
                      ├── "search for X"     → xdg-open google search URL
                      └── fallback           → witty "I don't know" response
```

### Steps

1. Create `commands.py`:

```python
# commands.py
import subprocess
import re
import random
from urllib.parse import quote_plus
from datetime import datetime

import yfinance as yf
import feedparser

from speaker import speak

# --- Website shortcuts ---
SITE_MAP = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "reddit": "https://www.reddit.com",
    "twitter": "https://twitter.com",
    "gmail": "https://mail.google.com",
    "netflix": "https://www.netflix.com",
    "spotify": "https://open.spotify.com",
}

NEWS_FEEDS = [
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
]

# --- Command handlers ---

def handle_open(text):
    """Open a website or application."""
    for name, url in SITE_MAP.items():
        if name in text:
            speak(f"Opening {name}, boss.")
            subprocess.Popen(["xdg-open", url])
            return True

    match = re.search(r'open\s+(.+)', text)
    if match:
        target = match.group(1).strip()
        if "." in target:
            url = target if target.startswith("http") else f"https://{target}"
            speak(f"Opening {target}.")
            subprocess.Popen(["xdg-open", url])
            return True
        speak(f"Trying to open {target}.")
        subprocess.Popen(["xdg-open", target])
        return True
    return False

def handle_stock(text):
    """Check stock prices using yfinance."""
    symbols = {
        "tesla": "TSLA", "apple": "AAPL", "google": "GOOGL",
        "amazon": "AMZN", "microsoft": "MSFT", "nvidia": "NVDA",
        "meta": "META", "netflix": "NFLX",
    }

    for name, symbol in symbols.items():
        if name in text:
            try:
                ticker = yf.Ticker(symbol)
                price = ticker.info.get("regularMarketPrice") or ticker.info.get("currentPrice")
                change = ticker.info.get("regularMarketChangePercent", 0)

                if price:
                    direction = "up" if change > 0 else "down"
                    speak(
                        f"{name.title()} is currently at {price:.2f} dollars, "
                        f"{direction} {abs(change):.1f} percent today."
                    )
                else:
                    speak(f"I found {name.title()} but couldn't get the current price. Markets might be closed.")
                return True
            except Exception as e:
                speak(f"Sorry boss, I couldn't fetch {name.title()} stock data right now.")
                print(f"Stock error: {e}")
                return True
    return False

def handle_news(text):
    """Fetch and speak top news headlines from RSS feeds."""
    try:
        headlines = []
        for feed_url in NEWS_FEEDS:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]:
                headlines.append(entry.title)

        if headlines:
            speak(f"Here are the top {min(len(headlines), 5)} headlines.")
            for i, headline in enumerate(headlines[:5], 1):
                speak(f"{i}. {headline}")
        else:
            speak("I couldn't fetch any news right now. Check your internet connection.")
        return True
    except Exception as e:
        speak("Sorry boss, news feeds are unreachable right now.")
        print(f"News error: {e}")
        return True

def handle_volume(text):
    """Control system volume via pactl (PipeWire compatible)."""
    try:
        if "mute" in text or "unmute" in text:
            subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"], check=True)
            speak("Audio toggled.")
            return True
        if "up" in text or "increase" in text or "louder" in text:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"], check=True)
            speak("Volume up.")
            return True
        if "down" in text or "decrease" in text or "lower" in text or "quieter" in text:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"], check=True)
            speak("Volume down.")
            return True
        if "max" in text or "full" in text:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "100%"], check=True)
            speak("Volume at maximum.")
            return True
    except subprocess.CalledProcessError:
        speak("I couldn't adjust the volume.")
    return False

def handle_screenshot(text):
    """Take a screenshot using KDE's Spectacle."""
    try:
        subprocess.Popen(["spectacle", "--background", "--copy-image"])
        speak("Screenshot taken and copied to clipboard.")
        return True
    except FileNotFoundError:
        speak("Spectacle is not installed. Install it with: sudo dnf install spectacle")
        return False

def handle_search(text):
    """Search the web via Google."""
    match = re.search(r'(?:search|google|look up)\s+(?:for\s+)?(.+)', text)
    if match:
        query = match.group(1).strip()
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        speak(f"Searching for {query}.")
        subprocess.Popen(["xdg-open", url])
        return True
    return False

def handle_time(text):
    """Tell the current time."""
    now = datetime.now()
    time_str = now.strftime("%I:%M %p")
    speak(f"It's currently {time_str}.")
    return True

# --- Main dispatcher ---

def process_command(text):
    """Route transcribed text to the correct command handler."""
    if not text or len(text.strip()) < 2:
        return

    text = text.lower().strip()

    # Command routing (order matters — more specific first)
    if any(word in text for word in ["stock", "price", "share", "ticker"]):
        if handle_stock(text):
            return

    if any(word in text for word in ["news", "headlines", "what's happening"]):
        if handle_news(text):
            return

    if any(word in text for word in ["open", "launch", "go to", "navigate"]):
        if handle_open(text):
            return

    if any(word in text for word in ["volume", "louder", "quieter", "mute", "unmute"]):
        if handle_volume(text):
            return

    if any(word in text for word in ["screenshot", "screen shot", "capture screen"]):
        if handle_screenshot(text):
            return

    if any(word in text for word in ["search", "google", "look up"]):
        if handle_search(text):
            return

    if any(word in text for word in ["time", "what time", "clock"]):
        if handle_time(text):
            return

    # Fallback — witty response
    fallback_responses = [
        f"I heard \"{text}\" but I'm not sure what to do with that, boss.",
        "That's above my pay grade. Try something I know — stocks, news, or opening apps.",
        "I didn't catch a command in there. Try saying 'open YouTube' or 'check Tesla stock'.",
    ]
    speak(random.choice(fallback_responses))
```

### Success Criteria

- "check Tesla stock" → speaks current TSLA price
- "open YouTube" → opens YouTube in browser
- "latest news" → speaks 5 news headlines
- "volume up" → increases system volume
- "take a screenshot" → captures screen
- "search for Python tutorials" → opens Google search
- Unknown commands get a witty fallback response

### Troubleshooting

- **Stock data returns None?** → Markets may be closed. yfinance returns last known price during market hours.
- **`xdg-open` does nothing?** → Check default browser: `xdg-settings get default-web-browser`
- **News feeds empty?** → Test feed URL in browser first. Some feeds may be geo-restricted.
- **Volume commands fail?** → Verify PipeWire: `pactl info | grep "Server Name"`

---

## Phase 7: Main Loop & Full Integration

**Goal:** Connect all components into one continuously running assistant.

### Architecture

```
main.py
  │
  ├─ Main Loop (runs forever)
  │    │
  │    ├─ Wake Word Detection (blocking — waits for "Hey Friday")
  │    │
  │    ├─ Acknowledgment speak ("Yes boss?")
  │    │
  │    ├─ Record command (with silence detection)
  │    │
  │    ├─ Transcribe speech → text
  │    │
  │    ├─ Process command → execute action
  │    │
  │    └─ Return to wake word listening
  │
  └─ Signal handler (Ctrl+C → clean shutdown)
```

### Steps

1. Create `main.py`:

```python
#!/usr/bin/env python3
# main.py — Friday Voice Assistant Entry Point

import signal
import sys
import logging
from datetime import datetime

from wake_word import create_wake_word_detector, listen_for_wake_word
from listener import listen
from speaker import speak, speak_greeting
from commands import process_command

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/friday.log"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("friday")

# --- Graceful shutdown ---
running = True

def shutdown_handler(signum, frame):
    global running
    log.info("Shutdown signal received. Goodbye, boss.")
    speak("Going offline. See you next time, boss.")
    running = False
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

# --- Main ---
def main():
    global running

    log.info("=== Friday Voice Assistant Starting ===")
    log.info(f"Start time: {datetime.now().isoformat()}")

    # Initialize wake word detector (loads model once)
    log.info("Loading wake word model...")
    detector = create_wake_word_detector()
    log.info("Wake word model loaded.")

    # Startup greeting
    speak_greeting()
    log.info("Friday is online and listening.")
    print("\nFriday is online. Say 'Hey Friday' to begin.\n")

    while running:
        try:
            # Step 1: Wait for wake word
            confidence = listen_for_wake_word(detector)
            log.info(f"Wake word detected (confidence: {confidence:.2f})")

            # Step 2: Acknowledge
            speak("Yes boss?")

            # Step 3: Listen for command
            command_text = listen()

            if not command_text:
                speak("I didn't catch that. Try again.")
                continue

            log.info(f"Command: '{command_text}'")

            # Step 4: Process command
            process_command(command_text)

        except Exception as e:
            log.error(f"Error in main loop: {e}", exc_info=True)
            continue

    log.info("Friday has shut down.")

if __name__ == "__main__":
    main()
```

2. Run the assistant:

```bash
mkdir -p ~/Friday-Assistant/logs
cd ~/Friday-Assistant && source venv/bin/activate
python3 main.py
```

3. Test the full flow:
   - Wait for "Friday is online" message
   - Say "Hey Friday" (or "Hey Jarvis" if using built-in model)
   - Wait for "Yes boss?"
   - Say a command: "Check Tesla stock" or "Open YouTube"
   - Verify Friday responds and executes the action

### Success Criteria

- Full loop works: wake word → listen → process → speak → back to listening
- Ctrl+C gracefully shuts down with farewell message
- Errors are logged to `logs/friday.log` without crashing
- Multiple consecutive commands work without restart

### Troubleshooting

- **Crashes after wake word?** → Check mic isn't released properly. Verify `listener.py` closes stream in `finally` block.
- **"Yes boss?" overlaps with recording?** → The speak function blocks until audio finishes, so recording starts after.
- **High CPU usage?** → Wake word detection uses ~5% CPU. If higher, check Whisper model isn't loading repeatedly.
- **Logs not writing?** → Ensure `logs/` directory exists.

---

## Phase 8: Polish & Personality

**Goal:** Make Friday feel like a real Iron Man companion.

### Steps

1. Create `personality.py`:

```python
# personality.py — Iron Man style response templates
import random
from datetime import datetime

def get_greeting():
    """Time-aware greeting."""
    hour = datetime.now().hour
    if hour < 12:
        return random.choice([
            "Good morning, boss. Systems are online.",
            "Morning. All systems nominal. What's on the agenda?",
        ])
    elif hour < 18:
        return random.choice([
            "Good afternoon. Friday is at your service.",
            "Afternoon, boss. Ready when you are.",
        ])
    else:
        return random.choice([
            "Good evening, boss. Burning the midnight oil?",
            "Evening. All systems operational. What do you need?",
        ])

def get_acknowledgment():
    """Quick acknowledgments while processing."""
    return random.choice([
        "On it.",
        "Right away, boss.",
        "Working on it.",
        "One moment.",
        "Let me check that for you.",
        "Yes boss?",
    ])

def get_error_response():
    """Witty error responses."""
    return random.choice([
        "Hit a snag, boss. But I'll figure it out.",
        "That didn't work as planned. Want me to try something else?",
        "Even I have my limits. Let's try a different approach.",
        "Technical difficulties. Nothing I can't handle.",
    ])

def get_farewell():
    """Shutdown messages."""
    return random.choice([
        "Going offline. Stay safe, boss.",
        "Shutting down. I'll be here when you need me.",
        "Friday signing off. Don't do anything I wouldn't do.",
    ])

def get_unknown_command(text):
    """Responses for unrecognized commands."""
    return random.choice([
        f"I heard '{text}' but that's not in my playbook yet.",
        "That's beyond my current capabilities. But I'm a fast learner.",
        "Not sure what to do with that one, boss. Try stocks, news, or opening apps.",
        "I'll add that to my to-learn list. For now, try something else.",
    ])
```

2. Improve command accuracy — update keyword matching in `commands.py` with fuzzy alternatives and more synonyms.

3. Test with real daily use cases:

```bash
# Run Friday and test these commands:
# "Hey Friday, what time is it?"
# "Hey Friday, check Apple stock"
# "Hey Friday, open Spotify"
# "Hey Friday, give me the news"
# "Hey Friday, volume down"
# "Hey Friday, take a screenshot"
# "Hey Friday, search for best restaurants near me"
```

### Success Criteria

- Friday responds with varied, personality-driven replies
- Time-aware greetings (morning, afternoon, evening)
- Error responses are helpful, not robotic
- At least 10 consecutive commands work without issues

---

## Phase 9: Autostart on KDE Plasma

**Goal:** Make Friday start automatically when you log into KDE.

### Option A: KDE Autostart (Recommended)

1. Create a launcher script:

```bash
cat > ~/Friday-Assistant/start_friday.sh << 'EOF'
#!/bin/bash
# Friday Voice Assistant Launcher
cd ~/Friday-Assistant
source venv/bin/activate
python3 main.py >> logs/friday.log 2>&1
EOF

chmod +x ~/Friday-Assistant/start_friday.sh
```

2. Create the autostart desktop entry:

```bash
mkdir -p ~/.config/autostart

cat > ~/.config/autostart/friday-assistant.desktop << EOF
[Desktop Entry]
Type=Application
Name=Friday Voice Assistant
Comment=Iron Man style voice assistant
Exec=$HOME/Friday-Assistant/start_friday.sh
Terminal=false
Hidden=false
X-KDE-autostart-after=panel
StartupNotify=false
EOF
```

### Option B: Systemd User Service (More Robust)

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/friday.service << EOF
[Unit]
Description=Friday Voice Assistant
After=pipewire.service

[Service]
Type=simple
WorkingDirectory=$HOME/Friday-Assistant
ExecStart=$HOME/Friday-Assistant/venv/bin/python3 $HOME/Friday-Assistant/main.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

# Enable and start
systemctl --user daemon-reload
systemctl --user enable friday.service
systemctl --user start friday.service

# Check status
systemctl --user status friday.service

# View logs
journalctl --user -u friday.service -f
```

### Success Criteria

- After reboot, Friday starts automatically
- `systemctl --user status friday.service` shows "active (running)"
- Friday responds to wake word without manual start
- Logs are written to `logs/friday.log`

### Troubleshooting

- **Service fails immediately?** → Check: `journalctl --user -u friday.service` for errors
- **Audio not working in service?** → Add `Environment=XDG_RUNTIME_DIR=/run/user/$(id -u)` to service file
- **PipeWire not ready?** → Change `After=pipewire.service` to `After=pipewire.socket`
- **Want to stop?** → `systemctl --user stop friday.service`
- **Want to disable autostart?** → `systemctl --user disable friday.service`

---

## Quick Reference — All Commands

| Say This | Friday Does |
|----------|-------------|
| "Hey Friday" | Wakes up and listens |
| "Open YouTube" | Opens YouTube in browser |
| "Open Gmail" | Opens Gmail |
| "Check Tesla stock" | Speaks current TSLA price |
| "Check Apple stock" | Speaks current AAPL price |
| "Latest news" | Reads top 5 headlines |
| "Volume up" | Increases volume 10% |
| "Volume down" | Decreases volume 10% |
| "Mute" | Toggles mute |
| "Take a screenshot" | Captures screen via Spectacle |
| "Search for Python tutorials" | Opens Google search |
| "What time is it?" | Speaks current time |

---

## Next Steps (Post-MVP)

After you have a working Friday, consider these enhancements:

- **LLM integration** — Connect to a local LLM (Ollama + Llama 3) for free-form conversation
- **Calendar integration** — Read your Google Calendar events
- **Weather** — Speak current weather using OpenWeatherMap API
- **Music control** — Play/pause/skip via Spotify API or `playerctl`
- **Smart home** — Control Home Assistant devices
- **Multi-language** — Add wake word models for other languages
- **GUI overlay** — Transparent KDE widget showing Friday's status




Revision:
flow:
AGENT: Greeting Boss its (current time) what are you up to?
User: I want to know whats happening in finance world today
Agent: Okay boss.....(pause) let me check....

-so while agent is searching after getting all the information datas 
summarize it so ai doesnt just read it raw but understood in summarize it reason with it and discuss to the user easy to understand after that

Agent: Pulling it now for you boss (this is the agent reply when searching and after getting the data and summarizing it and when data is ready)

Agent: Got it boss opening the website/browser (Worldmonitor or any website)
after opening the browser/website now respond with the summarize data

Agent: hmmmmmm based on the $topic boss this is etc etc (disccuss the summarize topic/data ) and his understand about it 


so its really like friday from iron man who talks reason tell her observation about it now just answering my questions
