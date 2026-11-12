# Friday — status

Last updated: 2026-11-12. Design: [specs/2026-11-11-friday-desktop-voice-agent-design.md](superpowers/specs/2026-11-11-friday-desktop-voice-agent-design.md)

**Nothing from this work is committed yet.** Commit before continuing.

| # | Phase | State |
|---|---|---|
| 1 | Design document | Done |
| 2 | Clean-up and restructure | Done, two items deferred |
| 3 | Engine | Done, three items deferred |
| 4 | Desktop app | **In progress — blocked** |
| 5 | In-app browser takeover | Not started |
| 6 | Windows installer | Not started |

## Done

### Phase 2 — clean-up and restructure

- Code moved from ~25 root files into the `engine/src/friday/` package
  (`core`, `voice`, `voice/tts`, `llm`, `agent`, `tools`, `browser`, `ui`, `api`).
- `.gitignore` and `.env.example` added. `.env`, `__pycache__`, logs and the Piper voice
  files are untracked; voices now live in `engine/models/piper/`.
- Deleted: `commands_old.py`, `commands.py`, the ElevenLabs code and dependency, the
  Linux-only test scripts, `requirements.txt` (replaced by `engine/pyproject.toml`).
- Old Fedora guides moved to `docs/archive/`. New `README.md`.
- Fixed a bug that predates this work: `tools/web.py` called `get_processing_start`
  without importing it.

### Phase 3 — engine

- **Agent** (`agent/loop.py`): a tool-calling loop. The keyword router still runs
  recognised commands directly; everything else goes to the agent.
- **Tools** (`tools/registry.py`, `tools/builtin.py`): `web_search`, `read_page`,
  `open_website`, `read_current_page`, `launch_app`, `get_time`, `system_status`.
- **Models** (`llm/`): OpenRouter free models, with the local Ollama model as backup.
  Only models priced at zero are called; a rate-limited model rests 60 seconds and the
  next free one is tried. Set with `llm.source` in `engine/config.yaml`.
- **Voice**: Underdog Woof is the default (`tts.provider: woof`), Piper the fallback.
- **API** (`api/app.py`): `python -m friday serve` starts a token-protected FastAPI
  service on 127.0.0.1 with `/health`, `/status`, `/models`, `/command`, `/activate`,
  `/stop`, `/approvals` and a `/ws` event stream (state, voice levels, speech, agent steps).
- **Approvals** (`agent/approvals.py`): answerable by voice or through the API.

### Checked

- `engine`: 105 tests pass (`cd engine && pytest`). Lint has one unused-variable warning in `ui/tui.py`.
- `desktop`: 11 store tests pass, `tsc --noEmit` passes, `vite build` passes.
- Live, on free OpenRouter models: fallback after two rate-limited models; a tool call;
  "how busy is my computer" answered in 6 s; "who won the most recent Formula One race"
  answered correctly in 16 s.
- Live, engine end to end: a typed "what time is it" was spoken through Woof and
  produced 54 level events on the WebSocket.

### Not checked

- **The microphone loop.** Wake word, listening and conversation mode have not been run
  since the restructure. Run `.venv\Scripts\python -m friday` and say a command.
- **The desktop app on screen.** It has never been launched (see the blocker below).

## In progress — Phase 4, desktop app

Written in `desktop/` (Electron 45, React 19, Vite 8, Tailwind 4, TypeScript):

- `electron/main.cjs`: starts the engine with a free port and a random token; widget
  window (frameless, always on top, remembers its position); full window; tray icon;
  a `--smoke` mode that screenshots each screen.
- `electron/preload.cjs`: the only bridge to the page (context-isolated, sandboxed).
- `src/store.ts`, `src/engine.ts`: state built from engine events; WebSocket with reconnect.
- `src/features/`: `Widget`, `Stage` (voice visualiser, caption, activity rail),
  `ApprovalCard`, `HistorySheet` (conversation and typing), `Visualizer` (canvas bars
  driven by real mic and voice levels).
