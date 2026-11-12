# Friday desktop voice agent — design

Date: 2026-11-11
Status: awaiting owner approval

## 1. Intent

Friday today is a terminal-only Python voice assistant: wake word, speech-to-text, a keyword
router, about fifteen skills, a Playwright browser and three TTS providers, in ~25 flat files.

The owner wants it rebuilt as a **downloadable Windows desktop app** that feels like Friday
from Iron Man: you say "Friday", it listens, talks back, and does work for you — most of it in
a browser you can watch it drive. The code must become maintainable and conventional, because
the current layout and keyword routing cannot grow into that.

Voice is the product. Chat, text and windows exist to support the voice, not the reverse.

## 2. Goals

1. A Windows installer (`.exe`) that a non-technical person can download and run, as the
   owner's earlier project Ember does.
2. One app in two shapes: a small always-on-top **widget** showing live voice frequency, and
   an expandable **full view**.
3. Wake word activates listening hands-free; conversation continues without repeating it.
4. An **agent** that picks tools itself, replacing the keyword list, so open-ended requests
   ("open GitHub and tell me what's new in my notifications") work.
5. A **browser inside the app** that Friday visibly drives, full-window, with the user able to
   take over and hand back.
6. Model choice: a **local model** (Ollama) or **OpenRouter free models**, with automatic
   switching between free models when one is rate-limited.
7. Underdog Woof as the default voice.
8. A maintainable codebase: package layout, typed settings, tests, lint, clean git.

## 3. Non-goals (this version)

- Controlling other desktop programs by clicking inside them (File Explorer, VS Code,
  Spotify). Existing app launch, volume, screenshot and timer commands stay. Planned next.
- Docker. A container cannot reach the Windows mic, speakers or desktop. Not used.
- macOS and Linux installers. The engine should not gain new Windows-only assumptions
  beyond what exists, but only Windows is built and tested.
- Accounts, multi-user, cloud sync, mobile.
- A password vault. See 7.5.
- One-click Ollama install from inside the app (Ember has this; later).
- Training the custom "Friday" wake-word model (see 7.1).

## 4. Anti-goals

- **Never spend money silently.** With OpenRouter, only models priced at zero are ever
  called. Fallback goes free → free, never to a paid model, even if the key could pay.
- **Never act irreversibly without a yes.** Signing in, submitting forms that send, buy,
  post or delete, and anything outside the browser that changes the system beyond volume
  require spoken or clicked approval.
- **The model never sees passwords.**
- **It must not turn into a chat app.** No permanent chat log on the main screen.
- **No regression in what works today.** Every current skill still works by voice after the
  restructure.

## 5. Constraints

- Target PC: 16 GB RAM, Intel Iris Xe, no dedicated GPU. Everything local runs on CPU.
- Installed: Python 3.12 on PATH, Ollama 0.30.0 with `qwen3:1.7b` only. The existing
  `.venv` was made with Python 3.14 and is recreated on 3.12.
- `.env` holds `ELEVEN_LABS`, `VOICE`, `OPENROUTER`. Only `OPENROUTER` is used from now on.
- Underdog Woof licence is **non-commercial** and requires the credit "Voice by Underdog
  Woof" in the app. Friday is a personal project; if that changes, the voice must change.
- Beautiful UI (beautifului.dev) is MIT, React + Tailwind 4, copy-paste source, no npm
  package. The site does not link a repository; where its source is obtained is unresolved
  (see 10).

## 6. What the owner decided

- Voice first; chat optional and hidden by default.
- Widget with a frequency visual, expandable to a full view.
- Use Beautiful UI's blocks and look; do not design from scratch.
- When Friday browses, the browser opens **inside the app, full screen**, and should feel
  like Friday is really controlling the PC.
- Approvals and questions appear as a **dialog card** only when needed; the main screen
  otherwise stays clean. History is available on demand.
- Local model **or** OpenRouter; OpenRouter uses **free models only**, switching to another
  free model automatically when one hits its limit.
- Underdog Woof for TTS. ElevenLabs is no longer used and is removed.
- Browser only for now; other desktop programs later.
- FastAPI for the backend; an `.exe` like Ember.

Everything in section 7 not listed above is the designer's call and is open to overrule.

## 7. Design

### 7.1 Shape of the system

Two processes on the user's PC:

- **Engine** — Python. Owns the microphone, speakers, wake word, speech-to-text, TTS, the
  agent, tools and model calls. Exposes a FastAPI app on `127.0.0.1` on a free port,
  protected by a random per-launch token.
