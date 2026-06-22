# social-content-factory — Delivery Plan

## Overview
Build a brand-pluggable factory that turns a short **theme brief** into platform-correct social assets (image first, video later), rendered locally on the Windows RTX 3080 via ComfyUI, queued in an `outbox/` for human review. Same hardware footprint as `social-media-business-account/`; zero new cloud spend.

**North star:** I can type `factory render --brand work --theme "shipped voice pipeline"` and 30 seconds later have a LinkedIn-ready 1.91:1 + IG-ready 1:1 image + caption variants on disk, with no Photoshop.

---

## Architecture

```
themes/<brand>.yaml ──┐
manual CLI brief ─────┼──► Theme Selector ─► Brief Builder ─► Prompt Composer
RSS / GH (Phase 5) ───┘    (local phi4)      (brand-aware)         │
                                                                   ▼
                            ComfyUI (Windows RTX 3080, LAN) ◄──────┘
                                          │
                                          ▼
                            Multi-format Renderer ─► outbox/<date>/<brand>/<slug>/
                                                       ├── img_1x1.png
                                                       ├── img_9x16.png  (Phase 2)
                                                       ├── video.mp4     (Phase 3)
                                                       ├── caption.md
                                                       └── metadata.json
```

---

## Locked Decisions

| # | Decision | Locked value |
|---|---|---|
| D1 | Brands at MVP | **`personal` only.** A "work" brand stays deferred — architecture remains brand-pluggable but no second YAML ships until the operator decides to add one. |
| D2 | Work brand voice / visual style | **Deferred** with D1. To be designed when (and if) a work brand is added. |
| D3 | Auto-publish | **No publish through Phase 3.** Phase 4 introduces opt-in `allow_auto_publish` per brand, dry-run by default. |
| D4 | Theme source | **Manual `themes/personal.yaml` only.** Auto-ingest (GitHub / RSS / changelog) deferred to Phase 5 and reviewed before render. |
| D5 | Video style (Phase 3) | **Ken Burns + `edge-tts` voiceover** over the 9×16 still. AnimateDiff not in scope. |
| D6 | Output cap per run | **1 theme → up to 4 image variants + 4 caption variants.** Operator approves before any publish. |

> Note: deferring the "work" brand removes Phase-4 LinkedIn publishing from MVP critical-path. LinkedIn hook is still listed in Phase 4 as a stub but is not required to ship; Instagram (personal) is the only Phase-4 target.

---

## Prerequisites
- Windows PC with ComfyUI already running on `COMFYUI_BASE_URL` (already set up for `social-media-business-account/`).
- DreamShaper 8 (already downloaded) + 1 SDXL checkpoint for sharper text-on-image work (Phase 2 download, ~6 GB).
- Mac M1 Pro with `phi4:14b` available via Ollama (already in use).
- `ffmpeg` on PATH (already required by Grow with Freya pipeline).

---

## Phase 1 — Single-brand, single-format MVP (Days 1–3)

**Deliverable:** `factory render --brand personal --theme <slug>` produces one 1:1 PNG + one caption.md to `outbox/`.

### 1.1 Module skeleton
- `social_content_factory/` Python package, `pyproject.toml` (or `requirements.txt` mirror of sibling module).
- `cli.py` using `typer` (already on classpath via sibling module patterns) — `render` subcommand only.
- `schemas/brand.py`, `schemas/theme.py`, `schemas/brief.py` — Pydantic v2 models.
- `tests/` mirror layout. First failing test: `test_brand_loader.py::test_loads_personal_brand_yaml`.

### 1.2 Brand + theme YAML loaders
- `brands/personal.yaml` only (D1). Loader rejects unknown brand keys with a clear error.
- `themes/personal.yaml` with ≥ 3 sample themes.
- Pydantic validation on load; fail fast.

### 1.3 Brief builder
- Pure function: `(brand, theme) -> Brief`. No LLM call yet — deterministic template fill.
- Tests cover: required fields populated, brand voice token injected, missing fields raise.

