# Friday Assistant — Development Plan

**Goal:** Build a mini Iron Man Friday — a voice-activated AI assistant with a rich terminal UI, conversational AI, and browser automation.

**System:** Acer Aspire A715-76G | i5-12450H (12T) | 7.5GB RAM | GTX 1650 (4GB) | Fedora KDE Wayland

**References:** cybernahx/jarvis-ai-assistant, giri-10/Friday-Voice-Assistant, DawoodTouseef/JARVIS

---

## Architecture

```
"Hey Friday" (Porcupine)
        ↓
  Listen (faster-whisper + Silero VAD)
        ↓
  Intent Parsing (Ollama LLM)
        ↓
     Action Router
  ┌─────────────────────────┐
  │ open website            │ → Playwright
  │ search web              │ → Playwright + Google
  │ interact with page      │ → Playwright (click/type/read)
  │ stocks / news / time    │ → yfinance / feedparser
  │ volume / screenshot     │ → pactl / spectacle
  │ system control          │ → subprocess
  │ conversation / question │ → Ollama LLM response
  └─────────────────────────┘
        ↓
  Speak Response (Piper TTS → PipeWire)
        ↓
  Terminal UI (Rich TUI — animated state display)
```

---

## Tech Stack (Final)

| Layer | Tool | Why |
|-------|------|-----|
| Wake Word | **Porcupine** (Picovoice) | Custom "Hey Friday" trainable, best accuracy, free tier |
| STT | **faster-whisper** (base) | Already working, fast, Silero VAD built-in |
| TTS | **Piper** (ryan-medium) | Free, offline, good quality — ElevenLabs upgrade later |
| LLM Brain | **Ollama** (phi3:mini 3.8B) | Free, local, fits 7.5GB RAM — Claude API upgrade later |
| Terminal UI | **Rich** | Python TUI library — panels, animations, live display |
| Browser | **Playwright** | Full browser control — click, type, scroll, read pages |
| Config | **PyYAML** | Load config.yaml properly |

> **RAM note:** With 7.5GB RAM, we use `phi3:mini` (3.8B, ~2.3GB) instead of llama3.2 (8B, ~4.7GB). GPU offload to GTX 1650 helps.

---

## Phase 0: Fix Critical Bugs (Mic Not Working)

| # | Task | Type | Risk |
|---|------|------|------|
| 0.1 | Create `config_loader.py` — load config.yaml, provide defaults | CODE | LOW |
| 0.2 | Wire config into all modules (listener, speaker, wake_word) | CODE | LOW |
| 0.3 | Fix silence detection — auto-calibrate from 1s ambient noise at startup | CODE | MEDIUM |
| 0.4 | Add mic diagnostic at startup — energy levels, device info, warnings | CODE | LOW |
| 0.5 | End-to-end test: wake → listen → transcribe → command → speak | TEST | LOW |

**Root cause:** `SILENCE_THRESHOLD=500` is hardcoded and likely too high for your mic. Auto-calibration will measure actual ambient noise and set threshold dynamically.

**Success:** Say "Hey Jarvis" → Friday hears you → transcribes → responds.

---

## Phase 1: Terminal UI (Rich TUI)

| # | Task | Type | Risk |
|---|------|------|------|
| 1.1 | Create `tui.py` — TUI engine with `rich.live` | CODE | MEDIUM |
| 1.2 | State machine: IDLE → LISTENING → THINKING → SPEAKING | CODE | LOW |
| 1.3 | Animated pulsing dots `● ● ●` when Friday speaks | CODE | LOW |
| 1.4 | Live mic level bars when listening `▁▂▃▅▇` | CODE | MEDIUM |
| 1.5 | Command history panel (last 10 exchanges) | CODE | LOW |
| 1.6 | Status bar: mic status, model, state, uptime | CODE | LOW |
| 1.7 | Integrate TUI into main.py (replace all print statements) | CODE | MEDIUM |

