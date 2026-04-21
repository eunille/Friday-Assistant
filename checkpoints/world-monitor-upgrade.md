# World Monitor Interactive Upgrade — Implementation Plan

## Overview
Transform World Monitor from a single-page scraper into a multi-category interactive dashboard with voice-controlled navigation, layer toggling, and session-based conversation.

## Architecture

### URLs
| Category | URL |
|----------|-----|
| World    | worldmonitor.app |
| Tech     | tech.worldmonitor.app |
| Finance  | finance.worldmonitor.app |

### Components Changed
- **browser.py** — Tab management (dedicated WM tab + general tabs)
- **world_monitor.py** — Multi-category scraping, layer checkbox interaction
- **handlers/world_handlers.py** — Sticky WM session loop, category routing
- **main.py** — No changes needed (conversation loop already exists)

### Model Usage
- **qwen3:1.7b** — Classify user intent (32 tokens), answer free-form questions only
- **No model for**: navigation, data reading, checkbox toggling, hot-topic detection

---

## Phase 1: Category Routing + Tab Management + Sticky Session
**Status: IMPLEMENTED — NEEDS TESTING**

### Tasks
1. **browser.py** — Add tab management:
   - `open_wm_tab(url)` — opens/reuses a dedicated WM tab
   - `open_new_tab(url)` — opens a new tab for non-WM commands
   - Track WM page reference separately from general browsing page

2. **world_monitor.py** — Multi-category URL routing:
   - `_WM_CATEGORIES` dict: world/tech/finance → base URLs
   - `get_category_url(category)` → returns full URL for category
   - Update `_scrape_page()` to accept optional URL parameter

3. **handlers/world_handlers.py** — Sticky WM session:
   - On "world monitor" → open WM → ask "World, Tech, or Finance?"
   - Enter WM conversation loop (stays active until user says "done"/"never mind")
   - Category switching mid-session ("switch to finance")
   - Exit phrases: "done", "never mind", "exit", "that's all", "go back"

### Checkpoint Criteria
- [ ] WM opens in dedicated tab
- [ ] Other commands open in separate tab
- [ ] Category navigation works (world/tech/finance)
- [ ] Sticky session stays active across follow-ups
- [ ] "Switch to X" changes category mid-session
- [ ] Exit phrases end WM session cleanly

---

## Phase 2: Hot-Topic Detection Per Category
**Status: IMPLEMENTED — NEEDS TESTING**

### Tasks
1. **world_monitor.py** — Category-aware topic scanning:
   - Tech topics: startup hubs, cloud regions, AI data centers, cyber threats, internet disruptions
   - Finance topics: crypto, forex, macro stress, commodities, central banks
   - World topics: conflicts, nuclear, sanctions, disasters (existing)

2. **handlers/world_handlers.py** — Overview flow:
   - After category selected → scrape → detect hot topics → speak overview
   - "Want an overview or a specific topic?" prompt
   - Overview reads top items from each active section

### Checkpoint Criteria
- [ ] Hot topics detected correctly for each category
- [ ] Overview speech reads key data points without LLM
- [ ] Topic drill-down works within category

---

## Phase 3: Playwright Checkbox Interaction
**Status: IMPLEMENTED — NEEDS TESTING**

### Tasks
1. **world_monitor.py** — Layer checkbox control:
   - `toggle_layer(page, layer_name, on=True)` — click checkbox by label text
   - `set_layers(page, layers_to_show)` — bulk toggle: uncheck all, check specified
   - CSS selectors for WM layer checkboxes

2. **handlers/world_handlers.py** — Voice-driven layer control:
   - "Show me cyber threats" → toggle cyber threats layer on
   - "Hide military" → toggle military layer off
   - "Only show nuclear" → uncheck all, check nuclear

### Checkpoint Criteria
- [ ] Individual layer toggle works (check/uncheck)
- [ ] Bulk layer switching works ("only show X")
- [ ] Layer state persists within session
- [ ] Correct CSS selectors identified for all 3 category views

---

## Risk Assessment
| Risk | Impact | Mitigation |
|------|--------|------------|
| CSS selectors change with WM updates | Layer toggling breaks | Use text-based selectors (`text=NUCLEAR SITES`) |
| Scrape takes too long on category switch | User waits | Cache per category, speak while scraping |
| Playwright tab management race conditions | Browser hangs | Reuse `_OP_LOCK`, sequential ops |
| Whisper mishears category names | Wrong navigation | Add fuzzy matching for "tech"/"finance"/"world" |
