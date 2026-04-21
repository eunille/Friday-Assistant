# F.R.I.D.A.Y. — Voice Assistant System Documentation

**Version:** 0.2  
**Platform:** Fedora Linux (KDE Plasma / Wayland)  
**Inspired by:** F.R.I.D.A.Y. from the Iron Man / Avengers universe

---

## What Is Friday?

Friday is a fully offline, voice-activated AI assistant that runs on your laptop. You speak a wake word, give a command, and Friday listens, thinks, and responds — all through natural speech. It features a real-time animated terminal UI, a conversational AI brain, and browser automation capabilities.

Think of it as a mini Iron Man AI assistant: witty, helpful, and always ready.

---

## How It Works

### The Voice Pipeline

```
Mic → Wake Word Detection → Speech-to-Text → Command Processor → Text-to-Speech → Speaker
         (OpenWakeWord)       (Whisper)         (Brain + Actions)      (Piper)
```

1. **Wake Word** — Friday continuously listens for "Hey Jarvis" using a lightweight neural network. This runs with minimal CPU and ignores all other sounds.

2. **Listening** — Once activated, Friday records your voice command. It uses energy-based silence detection with auto-calibration to know when you've stopped speaking.

3. **Transcription** — Your speech is converted to text using OpenAI's Whisper model running locally. No audio leaves your machine.

4. **Processing** — The transcribed text is routed to the appropriate handler: website commands, search, volume control, stock prices, news, browser interaction, or the LLM brain for conversational responses.

5. **Response** — Friday speaks back using Piper TTS, a fast neural text-to-speech engine with a natural-sounding male voice.

### The Terminal UI

Friday runs inside a rich terminal interface with:
- **Animated state indicator** — pulsing dots (speaking), waveform bars (listening), spinner (thinking), or a steady dot (idle)
- **Conversation panel** — shows what you said and Friday's response
- **Command history** — timestamped log of all interactions
- **Status bar** — mic status, model info, current state, uptime

---

## What Friday Can Do

### Voice Commands
| Command | Example | What Happens |
|---------|---------|-------------|
| Open websites | "Open YouTube" | Launches Brave browser to the site |
| Search the web | "Search for Python tutorials" | Opens Google with search results |
| Open + Search | "Open YouTube and search for lo-fi music" | Goes to YouTube, types and submits search |
| Stock prices | "What's the Tesla stock price?" | Fetches real-time price via Yahoo Finance |
| News headlines | "Tell me the news" | Reads top 5 headlines from BBC and NYT RSS |
| Volume control | "Volume up" / "Mute" / "Volume down" | Adjusts system volume via PipeWire |
| Screenshot | "Take a screenshot" | Captures screen via KDE Spectacle |
| Current time | "What time is it?" | Speaks the current time |
| Browser actions | "Click on the first video" / "Scroll down" / "Go back" / "Read this page" | Interacts with the open browser |
| Conversation | "What's the meaning of life?" | Responds via the LLM brain with personality |

### Browser Automation
Friday can control a Brave browser window through voice:
- Navigate to any URL
- Search within websites (YouTube, Google, etc.)
- Click elements by visible text
- Scroll up/down
- Go back to previous page
- Read and summarize page content using the LLM

### Conversational AI
When a command isn't recognized, Friday uses an on-device LLM (phi3:mini via Ollama) to have a natural conversation. It maintains a rolling context of the last 5 exchanges and responds in character — concise, warm, and with a touch of Tony Stark's AI assistant personality.

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Speech-to-Text | **faster-whisper** (base model, int8, CPU) | Converts voice to text locally |
| Text-to-Speech | **Piper TTS** (en_US-ryan-medium) | Natural-sounding voice synthesis |
| Audio Playback | **paplay** (PipeWire/PulseAudio) | Plays generated speech |
| Wake Word | **OpenWakeWord** (hey_jarvis model) | Lightweight always-on detection |
| LLM Brain | **Ollama** + phi3:mini (3.8B params) | Conversational AI, page summarization |
| Browser | **Playwright** + Brave Browser | Voice-controlled web automation |
| Terminal UI | **Rich** (Live display, panels, tables) | Animated dashboard interface |
| Audio Input | **PyAudio** via PipeWire | Microphone capture |
| Config | **PyYAML** | Centralized configuration |
| Logging | **Python logging** (RotatingFileHandler) | Debug logs to `logs/friday.log` |
| Audio Detection | Custom energy-based + auto-calibration | Silence/speech boundary detection |

### Hardware Requirements
- **CPU:** Intel i5 or better (tested on i5-12450H)
- **RAM:** 8GB minimum (phi3:mini uses ~2.3GB, Whisper uses ~500MB)
- **GPU:** Not required (all inference runs on CPU with int8 quantization)
- **Microphone:** Built-in laptop mic or external USB mic
- **OS:** Linux with PipeWire audio (Fedora, Ubuntu 22.04+, Arch)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     main.py                             │
│              (Main loop + TUI engine)                   │
│                                                         │
│   ┌──────────┐  ┌───────────┐  ┌────────────────────┐  │
│   │ wake_word│→ │ listener  │→ │    commands.py      │  │
│   │   .py    │  │   .py     │  │  (dispatcher)       │  │
│   └──────────┘  └───────────┘  │                     │  │
│                                │  ┌──────────────┐   │  │
│   ┌──────────┐                 │  │  brain.py    │   │  │
│   │ speaker  │← ─ ─ ─ ─ ─ ─ ─ │  │  (Ollama)    │   │  │
│   │   .py    │                 │  └──────────────┘   │  │
│   └──────────┘                 │  ┌──────────────┐   │  │
│                                │  │  browser.py  │   │  │
│   ┌──────────┐                 │  │  (Playwright)│   │  │
│   │  tui.py  │                 │  └──────────────┘   │  │
│   │  (Rich)  │                 └────────────────────┘  │
│   └──────────┘                                         │
│                                                         │
│   ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │
│   │ config_loader│  │  audio_utils │  │   logger    │  │
│   │     .py      │  │     .py      │  │    .py      │  │
│   └──────────────┘  └──────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### File Overview