- **Desktop app** — Electron + React + Vite + Tailwind 4. Owns the windows, tray icon and
  the in-app browser. Starts the engine as a child process, passes it the token, and stops
  it on quit.

They talk over one WebSocket (events both ways) plus a few REST routes (settings, models,
history, health). Audio never crosses this link; only levels and text do.

Electron is chosen over Tauri because it can host and remote-control a real Chromium page
inside its own window, and the owner already ships Ember with it.

**Wake word.** Stays `hey_jarvis` (openWakeWord built-in) until a custom "Friday" model is
trained. The wake-word model path is a setting, so dropping in a trained `hey_friday.onnx`
needs no code change. Space bar (when the app is focused) and a global hotkey are
push-to-talk alternatives.

### 7.2 Repository layout

```
Friday-Assistant/
├── engine/                      Python package
│   ├── pyproject.toml           deps, ruff, pytest config; Python 3.12
│   ├── src/friday/
│   │   ├── api/                 FastAPI app, routes, WebSocket, pydantic schemas
│   │   ├── core/                settings, logging, event bus, user-data paths
│   │   ├── voice/               audio I/O, wake word, STT, pipeline state machine
│   │   │   └── tts/             base interface + woof, kokoro, piper
│   │   ├── llm/                 provider interface + ollama, openrouter, fallback chain
│   │   ├── agent/               tool-calling loop, prompts, memory, approvals, fast path
│   │   ├── tools/               registry + finance, news, weather, web, system,
│   │   │                        timers, world_monitor, compare
│   │   ├── mcp/                 MCP client and server config
│   │   └── storage/             SQLite: history, settings, approvals
│   └── tests/
├── desktop/                     Electron app
│   ├── electron/                main process: windows, tray, engine child, browser view
│   └── src/
│       ├── features/            widget, stage, dialogs, history, takeover, settings
│       ├── components/ui/       Beautiful UI blocks (copied in)
│       └── lib/                 engine client (WebSocket + REST), state
├── docs/
└── scripts/                     dev and build helpers
```

Removed: `commands_old.py`, `commands.py` shim, `tui.py`, root test scripts (replaced by
real tests or moved to `scripts/`), `friday.md`/`FRIDAY.md`/`plan.md`/`ROADMAP.md`/
`SYSTEM.md` (Fedora-era; replaced by a new README).

Git: add `.gitignore`; stop tracking `.env`, `__pycache__/`, `logs/`, `*.onnx`,
`test_recording.wav`, `.superpowers/`. Add `.env.example`. History is **not** rewritten.
The ElevenLabs key in pushed history is no longer used; the owner should still revoke it
on the ElevenLabs site so it cannot be used by anyone else.

### 7.3 Engine

**Settings.** One typed settings object (pydantic-settings) replaces `config_loader.get`.
Defaults ship in the package; user changes live in the user-data folder
(`%APPDATA%/Friday`); secrets come from the Windows Credential Manager, with `.env` honoured
in development. Module-level globals (`_BROWSER`, `_CONVERSATION`, cached models) become
objects created once at startup and passed in.

**Voice pipeline.** An explicit state machine: `idle → listening → thinking → speaking →
listening …`, returning to `idle` after two silent turns, as today. It publishes on an
event bus: state changes, input and output spectrum (about 16 bands, ~20 times a second,
for the visualiser), partial and final transcripts, and caption text as TTS speaks each
sentence. TTS is sentence-streamed so speech starts before the full reply is generated.

Interrupting speech: the Stop button, the Space bar and the global hotkey always work.
Interrupting by saying the wake word works only with a **headset mode** setting on,
because on open speakers the mic hears Friday's own voice and there is no echo
cancellation. Headset mode is off by default; with it off the mic is not read while Friday
speaks, as today. Echo cancellation for open speakers is not in this plan.

