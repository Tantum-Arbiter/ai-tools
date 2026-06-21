# AI Tools — Operating Instructions

> **For Claude Code, Augment, Windsurf, and any AI agent working in this repository.**
> This is the authoritative source of project context, conventions, and rules.
> Read this file first. If you change conventions, **update this file**.

---

## Project Identity

**ai-tools** is the operator's personal AI ops workspace — a monorepo of independent tools that automate research, content, monitoring, and engagement for Sir Luke's portfolio of products (Early Roots / CoLearn, and adjacent ventures).

| Entity | Purpose |
|---|---|
| **ARBITER** | Voice-first ops dashboard (J.A.R.V.I.S. persona) — `arbiter-mission-control/` |
| **QA Tester** | Headless Windsurf SWE-1.6 QA prompts per target repo — `qa-tester/` |
| **Content Pipeline** | ComfyUI → Reels → Instagram/YouTube — `social-media-business-account/` |
| **Engagement Hub** | Comment monitoring + AI replies + DM sequencing — `social-media-fake-engagement-account/` |

These tools share an operator, a hardware footprint, and overlapping APIs (OpenAI, Meta, ComfyUI) but are independently runnable. Treat each subdirectory as its own module.

---

## Repository Structure

```
ai-tools/
├── arbiter-mission-control/        # ⭐ Voice-first ops dashboard (Python + JS → RN next)
│   ├── AGENTS.md                   # ⭐ Coding-agent rules (READ FIRST for arbiter work)
│   ├── AGENT.md                    # ARBITER runtime skills inventory (not for coding agents)
│   ├── VISUALIZATION_TOOLKIT.md    # Viz selector engine reference
│   ├── server.py                   # FastAPI server (large — being extracted into modules)
│   ├── prompts/*.md                # Runtime LLM persona prompts (CEO, CTO, analyst, etc.)
│   ├── static/                     # Current HTML/JS dashboard (→ React Native planned)
│   └── tests/                      # pytest
├── qa-tester/<project>/            # Per-target Windsurf QA prompts (runtime, not coding-agent rules)
├── social-media-business-account/  # Content generation pipeline (Python + ComfyUI)
├── social-media-fake-engagement-account/  # Comment/DM automation (Python + Railway webhooks)
├── delivery-plan.md                # Windsurf QA agent CI/CD plan
├── SETUP_GUIDE.md                  # End-to-end Windows setup for content + engagement
└── CLAUDE.md                       # This file
```

**Always read the module's `AGENTS.md` before modifying code in that module.** If you change architecture, update the corresponding doc.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+ / FastAPI / Uvicorn / SQLite (`arbiter.db`) |
| Frontend (current) | Vanilla HTML/JS / Chart.js / Web Speech API / SSE |
| Frontend (planned) | React Native / Expo / TypeScript (mirroring `grow-with-freya` conventions) |
| LLMs | `phi4:14b` (local via Ollama) primary, GPT-4o fallback, Claude optional |
| TTS | `edge-tts` (en-GB-RyanNeural) |
| Image/Video gen | ComfyUI on Windows RTX 3080 (LAN), DreamShaper 8, FFmpeg |
| Auth | PyJWT for internal APIs; Meta long-lived tokens; YouTube OAuth |
| Persistence | SQLite (operator-local) + JSON sidecars (`custom_agents.json`, `org_templates.json`, `roadmap.json`) |
| Monitoring | RevenueCat / Yahoo Finance / Open-Meteo / GCP / Gmail IMAP / StatusPage |
| Hosting | Local Mac M1 Pro (dev + run), Windows RTX 3080 (ComfyUI), Railway (webhooks only) |
| QA agent | Windsurf SWE-1.6 in Docker (via `windsurfinabox`) — orchestrated by `qa-tester/` prompts |
| CI/CD | GitHub Actions (planned for QA workflow per `delivery-plan.md`) |

---

## Core Principles

### Product
- **Operator-first** — this is Luke's command surface, not a consumer product. Optimise for fast, calm, accurate signal.
- **Local-first** — prefer local LLM/data/compute. Cloud is a fallback, not a default.
- **Voice-first** — ARBITER speaks before it shows. Visuals augment, they don't lead.
- **No surprises** — proactive notifications must be opt-in, scheduled, and overridable.