| File | Role |
|------|------|
| `main.py` | Entry point, main loop, startup diagnostics, TUI integration |
| `tui.py` | Rich terminal UI with animations, state management, threaded refresh |
| `listener.py` | Mic recording, silence detection, Whisper transcription |
| `speaker.py` | Piper TTS with async/blocking modes, thread-safe |
| `wake_word.py` | OpenWakeWord detection with timeout variant for push-to-talk |
| `commands.py` | Command dispatcher — routes voice commands to handlers |
| `brain.py` | Ollama LLM integration with conversation memory and persona |
| `browser.py` | Playwright browser automation with URL sanitization |
| `config_loader.py` | YAML config loading with deep-merge defaults |
| `audio_utils.py` | Mic detection, ALSA noise suppression, stereo-to-mono |
| `personality.py` | Iron Man-style response templates and greetings |
| `logger.py` | Centralized logging with file rotation |
| `config.yaml` | All configurable settings in one place |

---

## Configuration

All settings live in `config.yaml`:

- **Wake word:** Currently "hey_jarvis" (OpenWakeWord built-in). Sensitivity adjustable (0.0–1.0).
- **STT model:** Whisper base (140MB). Options: tiny (fastest), base, small, medium, large-v3 (most accurate).
- **TTS voice:** Piper en_US-ryan-medium. Speed adjustable.
- **LLM:** Ollama phi3:mini. Can switch to llama3.2 or other Ollama models.
- **Browser:** Brave at `/usr/bin/brave-browser`. Set to `null` for Playwright's built-in Chromium.
- **Audio:** Auto-detects system default mic. Silence calibration runs on startup.

---

## Security Measures

- **URL sanitization** — Only `http://` and `https://` schemes allowed. Blocks `file://`, `javascript:`, and `data:` URIs to prevent local file access or code injection.
- **No shell injection** — Piper TTS receives text via stdin pipe, not shell interpolation.
- **Local-only AI** — All speech recognition and LLM processing runs on-device. No audio or text is sent to external servers.
- **Playwright isolation** — Browser runs in a sandboxed Playwright context.
- **Log rotation** — Prevents log files from filling disk (10MB max, 3 backups).

---

## Known Limitations

1. **Wake word** — "Hey Jarvis" is the closest built-in option. Custom "Hey Friday" requires training a model or using Porcupine with an API key.
2. **RAM pressure** — With Whisper + Ollama + Playwright running, the system uses ~6GB of 7.5GB available. Swap usage is expected.
3. **Wayland restrictions** — Global keyboard shortcuts and `pyautogui` don't work on Wayland. Push-to-talk uses stdin Enter key as alternative.
4. **Single-threaded commands** — Commands execute sequentially. A long LLM response blocks the next wake word detection.
5. **No multi-language support** — STT is configured for English only (configurable in config.yaml).

---

## Future Improvements

### Phase 5 — Planned Enhancements

| Feature | Description | Complexity |
|---------|-------------|------------|
| **Custom Wake Word** | Train "Hey Friday" using Porcupine Console or OpenWakeWord custom training | Medium |
| **ElevenLabs TTS** | Cloud-based premium voice for more natural speech (optional, keeps Piper as fallback) | Low |
| **Claude/GPT API** | Optional cloud LLM for more capable conversations (keeps Ollama as offline fallback) | Low |
| **Smart Home** | Control lights, thermostat via Home Assistant API | Medium |
| **Spotify Control** | Play/pause/skip/search music via Spotify Web API | Medium |
| **File Search** | "Find my tax documents" — search local files by name or content | Medium |
| **Email Integration** | Read unread emails, compose and send via voice | High |
| **Calendar** | Read upcoming events, create new appointments | Medium |
| **Multi-language** | Support for Filipino, Japanese, etc. via Whisper language config | Low |
| **Voice Profiles** | Recognize different users by voice | High |
| **Continuous Listening** | No wake word needed — always processing (privacy trade-off) | Low |
| **Plugin System** | Load custom command handlers from a `plugins/` directory | Medium |
| **GUI Mode** | Optional Electron/Qt desktop widget alongside terminal UI | High |
| **Mobile Companion** | Connect to Friday from phone via local network | High |

### Technical Debt
- Add comprehensive pytest test suite (`tests/` directory is empty)
- Implement interrupt-able TTS (cancel long responses mid-speech)
- Add retry logic for Ollama timeouts
- Persistent conversation memory across sessions (SQLite)
- Proper shutdown cleanup (close browser, stop streams, save state)

---

## How to Run

```bash
cd ~/Friday-Assistant
source venv/bin/activate
python3 main.py
```

**Prerequisites:**
- Python 3.12+ virtual environment with dependencies
- Ollama installed and running (`ollama serve`)
- phi3:mini model pulled (`ollama pull phi3:mini`)
- PipeWire audio system with Digital Microphone as default source
- Brave browser installed at `/usr/bin/brave-browser`

---

*Built with love, caffeine, and a dream of having our own J.A.R.V.I.S.*