**Visual:**
```
╭──────────────────────────────────────╮
│         F R I D A Y  v0.2           │
│                                      │
│          ● ● ●  Speaking...         │
│                                      │
│  🎤 "Open YouTube for me"           │
│  🤖 "Opening YouTube, boss."        │
│                                      │
│  ─────── History ───────            │
│  14:32  open youtube → ✅            │
│  14:30  what time → 2:30 PM         │
├──────────────────────────────────────┤
│ MIC ✅ | phi3:mini | IDLE | ↑ 5m    │
╰──────────────────────────────────────╯
```

---

## Phase 2: LLM Integration (Conversational AI)

| # | Task | Type | Risk |
|---|------|------|------|
| 2.1 | Install Ollama + pull phi3:mini model | SETUP | LOW |
| 2.2 | Create `brain.py` — LLM interface with Friday personality system prompt | CODE | MEDIUM |
| 2.3 | Intent classification: command vs conversation | CODE | MEDIUM |
| 2.4 | Short-term conversation memory (last 5 exchanges) | CODE | LOW |
| 2.5 | Update `commands.py` — unknown commands → LLM fallback | CODE | LOW |
| 2.6 | Optional: Claude/Groq API fallback in config | CODE | LOW |

---

## Phase 3: Browser Automation (Playwright)

| # | Task | Type | Risk |
|---|------|------|------|
| 3.1 | Install Playwright + Chromium | SETUP | LOW |
| 3.2 | Create `browser.py` — persistent browser session | CODE | HIGH |
| 3.3 | Voice commands: "open YouTube and search for X" | CODE | MEDIUM |
| 3.4 | Page interaction: click, type, scroll, go back | CODE | HIGH |
| 3.5 | Page reading: extract text → LLM summarize → speak | CODE | MEDIUM |
| 3.6 | LLM-powered element selection (describe what to click) | CODE | HIGH |

**Example commands:**
- *"Open YouTube and search for Iron Man"*
- *"Click the first video"*
- *"Read this page for me"*
- *"Go back"*
- *"Type hello in the search box"*

---

## Phase 4: Polish & Hardening

| # | Task | Type | Risk |
|---|------|------|------|
| 4.1 | Switch wake word to Porcupine + custom "Hey Friday" | CODE | MEDIUM |
| 4.2 | Proper `logging` module (replace print) | CODE | LOW |
| 4.3 | Async audio pipeline (non-blocking TTS) | CODE | HIGH |
| 4.4 | Error recovery (mic disconnect, network loss) | CODE | MEDIUM |
| 4.5 | Push-to-talk keyboard shortcut (Wayland-safe) | CODE | LOW |
| 4.6 | pytest test suite | TEST | MEDIUM |

---

## Phase 5: Future Features

| # | Feature | Details |
|---|---------|---------|
| 5.1 | ElevenLabs TTS upgrade | Most realistic Friday voice (paid) |
| 5.2 | Claude API brain upgrade | Better reasoning (paid) |
| 5.3 | Smart home (Home Assistant) | Lights, thermostat |
| 5.4 | Music control (Spotify) | Play/pause/skip |
| 5.5 | File search | "Find my resume" |
| 5.6 | Email reading | Gmail API |
| 5.7 | Calendar queries | Google Calendar |
| 5.8 | Multi-language | Filipino, Japanese |

---

## MVP = Phase 0 + 1 + 2

A voice assistant that:
- ✅ Hears you reliably (fixed mic)
- ✅ Has a cool animated terminal UI
- ✅ Can hold conversations (LLM brain)
- ✅ Executes real commands (open, search, stocks, news, volume)
- ✅ Speaks with personality (Iron Man Friday)

---

## Dependencies

```bash
# Phase 0-1
pip install rich pyyaml

# Phase 2
curl -fsSL https://ollama.com/install.sh | sh
ollama pull phi3:mini
pip install ollama

# Phase 3
pip install playwright
playwright install chromium

# Phase 4
pip install pvporcupine  # + free API key from console.picovoice.ai
```