- `src/demo.ts`: fake activity for screenshots (`#/main?demo=speaking|approval|history`).

### Blocker

Windows refuses to run `desktop/node_modules/electron/dist/electron.exe`: "Access is
denied" from PowerShell, `spawn EPERM` from Node. The file is present (249 MB) and
reports as not signed. Cause not yet found. To check, in this order:

1. Run it by hand: `cd desktop; npx electron --version`. If it works in your own
   terminal, the block is only the assistant's sandbox.
2. Windows Security → Protection history, for a blocked or quarantined item.
3. Smart App Control (Windows Security → App & browser control). It blocks unsigned apps.
4. A company policy (AppLocker) on this PC.
5. Reinstall the binary: delete `desktop/node_modules/electron` and run `npm install`.

### Left in this phase

- Launch the app and fix whatever the first real run shows (layout, transparency, sizing).
- Allow the packaged page's origin in the API's CORS rule. Pages loaded from disk send
  `Origin: null`, which `api/app.py` does not accept yet, so typed commands and approval
  buttons will fail in the built app (the event stream is unaffected).
- Settings screen: model source and model, voice, wake-word sensitivity, microphone.
- Store conversation history (SQLite). It is in memory only and lost on restart.
- Global push-to-talk hotkey; "pause listening" in the tray menu.
- Obtain Beautiful UI's real block source. The screens currently imitate its look using
  its colour, font and radius tokens; no repository has been found.

## Not started

### Phase 5 — in-app browser takeover

- Spike: attach Microsoft's Playwright MCP to a Chromium page embedded in the Electron
  window. Fallback if unreliable: Playwright drives its own off-screen Chromium and the
  app shows a live stream of it.
- MCP client in the engine (`friday/mcp/`); MCP tools join the registry.
- Full-window takeover: glowing border, Friday cursor, floating voice bar, Take over / Stop.
- Approval rules decided by the engine: sign-ins, send / buy / delete style buttons,
  payments, uploads and downloads. "Always allow" per site and action.
- Persistent browser profile; passwords typed only by the user.
- Move stock, news, "open X", click / scroll commands from external Brave or Chrome to
  the in-app browser, then delete the external launch path.
- Setting to keep signed-in browsing on the local model only.

### Phase 6 — Windows installer

- Freeze the engine with PyInstaller (folder mode).
- `Friday-Setup-<version>.exe` with electron-builder (NSIS, per-user, unsigned).
- Move config, logs and models to `%APPDATA%\Friday` (one change, in `core/paths.py`).
- First run: download speech, voice and wake-word models with progress; detect Ollama.

## Deferred from finished phases

- One typed settings object in place of `config.get(...)` lookups.
- Module-level globals (`_BROWSER`, cached models, `_agent`) turned into objects.
- `tools/world_monitor.py` appears unused; confirm and delete.
- The terminal status screen (`ui/tui.py`) goes once the desktop app runs.

## Known problems

- **Woof is slow on this PC.** About 1.1× real time: a five-second sentence takes about
  four seconds before speech starts. `tts.provider: piper` is instant.
- **DuckDuckGo blocked searches during testing** (bot check). The agent's `web_search`
  falls back to Google News headlines. The older "search" and "tell me about" commands
  still depend on DuckDuckGo alone.
- **`qwen3:4b` is not downloaded**, so the agent has no local backup. `ollama pull qwen3:4b`.
- **Wake word is still "Hey Jarvis".** "Friday" needs a custom openWakeWord model trained.
- **OpenRouter free tier** has an account-wide daily request cap that switching models
  cannot get around. One agent turn uses 2 to 8 requests.
- **ElevenLabs key** is in pushed git history. It is no longer used; revoke it.

## Later versions

Control of other desktop programs, custom "Friday" wake word, credential vault,
one-click Ollama install, echo cancellation for interrupting by voice on open speakers.