**TTS.** One interface (`synthesize(text) → audio`, `voices()`), three local providers.
Default order: Woof → Kokoro → Piper. ElevenLabs is removed entirely (owner's decision):
`speaker_elevenlabs.py`, `list_elevenlabs_voices.py`, the `elevenlabs` dependency and the
`ELEVEN_LABS` / `VOICE` variables all go. Voice
models download to the user-data folder on first use; none are committed or bundled.

**LLM providers.** One interface with chat, streaming and tool calling.

- *Ollama*: default model `qwen3:4b` (fits 16 GB, supports tools). The app lists installed
  models and can pull one.
- *OpenRouter*: the engine fetches the model list, keeps only models whose prompt and
  completion price are both zero and that support tool calling, and orders them (a shipped
  preference list first, then the rest). A request goes to the first; on rate limit,
  exhausted quota, model-gone or overload it moves to the next and the turn continues. A
  model that failed is skipped for a cool-down period. If every free model is exhausted
  Friday says so and, if Ollama is available, offers to continue locally. A paid model is
  never called.

**Agent.** A tool-calling loop replaces `router.py`: the model receives the conversation and
the tool list, calls tools, reads results, and answers in one or two spoken sentences.
Limits: a maximum number of steps per turn and a time budget, both settings.

A **fast path** stays in front of the model. It is today's keyword router, moved into the
package and covered by tests: an utterance it recognises runs the matching tool directly,
exactly as now, with no model involved. Only what it does not recognise goes to the agent.
This is what "no regression" means as a test: every utterance in the current command
table gives the same outcome, at the same speed, on the default local model or with no
model at all. The fast path may shrink later as models prove faster; it is not removed in
this plan. The old LLM intent-classification fallback inside the router is what the agent
replaces.

Because tools no longer speak, the pipeline speaks a short acknowledgement from
`personality.py` ("On it, boss") whenever a turn has produced no speech after about 1.5
seconds, so Friday is never silent while working.

**Tools.** Each existing handler becomes a tool: a function with a typed argument schema
and a description, returning data. Tools no longer call `speak()` themselves; the agent
decides what to say. Each tool declares a risk level: `read`, `write` or `destructive`.

**Approvals and questions.** When an action needs approval, or the agent needs a choice
from the user, the engine emits a request and pauses the turn. Friday asks aloud. The
answer arrives either from speech ("yes", "no", "the second one") or from a button in the
app.

What needs approval is decided by the **engine, not the model**:

- *Local tools* carry a fixed label. Everything Friday does today (app launch, volume,
  screenshot, timers, lookups, opening a page) is `read` and never asks, as now. Nothing
  in this version is `destructive`; the label exists for later desktop control.
- *Browser actions* are free by default: navigate, scroll, read, click, type. The engine
  inspects each action before it runs and requires approval when any of these is true:
  the page has a password field and the action submits it (a sign-in); the action submits
  a form or clicks a control whose name matches a maintained word list (send, post, submit,
  publish, pay, buy, order, checkout, confirm, delete, remove, transfer, subscribe,
  unsubscribe); a file upload or download; a payment field is on the page.
- *Other MCP servers* default to asking on every call until the owner marks a tool as
  free in settings.

"Always allow" is stored per site (domain) and action kind — for example "sign in on
github.com" or "send on mail.google.com" — never globally. Payment actions cannot be set to
always allow.

**MCP.** The engine is an MCP client. Servers are listed in settings; their tools join the
registry with a default risk of `write` unless marked otherwise. The browser (7.5) is the
first MCP server; this is also how further capabilities get added without engine changes.

**History and memory.** Turns, tool steps and approvals are stored in SQLite and shown in
the history sheet. A short rolling window plus a small user-editable notes file is given to
the model each turn.

### 7.4 Desktop app

Built from Beautiful UI's blocks and its dark theme tokens (Inter, JetBrains Mono, its
colour and radius scale). Custom only where the library has nothing: the voice visualiser
and the takeover overlay.

**Widget.** A small pill, always on top, draggable, position remembered. Shows state
(idle, listening, speaking), live frequency bars driven by real mic or TTS levels, Stop
while speaking, and Expand. Closing the full view returns to the widget; the tray icon
restores, pauses listening, or quits.

**Full view — stage.** A large visualiser and one caption line that changes like
subtitles. A slim side rail lists what Friday just did and what is running (timers, tasks).
No chat log.

**Dialogs.** For an approval or question the visualiser shrinks and a card (Beautiful UI's
Approval Card) rises under it; it leaves when answered. In widget mode the pill grows into
the same card. During browser takeover it appears above the floating voice bar with the
page dimmed.

**History sheet.** Hidden by default. "Show history", a scroll up, or a button slides the
conversation over the stage: messages, Friday's steps (Thinking, Tool Chips), and a prompt
bar for typing. Typed and spoken turns are the same conversation.

**Settings.** Model source and model, voice and speed, wake word sensitivity, microphone,
approval rules, MCP servers, keys. A visible "Voice by Underdog Woof" credit.

Scrolling surfaces follow the owner's standing rule: opaque background on the scroller,
`will-change: scroll-position`, hover disabled while scrolling, passive listeners.