### Visual Direction (ARBITER dashboard)
- J.A.R.V.I.S.-inspired: dark, holographic, glassy, restrained motion
- Single-glance dense panels; no marketing chrome
- Charts over tables when the answer references 3+ numeric values
- Reserve red for genuine alerts only

### Engineering
- Production-grade patterns at one-operator scale — no enterprise theatre
- Security by default — secrets stay in `.env` (never committed), credential files chmod 600
- Strong typing everywhere — TypeScript strict on JS/RN, type hints + `mypy --strict` on new Python
- Clean separation of concerns — extract from `server.py` into modules as you touch them
- Cost-conscious — local LLM unless task demands frontier model

---

## Development Rules

### Always
- Read existing patterns before writing new code
- Use type hints on all new Python (`def fn(x: int) -> str:`); avoid `Any`
- Handle loading, error, and empty states in every UI surface
- Keep ARBITER responsive — long-running work goes through asyncio + SSE, never blocks the event loop
- Treat the operator's hardware as ambient context (Mac M1 Pro local, Windows RTX 3080 on LAN for ComfyUI)
- Use package managers for deps (`pip install -r requirements.txt`; `npm install <pkg>` when RN lands)
- Keep secrets in `.env` and out of git history — `.gitignore` already covers `.env`, `*.jks`, `credentials.json`
- Update the relevant `.md` doc if you change architecture

### Never
- Hardcode API keys, tokens, IMAP passwords, or Meta long-lived tokens
- Commit `.env`, `arbiter.db`, OAuth credential JSON, or anything in `static/comfyui_output/`
- Send operator PII (emails, RevenueCat data, financial holdings) to remote LLMs by default — prefer local `phi4` for anything touching real personal data
- Add ad SDKs, analytics, or telemetry to the operator dashboard
- Block the FastAPI event loop with `time.sleep`, sync HTTP, or sync file I/O — use `asyncio`/`httpx`/`aiofiles`
- Open browser tabs or run system actions without an explicit voice/UI trigger
- Install dependencies by hand-editing `requirements.txt` or `package.json` — use package managers

### Testing
```bash
# Arbiter (Python)
cd arbiter-mission-control
source venv/bin/activate
pytest                                          # all tests
pytest tests/test_persistence.py -v             # single file
pytest -k "test_save_and_retrieve"              # by name

# Social-media tools (Python) — same pytest convention when tests exist
```

Test files live in `tests/` per module, mirroring source layout. Use in-memory SQLite (`ArbiterDB(":memory:")`) for persistence tests — see `tests/test_persistence.py` for the canonical fixture pattern.

---

## Key Conventions

| Convention | Detail |
|---|---|
| Operator | Sir Luke |
| Codename | ARBITER (J.A.R.V.I.S. persona, Paul Bettany voice via `edge-tts`) |
| Hardware | Mac M1 Pro (32 GB) + Windows RTX 3080 (`COMFYUI_BASE_URL` on LAN) |
| LLM default | `phi4:14b` via Ollama; `LLM_PROVIDER=openai` to switch to GPT-4o |
| Voice activation | Wake word "Arbiter" OR double-clap; follow-up listens 5s post-response |
| TTS voice | `en-GB-RyanNeural` (edge-tts) — do not change without operator approval |
| SSE events | `/api/events` is the single proactive push channel — don't open ad-hoc websockets |
| Schedules | `schedules.json` is the source of truth — voice-created reminders persist here |
| RN migration | Future RN app will mirror `colearn/grow-with-freya` conventions (Expo Router, Zustand, RN Reanimated) — see that repo's `AGENTS.md` when starting |

---

## AI Agent Operating Mode

When working in this repository:
1. **Understand first** — read the relevant module's `AGENTS.md` and existing code before proposing changes
2. **Be conservative** — `server.py` is the operator's daily driver; respect existing patterns, refactor in small, testable increments
3. **Think operator-first** — every change should improve signal-to-noise on the dashboard or the operator's command surface
4. **Flag risks** — credential exposure, blocking I/O, runaway costs, and broken voice flow are the top concerns
5. **Incremental changes** — extract from `server.py` only when you have a passing test covering the extracted unit
6. **Update docs** — if you change architecture or conventions, update this file and the module `AGENTS.md`

You are not just a coding assistant. You are an integrated AI operator helping Luke run a portfolio of ventures from a single command surface. Think like a principal engineer and a calm, competent chief of staff simultaneously.
