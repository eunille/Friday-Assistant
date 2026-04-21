# Friday Assistant — Development Roadmap

**Last Updated:** 2026-04-20
**Current Checkpoint:** Phase 9 Complete ✅

---

## Quick Start

```bash
cd ~/Friday-Assistant
source venv/bin/activate

# Prerequisites (one-time):
# 1. Ollama running with qwen3:4b — `ollama serve` then `ollama pull qwen3:4b`
# 2. Playwright browsers installed — `playwright install`
# 3. Brave browser at /usr/bin/brave-browser

# Run:
python3 main.py
# Say "Hey Jarvis" to activate
# Ctrl+C to exit
```

---

## Completed Phases

### Phase 0 — Foundation ✅
- Mic detection + PipeWire integration
- Config system (config.yaml + config_loader.py)
- ALSA error suppression
- Persistent mic default via WirePlumber

### Phase 1 — Terminal UI ✅
- Rich-based TUI with state machine
- Animated waveform (speaking), bouncing dots (listening), pulsing dot (idle)
- Minimal dark design — no emoji, no panels, centered content
- 8fps smooth animation refresh

### Phase 2 — LLM Brain ✅
- Ollama qwen3:4b integration (brain.py) — upgraded from phi3:mini for better summarization & reasoning
- Qwen3 hybrid mode: /no_think for fast voice responses, thinking mode for deep analysis
- Think-tag stripping for clean TTS output
- Conversation memory (deque, 10 messages)
- Iron Man personality system prompt
- Personality module with dynamic responses

### Phase 3 — Browser Automation ✅
- Playwright + Brave browser integration
- URL sanitization (http/https only)
- Site map shortcuts (YouTube, Google, Reddit, etc.)
- Search, click, scroll, read page, go back
- Browser crash recovery (auto-relaunch)

### Phase 4 — Polish & Hardening ✅
- Async TTS (non-blocking speech)
- Error recovery (mic disconnect, generic errors)
- Push-to-talk (Enter key alternative)
- Rotating file logging (10MB, 3 backups)
- Code review: fixed 3 CRITICAL + 6 HIGH issues
- Conversation mode (follow-up commands without wake word)
- Iron Man style flow: ack → pre-browser → browser → result

---

## Current Phase

### Phase 5 — Dynamic Capabilities ✅
**Goal:** Remove hardcoded limitations, make Friday handle ANY query dynamically.

#### Step 5.1 — Dynamic Stock Lookup ✅
- [x] Expanded from 8 → 60+ companies (tech, finance, consumer, energy, crypto, indices)
- [x] LLM-powered ticker resolver for unknown companies
- [x] Uses brain.classify() — doesn't pollute conversation memory
- [x] Always opens Yahoo Finance + speaks result

#### Step 5.2 — Dynamic News ✅
- [x] Topic-specific news: tech, sports, business, health, entertainment, science, world
- [x] Google News RSS feeds per topic
- [x] Always opens Google News + speaks headlines

#### Step 5.3 — Expanded Command Vocabulary ✅
- [x] Weather queries — wttr.in API (no API key), city extraction, browser visual
- [x] Timer/alarm — threading.Timer, duration parsing, remaining time check, cancel
- [x] System info — psutil for CPU, RAM, battery (targeted or full report)
- [x] App launcher — .desktop file scanning, fuzzy matching (difflib), subprocess launch

---

## Planned Phases

### Phase 6 — LLM Function-Calling Router ✅
**Goal:** Let the LLM decide which tools to use, like ChatGPT's function calling.

- [x] brain.classify() — dedicated classification endpoint (no memory pollution)
- [x] System prompt with tool descriptions for context-aware LLM
- [x] _classify_intent() returns (category, entity) tuple
- [x] _resolve_stock_ticker() uses LLM for unknown company → ticker resolution
- [x] Keyword matching as fast-path, LLM routing as smart fallback
- [x] Unified flow: ack → pre-browser → browser → result

### Phase 7 — Session Memory & Context ✅
**Goal:** Remember conversation context within a session.

- [x] context.py — SessionContext class with thread-safe topic/entity/history tracking
- [x] _classify_intent() injects session context for follow-up resolution
- [x] update_context() wired into all command handlers
- [x] clear_context() called when conversation mode exits (2 silences)
- [x] Follow-up resolution: "check Tesla" → "what about Apple?" → stock|apple via context

### Phase 8 — Web Search & Knowledge ✅
**Goal:** Answer questions Friday can't handle from built-in tools.

- [x] browser.search_and_extract() — Google search with DOM snippet extraction
- [x] handle_knowledge() — feeds snippets to LLM for spoken summary
- [x] LLM _classify_intent() updated with "knowledge" category
- [x] Fallback scraping when structured results unavailable
- [x] Source awareness in LLM prompt

### Phase 9 — 3-Verb Simplification ✅
**Goal:** Strip over-engineered World Monitor and consolidate routing into 3 clean verbs.

- [x] **Check** — look up current data (news, crypto, stocks, weather)
- [x] **Tell me** — knowledge queries (Wikipedia/Google → LLM summary)
- [x] **Compare** — side-by-side comparison (CoinGecko crypto, Google general)
- [x] world_monitor.py rewritten: 552 → 132 lines (single URL scraper, no categories/layers)
- [x] world_handlers.py rewritten: 293 → 30 lines (no sticky session, no menus)
- [x] router.py simplified: 319 → 278 lines (3-verb keyword routing + LLM fallback)
- [x] browser.py cleaned: removed dedicated WM tab (_WM_PAGE + 3 functions)
- [x] New compare_handlers.py: CoinGecko compare for crypto, Google for general
- [x] Total reduction: 1,527 → 878 lines across 5 files (−42%)

### Phase 10 — Custom Wake Word
**Goal:** Use "Hey Friday" instead of "Hey Jarvis".

- [ ] Build recording script for training samples
- [ ] Collect 50-100 "Hey Friday" recordings
- [ ] Train custom OpenWakeWord model
- [ ] Deploy hey_friday.onnx model

### Phase 11 — Advanced Features (Future)
- [ ] Multi-language support
- [ ] Smart home integration (Home Assistant API)
- [ ] Calendar integration
- [ ] Email reading/composing
- [ ] Music playback control (Spotify API)
- [ ] GPU acceleration for Whisper (CUDA)
