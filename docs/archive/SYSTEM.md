# Friday AI Assistant — System Documentation

## Overview

Friday is a voice-activated AI assistant running on Fedora Linux with KDE Plasma.
- **STT**: Whisper (small model)
- **TTS**: Piper (`en_US-ryan-medium`)
- **LLM**: Ollama `qwen3:1.7b` (num_ctx: 1024, num_predict: 150)
- **Browser**: Playwright controlling Brave (`/usr/bin/brave-browser`)

---

## Routing Architecture

Voice input goes through a **3-tier routing pipeline** in `router.py`:

```
Voice Input → Whisper STT → router.py
                               │
                    ┌──────────┼──────────────┐
                    │          │              │
              Keyword      LLM Classify    LLM Chat
              (Tier 1)     (Tier 2)        (Tier 3)
```

**Tier 1 — Keyword match**: Fast, deterministic. Catches known intents by exact/partial words.  
**Tier 2 — LLM classify**: For ambiguous inputs. LLM picks intent from a defined list.  
**Tier 3 — LLM chat**: Fallback. Treats input as a direct conversation message.

### Routing Priority Order (top wins)

1. Goodbye/thanks
2. Compare (vs, versus)
3. **Crypto** — checked BEFORE "what is" so "what is bitcoin" → live prices not Britannica
4. "Tell me / what is / explain" → Knowledge handler
5. World news / World Monitor
6. Stocks & commodities (LLM resolves any ticker)
7. Weather
8. General news
9. "Check [x]" fallback → Knowledge handler
10. System commands (volume, time, timer, screenshot, apps, browser)
11. LLM classify → intent dispatch
12. LLM chat (conversational fallback)

---

## Handler Flows

### Knowledge — `handle_knowledge` (`handlers/web_handlers.py`)

Triggered by: "what is", "tell me about", "explain", "check [topic]"

```
1. Speak echo: "Looking into [topic]."
2. HTTP DDG search (silent, no browser) → top organic results (ads filtered out)
3. Silent page visit → extract <main>/<article> content (no visible browser)
4. LLM summarizes → Friday speaks 2–3 sentence answer
5. "Pulled up the source for you, boss." → browser tab opens to article
```

Key behaviors:
- DDG ad URLs (`/y.js?ad_domain=...`) are filtered before any URL is collected
- `<main>` / `<article>` are preferred over full `<body>` to avoid nav/ad text
- LLM context is capped at 600 chars to fit within `num_ctx: 1024`
- Browser tab opens AFTER answer is spoken (source display, not part of answering)

---

### Crypto — `handle_crypto` (`handlers/finance_handlers.py`)

Triggered by: "crypto", "bitcoin", "ethereum", coin names (dynamic from CoinGecko config)

**Overview mode** (no specific coin named):
```
1. "Okay boss, let me check the crypto market."
2. Parallel: fetch all overview coins (CoinGecko API) + open CoinGecko in browser tab
3. Speak price + % change for each coin
4. Closing phrase
```

**Single coin mode** (e.g., "bitcoin price"):
```
1. "Okay boss, let me check [coin]."
2. Fetch price from CoinGecko API
3. Speak price + % change + market quip if notable move
4. Closing phrase
```

---

### Stocks & Commodities — `handle_stock` (`handlers/finance_handlers.py`)

Triggered by: "stock", "price", "share", "oil", "gold", "silver", "copper", "gas", "how much", "worth", "trading"

```
1. Check config for known ticker shortcuts
2. If not found → LLM resolves any natural language to TICKER|ASSET_NAME
   (handles stocks, ETFs, futures like CL=F, GC=F, indices like ^GSPC)
3. Repeat check: if same asset asked within 5 min → short sarcastic quip, no "just a second"
4. "Okay boss, just a second." (if not repeat)
5. Thinking pause: "Alright, boss —" or "Hmm." etc. (~50% include "boss")
6. Speak price + % change
7. Market quip if notable move (>4% down or >5% up)
8. Closing phrase
```

---

### World Monitor — `handle_world_monitor` (`handlers/world_handlers.py`)

Triggered by: "check news", "world monitor", "global news", "world events", etc.

```
1. "Okay boss, just a second."
2. Parallel:
   a. Fetch RSS headlines (BBC World + Google News World) — no browser
   b. Open World Monitor URL in browser tab
3. LLM summarizes headlines → Friday speaks overview
4. Closing phrase
```

---

### Weather — `handle_weather` (`handlers/web_handlers.py`)

Triggered by: "weather", "temperature", "forecast", "rain", "sunny", "hot outside", "cold outside"

Uses configured weather site/API. Speaks current conditions.

---

## Browser Architecture (`browser.py`)

```
_BROWSER     — single Playwright Chromium/Brave process (launched once)
_CONTEXT     — single browser context
_PAGE        — internal extraction tab (silent, used by visit_and_extract)
_DISPLAY_PAGE — visible user-facing tab (used by open_url)
```

**`open_url(url)`**: Navigates `_DISPLAY_PAGE`. Skips navigation if already on target URL. Never opens a new OS window.

**`visit_and_extract(url)`**: Navigates `_PAGE` silently for content extraction. Not visible to user.

**`search_and_extract(query)`**: Pure HTTP request to DDG — zero browser involvement. Returns organic results with ads filtered.

**`get_page_text()`**: Extracts text from `_PAGE`. Tries `<main>` → `<article>` → `[role="main"]` → `#content` → `.content` → `<body>`. Filters lines shorter than 15 chars.

**Browser recovery**: If `_PAGE.evaluate("1")` throws, `_reset_browser()` clears all state and Playwright relaunches on next call.

---

## Personality (`personality.py`)

| Function | Purpose | "boss" usage |
|---|---|---|
| `get_thinking_pause()` | Opening phrase before data | ~50% include "boss" |
| `get_summary_done()` | Closing phrase after data | Never "boss" |
| `get_browser_opening()` | "Okay boss, just a second." | Always "boss" |
| `get_market_quip(dir, pct)` | Dry comment on notable moves | Never "boss" |
| `get_repeat_quip(topic)` | Short reply when same topic re-asked | Never "boss" |

**"boss" rule**: Appears at most once per response — only in the thinking pause (and `get_browser_opening`). Never repeated in data line or closing phrase.

---

## Key Config (`config.yaml`)

```yaml
browser:
  executable: /usr/bin/brave-browser
  search_url: "https://duckduckgo.com/?q={query}"
  tile_left: false          # Set true to auto-snap browser left on KDE/KWin
  page_load_timeout: 15000
  action_timeout: 10000

llm:
  model: qwen3:1.7b
  num_ctx: 1024
  num_predict: 150
```

---

## File Map

| File | Purpose |
|---|---|
| `main.py` | Entry point, init, wake word loop |
| `router.py` | Intent routing (3 tiers) |
| `brain.py` | LLM interface (Ollama chat + summarize) |
| `browser.py` | Playwright browser automation |
| `speaker.py` | Piper TTS output |
| `listener.py` | Whisper STT input |
| `wake_word.py` | Wake word detection |
| `personality.py` | All spoken phrase templates |
| `context.py` | Conversation context tracker |
| `handlers/finance_handlers.py` | Stocks, crypto, commodities |
| `handlers/web_handlers.py` | Browser open, search, knowledge |
| `handlers/world_handlers.py` | World news via RSS + LLM |
| `handlers/weather_handlers.py` | Weather |
| `config.yaml` | All configuration |
