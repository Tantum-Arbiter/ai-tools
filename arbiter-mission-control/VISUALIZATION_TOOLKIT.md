# ARBITER — Intelligent Visualization Toolkit

## Overview

Server-side engine that replaces hardcoded `_build_panel()` keyword matching with
intelligent **intent detection × data shape → optimal visualization** selection.
The LLM never generates panel JSON — it writes the spoken summary. The viz engine
independently builds the best visual for the data.

---

## Architecture

```
User Query
    │
    ├─▶ Intent Classifier ──▶ compare | trend | breakdown | snapshot | detail | rank
    │
    ├─▶ Topic Detector ──▶ stocks | weather | revenue | gcp | email | news | sports | comfyui
    │
    └─▶ Data Fetcher (existing async functions)
            │
            ▼
        Viz Selector (intent × data shape → chart type + layout)
            │
            ▼
        Panel JSON ──▶ Frontend Renderer (Chart.js + custom components)
```

---

## Intent Classification

| Intent | Trigger Patterns | Example |
|--------|-----------------|---------|
| `compare` | compare, vs, versus, against, better, which, difference | "compare Apple and Tesla" |
| `trend` | trend, over time, this week, history, forecast, projection | "stock trend this week" |
| `breakdown` | breakdown, break down, split, composition, what makes up | "break down my GCP costs" |
| `snapshot` | how's, what's, status, current, right now, overview | "how's the market" |
| `detail` | tell me about, what is, explain, deep dive, details on | "tell me about Cloud Run" |
| `rank` | top, best, worst, highest, lowest, most, least, ranking | "top performing stocks" |

Default: `snapshot` (when no intent pattern matches).

---

## Viz Selection Matrix

| Data Shape | compare | trend | breakdown | snapshot | detail | rank |
|-----------|---------|-------|-----------|----------|--------|------|
| N items + numeric value | hbar (sorted) | — | doughnut | stat cards | — | hbar (sorted) |
| Time series | grouped bar | line / area | stacked area | line | line | — |
| Parts of whole | — | — | doughnut | doughnut | — | — |
| Single entity + metrics | — | sparkline | — | hero + cards | hero + cards | — |
| Binary status per item | — | — | — | status_grid | status_grid | — |
| List (no numeric axis) | — | — | — | table | table | table |
| Two metrics | side-by-side cards | dual-axis line | — | stat cards | stat cards | — |

---

## Viz Types (Frontend)

### Existing
- `bar` — vertical bars (Chart.js)
- `line` — line chart with optional multi-dataset (Chart.js)
- `doughnut` / `pie` — proportional (Chart.js)
- `stat cards` — key-value badges with status color
- `table` — header + rows grid

### New (Phase 2)
- **`hbar`** — horizontal bar (`indexAxis: 'y'`). Better for ranked comparisons.
- **`area`** — filled line (`fill: true`). For cumulative/volume data.
- **`hero`** — single large number + delta indicator + optional sparkline.
- **`status_grid`** — colored dots for service health (replaces "NOMINAL" text).
- **`sparkline`** — tiny inline chart inside stat cards for mini-trends.
- **`multi_panel`** — vertically stacked sections for complex queries.

---

## Smart Defaults Per Data Source

| Source | snapshot | compare | trend | breakdown | rank |
|--------|----------|---------|-------|-----------|------|
| Stocks | stat cards | hbar (by % change) | line (intraday†) | doughnut (portfolio) | hbar (sorted) |
| Weather | hero (temp) + cards | side-by-side cards | line (7-day) | — | — |
| Revenue | stat cards (MRR etc) | grouped bar | line (MRR†) | doughnut (split) | — |
| GCP | status_grid + cards | — | line (CPU/mem†) | doughnut (cost†) | — |
| Email | stat cards | — | bar (recv/replied) | doughnut (read/unread) | — |
| News | table | — | — | — | — |
| Sports | table | — | — | — | — |

† = requires historical data (Phase 3).

---

## ComfyUI Creative Actions (Phase 5)

### Trigger Detection
Voice commands matching creative intent route to the Windows RTX 3080:

| Pattern | Action |
|---------|--------|
| "generate/create/make an image of..." | `comfyui_image` |
| "generate/create/make a video of..." | `comfyui_video` |
| "render/draw/design..." | `comfyui_image` |
| "show me what X looks like" | `comfyui_image` |

### Flow
```
"Arbiter, generate an image of a sunset over London"
    │
    ├─▶ Extract prompt: "a sunset over London"
    ├─▶ POST COMFYUI_BASE_URL/prompt (with workflow JSON)
    ├─▶ Poll COMFYUI_BASE_URL/history/{id} until complete
    ├─▶ GET COMFYUI_BASE_URL/view?filename=... → download image
    └─▶ Display in analysis panel as hero image + metadata cards
```

### Panel Output
```json
{
  "title": "COMFYUI — IMAGE GENERATED",
  "image_url": "/api/comfyui/output/ComfyUI_00042_.png",
  "stats": [
    {"label": "Prompt", "value": "sunset over London"},
    {"label": "Resolution", "value": "1024×1024"},
    {"label": "Steps", "value": "30"},
    {"label": "Time", "value": "12.4s"}
  ]
}
```

### Configuration
```env
COMFYUI_BASE_URL=http://192.168.1.XX:8188   # Windows PC local IP
COMFYUI_CHECKPOINT=dreamshaper_8.safetensors
COMFYUI_OUTPUT_DIR=C:/ComfyUI/output
```

---

## Implementation Phases

### Phase 1 — Viz Selector Engine (server.py)
- [ ] Extract `_classify_intent(query)` → returns intent enum
- [ ] Extract `_detect_topic(query, history)` → returns data source
- [ ] Refactor `_build_panel()` → intent × topic → viz rules → panel JSON
- [ ] Each data handler returns raw data + shape hints

### Phase 2 — Frontend Components (jarvis.js + style.css)
- [ ] `hbar` renderer (indexAxis: 'y')
- [ ] `hero` stat component (large number + delta)
- [ ] `status_grid` component (colored dots)
- [ ] `multi_panel` layout (vertical stacking)
- [ ] Responsive sizing for analysis overlay

### Phase 3 — Richer Data (server.py)
- [ ] Stock: sorted by % change, gainers/losers split
- [ ] Weather: proper day names (Mon, Tue...), precipitation
- [ ] GCP: real pod metrics (CPU, memory) as trend data
- [ ] Revenue: historical MRR if RevenueCat exposes it

### Phase 4 — Auto-Panel
- [ ] Heuristic: if spoken answer has 3+ numbers → auto-attach panel
- [ ] User can dismiss immediately
- [ ] "No panel" override in system prompt for simple queries

### Phase 5 — ComfyUI Creative Actions
- [ ] `/api/comfyui/generate` endpoint in server.py
- [ ] Prompt extraction from natural language
- [ ] Job polling + output retrieval
- [ ] Image display in analysis panel
- [ ] Video generation pipeline (image → Ken Burns → TTS → FFmpeg)

### Phase 6 — Automation & Scheduling ✅
- [x] Lightweight asyncio cron scheduler (no external deps)
- [x] Built-in jobs: Morning Briefing (8:00 AM M-F), Market Close (4:30 PM M-F), Evening Digest (9:00 PM daily)
- [x] SSE event stream (`/api/events`) for proactive push to dashboard
- [x] Schedule management API (GET/POST/toggle/trigger `/api/schedules`)
- [x] Voice-created reminders ("remind me to X at Y")
- [x] User schedule persistence to `schedules.json`
- [x] Frontend SSE listener with auto-reconnect + panel/TTS rendering

---

## Testing Strategy

`tests/test_viz_engine.py` covers (56 tests):
1. **Intent classification** — each intent type with multiple phrasings
2. **Topic detection** — correct data source from query text
3. **Viz selection** — correct chart type for intent × topic combos
4. **Panel structure** — valid JSON with required fields
5. **ComfyUI routing** — creative commands detected and routed correctly
6. **Scheduler cron matching** — exact times, weekday filters, comma lists, Sunday=0, invalid crons
7. **Voice schedule commands** — regex parsing for "remind me to X at Y" patterns
8. **Edge cases** — ambiguous queries, missing data, fallback behavior
