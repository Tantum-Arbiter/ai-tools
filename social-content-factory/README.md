# social-content-factory

> Theme → social-media-ready image and video assets, generated locally on the operator's Windows RTX 3080 and queued for human review before publish.

This module turns a short **theme brief** (`"shipped a new voice pipeline today"`, `"toddler bedtime myth #3"`, `"engineering wins of the week"`) into a pack of platform-correct visuals + caption variants, written to an `outbox/` for human approval. No auto-publishing in early phases.

It is a sibling of `social-media-business-account/` (which already runs the Grow with Freya pipeline). Where that module is a single-brand end-to-end content + publish system, **social-content-factory** is a **brand-pluggable asset factory** — it can serve Early Roots, Sir Luke's personal voice, *or* a workplace "cool things we built" feed.

---

## Why a new module?

- `social-media-business-account` is tightly coupled to the Grow with Freya brand voice and publishes directly to IG/YouTube.
- Workplace use ("share the cool things we do") needs a different brand registry, different formats (LinkedIn 1.91:1, square dev-tweet style), and a hard requirement of **no auto-publish** until reviewed.
- A clean module keeps brand assets, prompts, and outbox folders separate so a work brand can never accidentally inherit Grow with Freya psychology triggers.

---

## Architecture (target)

```
themes/<brand>.yaml ──┐
manual brief (CLI) ───┼──► Theme Selector ──► Brief Builder ──► Prompt Composer
RSS / GH releases ────┘    (local phi4)        (brand-aware)         │
(Phase 5)                                                            │
                                                                     ▼
                                ComfyUI on Windows RTX 3080  ◄───────┘
                                (COMFYUI_BASE_URL on LAN)
                                          │
                                          ▼
                                 Image Renderer ──► Variants (1:1, 4:5, 9:16)
                                          │
                                          ▼
                                 Caption + Hashtag Generator (local phi4)
                                          │
                                          ▼
                          outbox/<date>/<brand>/<theme-slug>/
                            ├── img_1x1.png
                            ├── img_4x5.png
                            ├── img_9x16.png
                            ├── video.mp4         (Phase 3+)
                            ├── caption.md        (IG + X variants)
                            └── metadata.json     (prompt hash, seed, model, brand, theme)
                                          │
                                          ▼
                          Human review → Phase-4 publish hooks
```

---

## What this module does **not** do

- ❌ No automatic publishing until Phase 4 (and even then, opt-in per brand).
- ❌ No children's faces, no real-person likenesses, no PII in prompts.
- ❌ No remote LLMs for any prompt touching operator/work PII — local `phi4` only.
- ❌ Does not replace `social-media-business-account` — that pipeline keeps running for Grow with Freya.

---

## Brand registry

A brand is just a YAML file under `brands/`. **MVP ships one brand: `personal`.** The architecture stays brand-pluggable so a workplace ("cool things we built") brand can be added later without code changes — but no second YAML is in scope until the operator decides to add one.

| Brand key | Source of truth | Audience | Default formats | Status |
|---|---|---|---|---|
| `personal` | `brands/personal.yaml` | Sir Luke's own feed | 1:1, 9:16 | MVP |
| _future brands_ | _deferred_ | — | — | Deferred — add by dropping a new YAML in `brands/`. No code change required. |

Adding a brand = new YAML + a brand-tuned prompt suffix. No code changes.

---

## Status

- 📋 **Planning** — see [`delivery-plan.md`](./delivery-plan.md) for the phased build.
- 🤖 **Coding-agent rules** — see [`AGENTS.md`](./AGENTS.md) before editing this module.

---

## Quick reference

| Concern | Where it lives |
|---|---|
| Phased build plan | `delivery-plan.md` |
| How coding agents must operate here | `AGENTS.md` |
| Brand definitions | `brands/<key>.yaml` (Phase 1) |
| Theme catalogue | `themes/<brand>.yaml` (Phase 1) |
| ComfyUI workflow JSONs | `workflows/` (Phase 1) |
| Generated assets (gitignored) | `outbox/` |
| Render history / dedup | `data/factory.db` (SQLite) |
| Tests | `tests/` (pytest, mirror source layout) |

---

## Hardware contract

- **Mac M1 Pro** — runs the orchestrator, theme selector, caption generator (local `phi4` via Ollama).
- **Windows RTX 3080** — runs ComfyUI on `COMFYUI_BASE_URL` (LAN). Same machine the existing `social-media-business-account` module already uses; no new install.
- **No cloud GPU** in any phase. If the Windows host is unreachable, the factory fails fast with a clear message rather than falling back to a paid API.

---

## Locked decisions

All planning decisions are locked in `delivery-plan.md` §"Locked Decisions" (D1–D6). MVP scope: **`personal` brand only**, no auto-publish through Phase 3, manual themes, Ken Burns + TTS video, 4 image + 4 caption variants per run.