### 1.4 ComfyUI client (forked-not-copied from sibling)
- New `comfyui_client.py` — `httpx.AsyncClient`, workflow JSON loaded from `workflows/image_sd35_base.json`.
- Model: `sd3.5_medium_incl_clips_t5xxlfp8scaled.safetensors` (proven on the Windows RTX 3080 box; overridable via `SCF_COMFYUI_MODEL`).
- Proven defaults: sampler `euler`, scheduler `sgm_uniform`, cfg 5.5, steps 35 (lifted from Stickrbook's tuned settings — same checkpoint, same GPU).
- Per-brand `style_suffix` + `negative_prompt` injected from brand YAML (no hardcoded brand strings).
- Test against a `respx`-mocked ComfyUI; assert workflow JSON shape after substitution.

### 1.5 Outbox writer
- `outbox/<YYYY-MM-DD>/<brand>/<theme-slug>/` — atomic write via temp file + rename.
- `metadata.json` records: brand, theme, seed, checkpoint, prompt hash (not full prompt), git SHA, timestamp.
- Add `outbox/` and `data/` to `.gitignore`.

### Phase 1 acceptance
- ✅ `pytest` green, no real network calls in tests.
- ✅ `factory render --brand personal --theme weekly-build` writes a real PNG to `outbox/` on a live Windows ComfyUI.
- ✅ `metadata.json` lets you reproduce the same image (same seed → same hash).

---

## Phase 2 — Multi-format renderer (Days 4–5)

**Deliverable:** one theme renders to 4 aspect ratios in parallel; per-platform caption variants.

- Add `formats: [1x1, 4x5, 9x16]` to `brands/personal.yaml`; renderer queues N ComfyUI jobs (1.91:1 reserved for a future work brand).
- Caption generator (`phi4` local) produces IG / X variants from one Brief (LinkedIn deferred with the work brand).
- Tests: assert all formats present, dimensions match, captions ≤ platform limits.

---

## Phase 3 — Video pipeline (Days 6–8)

**Deliverable:** opt-in `--video` flag produces a 6–10 s MP4.

- Ken Burns pan/zoom over the 9×16 PNG + `edge-tts` voiceover (en-GB-RyanNeural) — D5 locked.
- `ffmpeg` invocation via `asyncio.create_subprocess_exec` — never block.
- Tests: video file exists, duration within tolerance, audio stream present.

---

## Phase 4 — Publish hook (Days 9–10, opt-in)

**Deliverable:** `factory publish <outbox-dir>` posts to Instagram (`personal` brand only, gated by `allow_auto_publish: true` in `brands/personal.yaml`).

- Reuse `social-media-business-account/scripts/publisher/instagram_publisher.py` patterns — but **do not import**. Copy minimal client; ask before extracting a shared package.
- Dry-run mode default; `--confirm` required for an actual post.
- LinkedIn hook deferred — reopens only when a work brand is added.

---

## Phase 5 — Theme auto-ingest (stretch)

**Deliverable:** themes can be auto-suggested from GitHub releases / RSS / JIRA changelog.

- New `ingest/` package with one collector per source.
- LLM-assisted ranking against brand audience; output candidate themes to `themes/<brand>.suggested.yaml` for operator review.
- **Never** auto-render from auto-ingested themes — operator promotes them manually.

---

## Test matrix

| Phase | Pass criteria |
|---|---|
| 1 | Brand/theme load · brief build · ComfyUI client (respx-mocked) · outbox write atomic · CLI smoke test against live Windows host |
| 2 | All 4 formats render · captions within platform limits · parallel job queueing doesn't dead-lock |
| 3 | Ken Burns MP4 valid, ≤ 12 MB, audio present · video re-renders with same seed |
| 4 | IG dry-run path · live post only with `--confirm` · `allow_auto_publish=false` blocks publish |
| 5 | Each ingestor produces well-formed suggested themes · no auto-promotion to render |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Windows host unreachable | All renders fail | Pre-flight `/system_stats` check; clear error; queue retry locally |
| ComfyUI workflow drift | Silent bad output | Workflow JSONs versioned in-repo; shape-asserted in tests |
| Brand bleed if a second brand is added later | Wrong tone published | Brand loaded once per CLI invocation; renderer takes Brand by value, not by mutation. Test enforces this when a second brand lands. |
| LLM hallucinated captions | Reputational | Phase 2 captions require operator review; Phase 4 publish gated by `--confirm` |
| IG long-lived token expiry (60 days) | Phase 4 publish broken | Document refresh; surface expiry in ARBITER dashboard (later) |
| `outbox/` bloat | Disk fill | Phase 1 adds `factory prune --older-than 30d` |

---

## Cost: $0/month
- ComfyUI on existing RTX 3080. `phi4` local via Ollama. `edge-tts` free. Instagram Graph API free tier.

---

## Timeline (operator-bandwidth dependent)

| Phase | Duration | Deliverable |
|---|---|---|
| 1 | 3 days | Single-brand, single-format MVP, green tests |
| 2 | 2 days | Multi-format + captions |
| 3 | 3 days | Video (Ken Burns + TTS) |
| 4 | 2 days | Publish hooks, dry-run default |
| 5 | TBD | Theme auto-ingest |