### 7.5 Browser takeover

Friday's browser is a Chromium page hosted inside the Electron window with its own
persistent profile (separate from the user's Brave or Chrome). When the agent starts
browsing, that page expands to fill the app window with:

- a glowing border while Friday is in control,
- a visible Friday cursor that moves to each click and typing target,
- a floating voice bar: visualiser, current step ("Typing your username · step 2 of 5"),
  **Take over** and **Stop**.

**Take over** gives the user mouse and keyboard on the same page; "Friday, continue" or a
button hands it back. When the task ends the view returns to the stage and Friday reports
by voice.

**Control.** Microsoft's Playwright MCP server (free) attaches to that page over the
Chrome DevTools Protocol. It gives the model the page as an accessibility text snapshot
rather than screenshots, which small and free models handle far better. The current
`browser.py` extraction helpers (search results, page text) are kept as plain tools for
quick lookups that need no visible browsing.

**Where pages appear.** Until phase 5 ships, everything that shows a page today (stock,
crypto, news, World Monitor, "open YouTube", click / scroll / go back / read this page)
keeps driving the external Brave or Chrome through the existing Playwright code, so each
phase leaves Friday working. In phase 5 all of those move to the in-app browser and the
external-browser launch path is deleted. A page opened by a lookup or "open X" fills the
app window like any other, but the takeover dressing (glowing border, Friday cursor, step
text) appears only while the agent is performing actions on the page.

**Sign-ins.** The profile keeps cookies, so a site stays signed in. The first time a site
needs a password, Friday stops, says so, and the user types it via Take over. The model
never receives or types passwords. A vault that fills credentials without the model seeing
them is a later addition.

**Known risk.** Attaching Playwright to a page embedded in Electron is the least proven
part of the design. Phase 5 begins with a short spike. Fallback if it proves unreliable:
Playwright launches its own Chromium off-screen and the app shows a live stream of it
(DevTools screencast), forwarding mouse and keyboard during Take over. The user-visible
behaviour above is the same either way.

### 7.6 Installer

- The engine is frozen with PyInstaller (folder mode) and shipped as a resource of the
  Electron app.
- electron-builder produces `Friday-Setup-<version>.exe` (NSIS, per-user, no admin).
- Not code-signed; Windows SmartScreen will warn, as with Ember.
- First run downloads speech, voice and wake-word models with progress shown, checks for
  Ollama, and if it is missing explains the two choices: install Ollama, or use OpenRouter.

## 8. Build order

Each phase leaves Friday working.

1. This document, reviewed and approved.
2. **Clean-up and restructure.** Git hygiene, delete dead code, move modules into
   `engine/src/friday/`, typed settings, remove globals, tests around routing, tools and
   the pipeline with fake audio and a fake model. Behaviour unchanged; still runs from the
   terminal.
3. **Engine.** FastAPI + WebSocket, event bus, agent loop with tools and fast path, Ollama
   and OpenRouter providers with free-only fallback, Woof, approvals, MCP client, SQLite.
4. **Desktop app.** Electron shell, engine child process, widget, stage, dialogs, history
   sheet, settings, tray.
5. **Browser takeover.** Spike, then in-app browser, Playwright MCP, overlay, Take over.
6. **Installer.** PyInstaller, electron-builder, first-run setup.

Later, not in this plan: other desktop programs, custom "Friday" wake word, credential
vault, one-click Ollama install.

## 9. Left to the builder

- Exact WebSocket message names and schemas.
- Test framework details beyond pytest (engine) and Vitest (desktop); whether to add CI.
- State management library in the React app.
- The shipped OpenRouter preference list and cool-down length, after checking the live
  free-model list.
- Step and time limits for the agent, tuned on the target PC.
- How the fast path matches commands, provided it stays small and tested.

## 10. Open items

- **Beautiful UI source.** No repository is linked from the site. Builder tries to obtain
  the block source (site, author); if unavailable, blocks are recreated in React + Tailwind
  from the site's rendered markup and stylesheet, keeping names and look. MIT permits this.
- **Local model quality.** `qwen3:4b` on this CPU is expected to handle single-tool
  requests and to be slow and error-prone on multi-step browser tasks. OpenRouter free
  models are the recommended source for those. To be measured in phase 3, and the default
  adjusted if another small model does better.
- **Woof on Windows x86.** The publisher's speed figures are from Apple silicon only. To be
  measured in phase 3; if it is slower than real time on this PC, Kokoro becomes the
  default and Woof an option.
