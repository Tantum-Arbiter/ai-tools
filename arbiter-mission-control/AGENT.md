# ARBITER — Agent Skills & Specialties

## Identity

**Codename:** ARBITER  
**Persona:** J.A.R.V.I.S. (Paul Bettany)  
**Operator:** Sir Luke  
**Platform:** Mac M1 Pro (32 GB) + Windows RTX 3080 (ComfyUI)  
**LLM:** phi4:14b (local) / GPT-4o (fallback)  

---

## Core Skills

### 🎯 Voice Interface
- Wake word detection ("Arbiter") with fuzzy phonetic matching
- Double-clap activation with acoustic fingerprinting (broadband + transient analysis)
- Neural TTS via edge-tts (en-GB-RyanNeural)
- Follow-up listening (5s post-response, no wake word needed)
- Interrupt support (stop button, orb click)

### 📊 Intelligent Visualization (Phase 1–2)
- Intent classification: `compare`, `trend`, `breakdown`, `snapshot`, `detail`, `rank`
- Viz selection engine: maps intent × data shape → optimal chart type
- Toolkit: line, bar, hbar, doughnut, pie, area, hero stat, status grid, tables
- Multi-panel layouts for complex queries
- Auto-panel heuristic: attach visuals when answer references 3+ numeric values

### 💰 Financial Intelligence
- Live stock quotes (Yahoo Finance): AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META
- Market indices: S&P 500, FTSE 100, Dow Jones
- RevenueCat integration: MRR, subscribers, trials, churn, revenue
- Conversational synthesis (not raw ticker dumps)

### ☁️ Infrastructure Monitoring
- GCP: Cloud Run pods, CPU/memory, billing, service status
- ComfyUI health check (Windows PC on local network)
- Service health dashboard (Cloudflare, AWS, OpenAI, Gmail, etc.)
- Agent registry with heartbeat monitoring

### 🌤️ Daily Life
- Weather: current conditions + 7-day forecast (Open-Meteo, any location)
- News headlines (BBC/RSS)
- Sports updates
- Email intelligence (Gmail IMAP: unread, urgent, replied)

### 🎨 Creative Engine (Phase 5 — ComfyUI)
- Image generation via ComfyUI on Windows RTX 3080
- Video generation: ComfyUI image → Ken Burns → TTS voiceover → FFmpeg
- Prompt construction with brand-consistent style suffixes
- Queue management: submit, poll, download results
- Workflow: text prompt → ComfyUI API → poll history → retrieve output

### ⏰ Automation & Scheduling (Phase 6)
- Asyncio cron scheduler with minute-level precision
- Built-in reports: morning briefing, market close, evening digest
- Voice-created reminders persisted to `schedules.json`
- SSE event stream for proactive dashboard push
- Schedule management API (list, create, toggle, trigger)

### 🔧 System Actions
- Browser opening (explicit "open X" commands only)
- Dashboard refresh
- Panel focus

---

## Skill Phases

### Phase 1 — Viz Selector Engine ✅ PLANNED
Server-side intent detection + data-shape-aware chart selection.
Replaces hardcoded "stocks = bar chart" with intelligent mapping.

### Phase 2 — Frontend Components ✅ PLANNED
New viz types: hbar, hero stat, status grid, sparkline, multi-panel.
Responsive analysis overlay with better auto-sizing.

### Phase 3 — Richer Data Sources ⬜ BACKLOG
Historical revenue trends, real GCP pod metrics, proper day labels,
precipitation data, intraday stock data.

### Phase 4 — Auto-Panel ⬜ BACKLOG
Automatically attach visualization when spoken answer contains 3+ numbers.
No "show me" required — AI decides when a visual genuinely helps.

### Phase 5 — ComfyUI Creative Actions ✅ DONE
Voice-triggered image/video generation: "Arbiter, generate a sunset image"
→ routes to ComfyUI on Windows PC → polls for result → displays in panel.
Supports custom workflows, resolution presets, style modifiers.

### Phase 6 — Automation & Scheduling ✅ DONE
Lightweight asyncio cron scheduler with no external dependencies.
- **Built-in jobs**: Morning Briefing (8:00 AM M-F), Market Close (4:30 PM M-F), Evening Digest (9:00 PM daily)
- **SSE push**: `/api/events` streams proactive notifications to dashboard
- **Voice scheduling**: "remind me to check emails at 9am" creates persistent cron jobs
- **Management API**: GET/POST/toggle/trigger via `/api/schedules`
- **Frontend**: SSE listener auto-renders panels + speaks notifications

---

## Data Sources

| Source | Type | Endpoint | Refresh |
|--------|------|----------|---------|
| Open-Meteo | Weather | `/api/weather` | 30s |
| Yahoo Finance | Stocks | `/api/stocks` | 30s |
| BBC RSS | News | `/api/news` | 30s |
| ESPN RSS | Sports | `/api/sports` | 30s |
| Gmail IMAP | Email | `/api/email/*` | 30s |
| RevenueCat | Revenue | `/api/revenue/*` | 30s |
| GCP APIs | Infra | `/api/gcp/*` | 30s |
| ComfyUI | Creative | `COMFYUI_BASE_URL` | On-demand |
| Agent Registry | Agents | `/api/agents` | Heartbeat |
| StatusPage APIs | Health | `/api/service-health` | 30s |

---

## Architecture

```
Voice Input → Web Speech API (passive/active)
    ↓
Wake Word / Clap Detector
    ↓
LLM (phi4 local / GPT-4o) ← Live Data Context
    ↓
Response Parser → Spoken Text + Actions
    ↓                    ↓
Neural TTS          Panel Builder → Viz Selector → Frontend Renderer
    ↓                    ↓
Audio Playback     Analysis Overlay (Chart.js)
```

---

## Configuration

See `.env.example` for all environment variables.
Key settings: `LLM_PROVIDER`, `OLLAMA_MODEL`, `COMFYUI_BASE_URL`, `REVENUECAT_API_KEY`.
