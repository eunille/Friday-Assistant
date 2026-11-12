# Friday

A voice assistant for your PC. Say the wake word, talk, and Friday answers out loud and
does things for you: opens sites and apps, checks stocks, crypto, news and weather, reads
and summarises pages, sets timers, and controls volume.

Friday is being rebuilt from a terminal program into a Windows desktop app. The design is
in [docs/superpowers/specs](docs/superpowers/specs/2026-11-11-friday-desktop-voice-agent-design.md).

| Phase | What | Status |
|---|---|---|
| 2 | Clean repository, Python package, tests | done |
| 3 | Engine: FastAPI service, tool-calling agent, local or OpenRouter free models, Woof voice | next |
| 4 | Desktop app: widget, voice stage, dialogs | planned |
| 5 | In-app browser Friday drives | planned |
| 6 | Windows installer | planned |

## Run it (terminal, for now)

Needs Python 3.12 or newer, a microphone, and [Ollama](https://ollama.com) for the local
model.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e "engine[dev]"
playwright install chromium        # only if you have no Brave or Chrome
ollama pull qwen3:1.7b
python -m friday
```

Say **"Hey Jarvis"** (the wake word until a custom "Friday" one is trained) or press
Enter, then speak.

### Voices

Friday speaks with Piper by default. Download a voice once:

```bash
python -m piper.download_voices en_US-ryan-medium --data-dir engine/models/piper
```

Set `tts.provider: kokoro` in `engine/config.yaml` for the higher-quality Kokoro voice; it
downloads about 330 MB on first use.

## Settings

Everything is in [`engine/config.yaml`](engine/config.yaml): wake word, speech model,
voice, local model, browser, site shortcuts, stock and crypto names.

Secrets go in `.env` at the repository root (copy `.env.example`). It is never committed.

## Layout

```
engine/                  Python engine
  config.yaml            settings
  src/friday/
    app.py               terminal entry point and main loop
    core/                config, logging, file locations
    voice/               microphone, wake word, speech-to-text
      tts/               speaking: Kokoro, Piper
    llm/                 local model (Ollama)
    agent/               command router, conversation context, personality
    tools/               what Friday can do: finance, news, weather, web, system, timers
    browser/             Playwright browser control
    ui/                  terminal status screen
  tests/
  scripts/               check_mic.py
  models/                downloaded voices (not committed)
docs/                    design, and archive/ for the old Fedora-era guides
```

## Develop

```bash
cd engine
pytest          # tests need no microphone, network or model
ruff check src
```
