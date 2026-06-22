# Agent Operating Rules — `social-content-factory`

> Read this **after** the root `../CLAUDE.md` (project identity, principles, never-rules).
> This file covers **how to work in this module**, not **what it is** (see `README.md` + `delivery-plan.md`).

---

## 1. Module scope

`social-content-factory` produces social-media-ready images and (later) videos from a **theme brief**, rendering on the Windows RTX 3080 via ComfyUI. It is **brand-pluggable** and **review-gated** — no auto-publishing until Phase 4, and only opt-in per brand even then.

Sibling modules and their boundaries:
- `social-media-business-account/` — Grow with Freya pipeline. Do **not** import from it; if you find shared logic, ask before extracting into a third shared package.
- `arbiter-mission-control/` — operator dashboard. May surface factory status via SSE in a later phase; don't reach into its DB or routes from here.

---

## 2. Communication

- Be concise. No "Great question!", "You're absolutely right!".
- Wrap code excerpts shown to the operator in `<augment_code_snippet>` XML tags.
- When an assumption is being made, write it into `delivery-plan.md` under §"Open Questions" — never inline in code comments.

---

## 3. Test-Driven Development

### Workflow (non-negotiable for new code)
1. Create a **failing test first** in `tests/<mirror of source path>`.
2. Run, confirm failure for the right reason.
3. Write minimum code to pass.
4. Re-run green, refactor green, then `pytest` before moving on.

### Test quality
- One behaviour per test; AAA structure; deterministic.
- Unit under test variable: **`under_test`**.
- Prefer `pytest.mark.parametrize` over duplicated tests.
- **Never call ComfyUI, Ollama, or any LLM in tests.** Stub at the boundary:
  - `ComfyUIClient` — mock `httpx.AsyncClient` responses via `respx` (add to `requirements.txt` when first needed).
  - Local LLM (`phi4`) — stub the `chat()` function at module boundary.
- **Never write to `outbox/` in tests.** Use `tmp_path` for any file I/O.

### Tooling
| Concern | Tool |
|---|---|
| Runner | `pytest` |
| Async | `pytest-asyncio` (add when first needed) |
| HTTP mocks | `respx` for `httpx` |
| Image diff (Phase 2+) | `Pillow` + pixel-hash assertion, not perceptual diff |
| Coverage | `pytest-cov` (add when first needed) |

---

## 4. Editing Rules

### Python
- `from __future__ import annotations` at top of every new module.
- Type hints on all new code; no `Any` without justification (`TypedDict` / `Protocol` / `dataclass`).
- **No explanatory comments in code.** Meaningful names + small functions; docstrings only.
- `pydantic.BaseModel` for any structured data crossing module boundaries (brand, theme, brief, render result).
- `pathlib.Path` over `os.path`.
- `httpx.AsyncClient` for HTTP — never `requests`.
- `pip install <pkg> && pip freeze | grep <pkg> >> requirements.txt`. Never hand-edit version pins.
- Logging via `logging.getLogger(__name__)`. **Never log brand secrets, IG tokens, or full prompts containing PII** — log a prompt hash instead.

### ComfyUI workflows
- Workflow JSONs live under `workflows/<purpose>.json` (e.g. `workflows/image_sd35_base.json`).
- Edits to a workflow JSON must come with a test that loads it and asserts node-graph shape — the API is unforgiving and silent failures are easy.
- Use the same `BRAND_STYLE_SUFFIX` / `BRAND_NEGATIVE` shape as `social-media-business-account/scripts/generator/comfyui_client.py` but **per brand**, loaded from `brands/<key>.yaml`. Do not hardcode brand strings.

### Brand & theme YAML
- Schema lives in `schemas/brand.py` and `schemas/theme.py` as Pydantic models.
- Validate every YAML on load — fail fast on missing fields.
- A brand YAML must declare: `name`, `voice`, `audience`, `visual_style`, `negative_prompts`, `default_formats`, `allow_auto_publish` (bool, default false), `llm_provider` (default `phi4`).

### Secrets & operator data
- All secrets via `.env` + `python-dotenv`. Never commit `.env`.
- `outbox/`, `data/factory.db`, `workflows/local_*.json`, and `brands/*.private.yaml` are **gitignored** — confirm before committing.
- Operator PII (and any future workplace-brand content) routes to **local `phi4`** by default. A brand may set `llm_provider: openai` only with an explicit opt-in field; the loader must log the choice at INFO.

---

## 5. Evidence-based analysis

Every claim about the codebase includes:
```
File: social-content-factory/<relative path>
Lines X-Y:
    <exact snippet>
```
If you can't verify: **"⚠️ UNVERIFIED — Unable to confirm this claim in codebase"**. No guessing — ask.

---

## 6. Refactoring & deletion

- **Always ask** before deleting anything under `brands/`, `themes/`, `workflows/`, or `prompts/`.
- Schema changes to `data/factory.db` require a migration in `persistence.py` (when introduced) + a test exercising the upgrade path on a pre-migration fixture.
- Cross-module extraction (factoring shared logic with `social-media-business-account`) — **ask first**.

---

## 7. Commits

```
<message>

References: ai-tools#<issue-number>
```
- Never stage `.env`, `outbox/`, `data/factory.db`, `workflows/local_*.json`, or `brands/*.private.yaml`.
- `Co-authored-by:` for pairing.
- **Never push or open PRs without explicit operator permission** (root `CLAUDE.md`).

---

## 8. Build / run failure analysis

1. **3-line summary** of likely cause.
2. **Failed checks** table: `| Check | Started | Completed | Duration |`.
3. Per failure: suggested fix · relevant logs (collapse > 10 lines in `<details>`) · confidence (high/med/low).
4. For ComfyUI failures: include queue ID, Windows host reachability (`curl $COMFYUI_BASE_URL/system_stats`), and workflow JSON filename.
5. For brand/theme YAML failures: include the Pydantic validation error verbatim.

---

## 9. Commands

```bash
# Setup (once, on Mac orchestrator)
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run a single theme through the factory (Phase 1+)
python -m social_content_factory.cli render --brand personal --theme weekly-build

# Tests
pytest                                    # all
pytest tests/test_brand_loader.py -v
pytest -k "render_outputs_all_formats"

# Reach Windows ComfyUI host (sanity)
curl -s "$COMFYUI_BASE_URL/system_stats" | jq
```
