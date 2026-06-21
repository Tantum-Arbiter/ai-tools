# Agent Operating Rules — `arbiter-mission-control`

> Read this **after** the root `../CLAUDE.md` (project identity, principles, never-rules).
> This file covers **how to work**, not **what ARBITER is** (see `AGENT.md` for the runtime skills inventory).

---

## 1. Communication

- Be concise. Don't over-explain. No "Great question!", "You're absolutely right!", "Excellent point!".
- Brief acknowledgements only when they add clarity: "Got it.", "I see the issue."
- Skip acknowledgements when you can just proceed.
- Wrap code excerpts shown to the operator in `<augment_code_snippet>` XML tags (see root `CLAUDE.md`).

---

## 2. Test-Driven Development

### Workflow (non-negotiable for new code)
1. Find or create a **failing test first**.
2. Match the style of surrounding tests: same file → same `tests/` module → same fixture pattern.
3. Run the test, confirm it fails for the **right reason**.
4. Write the minimum code to make it pass.
5. Re-run, confirm green.
6. Refactor while tests stay green.
7. Run `pytest` and (when added) `mypy --strict <module>` before moving on.

### Legacy code (`server.py`)
`server.py` is ~500 KB and largely untested. It is **grandfathered** — do not block work demanding retroactive coverage. **However**: any function you touch must be extracted into a testable module (`scheduler.py`, `viz_selector.py`, etc.) with a covering test before the edit lands. Leave the call site in `server.py` as a thin shim importing the new module.

### Test Quality
- One behaviour per test. Test names describe behaviour, not implementation (e.g. `test_save_error_result`, not `test_save_method_branch_2`).
- Deterministic — no real timers, no real network, no real `datetime.utcnow()` without `freezegun` or injection.
- Prefer **`pytest.mark.parametrize`** over duplicating tests with different inputs.
- Variable name for the unit under test: **`under_test`** (adopt going forward; don't retrofit existing tests).
- Use AAA structure (Arrange / Act / Assert) with blank lines between sections.

### Tooling
| Concern | Tool |
|---|---|
| Runner | `pytest` (no `unittest.TestCase` for new tests) |
| Fixtures | `@pytest.fixture` — see `tests/test_persistence.py` for the in-memory SQLite pattern |
| Async tests | `pytest-asyncio` (add to `requirements.txt` when first needed; not yet present) |
| HTTP mocks | `respx` for `httpx` clients; `pytest-httpserver` for full-stack — not yet on classpath, add when first needed |
| Mocks | `unittest.mock` (`MagicMock`, `patch`) — match existing style |
| LLM mocks | Stub `openai`/`anthropic` clients at the boundary; never call real LLMs in tests |
| Coverage | `pytest-cov` (add when first needed) |

### FastAPI / Async Specifics
- **Never block the event loop.** No `time.sleep`, no `requests.get`, no sync DB calls in route handlers. Use `asyncio.sleep`, `httpx.AsyncClient`, and run sync SQLite calls via `asyncio.to_thread` or a dedicated worker.
- Test routes with `httpx.AsyncClient(app=app)` or `fastapi.testclient.TestClient` — pick one per test file and stay consistent.
- SSE endpoints (`/api/events`) must yield within a few seconds even when idle — send keepalive comments (`: ping\n\n`).
- Background jobs go through the existing asyncio scheduler — never spawn raw `threading.Thread` for new work.

---

## 3. Editing Rules

### Python
- **Type hints on all new code.** Use `from __future__ import annotations` at the top of new modules; prefer `list[str]` / `dict[str, int]` over `List` / `Dict`.
- **No `Any` without justification** — use `TypedDict`, `Protocol`, or `dataclass` instead.
- **No comments in code.** Use meaningful names and small functions. Existing docstrings stay; don't add new explanatory comments unless asked.
- Prefer **dataclasses / `pydantic.BaseModel`** for structured data over bare dicts crossing module boundaries.
- Prefer **composition** over inheritance, **iteration** over recursion. Ask before recursing.
- `pathlib.Path` over `os.path` strings for new code.
- Use **`httpx`** for HTTP (already on classpath); do **not** introduce `requests` for new code.
- Manage deps via `pip install <pkg> && pip freeze | grep <pkg> >> requirements.txt` — never hand-edit version constraints to silence resolver errors.
- When making assumptions or deferring work, write them in a plan file — ask which file to use.

### Frontend (current — `static/`)
- Vanilla JS, no build step. ES modules, `const`/`let`, no `var`.
- Co-locate styles in `static/style.css`; don't introduce a new CSS file without a reason.
- Chart.js is the only chart lib — see `VISUALIZATION_TOOLKIT.md` for selector mapping.
- Web Speech API for STT, `edge-tts` (server-rendered) for output — don't add browser TTS.

### Frontend (planned — React Native)
- When the RN migration starts, mirror `colearn/grow-with-freya/AGENTS.md` for conventions: Expo Router, Zustand + AsyncStorage, RN Reanimated, functional components, hooks at top level, `StyleSheet.create` co-located, offline-first wrappers around all fetches.
- Do not begin RN work without a top-level decision recorded in a `NEXT-PHASE-RN.md` doc — ask first.

### Secrets & Operator Data
- Read secrets from `.env` via `python-dotenv` (already wired). Never log token values or IMAP passwords — even at DEBUG.
- Operator PII (emails, RevenueCat, financial holdings, schedules) must default to the local LLM (`phi4`). Only route to remote LLMs when `LLM_PROVIDER=openai` is explicitly set AND the operator has opted into that flow.

---

## 4. Evidence-Based Analysis

Every claim about the codebase includes:
```
File: arbiter-mission-control/<relative path>
Lines X-Y:
    <exact snippet>
```
If you can't verify: **"⚠️ UNVERIFIED — Unable to confirm this claim in codebase"**. No guessing — ask.

---

## 5. Bug Analysis (use this skeleton)

**Description** — expected vs actual; when it started; affected surface (voice / dashboard / SSE / monitor).
**Reproduction** — exact voice command or HTTP request; reproducibility rate.
**Impact** — operator (signal lost, false alert, broken voice flow) / technical (route, module, similar bugs) / downstream (ComfyUI queue, schedules, persisted DB rows).
**Root cause** — entry point (route / wake-word / scheduler tick) → data flow → failure point → wrong assumption.
**Fix approach** — describe (don't implement unless asked); cite existing patterns; list downstream changes (tests, `persistence.py` schema, `static/jarvis.js` rendering, prompt files).

---

## 6. Refactoring

- **Extract from `server.py` when you touch it** (see §2 Legacy code).
- Migrate **all scenarios** in a test file before asking to delete the old one.
- **Always ask** before deleting a file — especially anything in `prompts/`, `static/`, or top-level JSON state files.
- Schema changes to `arbiter.db` need a migration in `persistence.py` and a test that exercises the upgrade path on a pre-migration fixture.

---

## 7. Commits

```
<message>

References: arbiter#<issue-number>  (or ai-tools#<issue-number>)
```
- Confirm all intended files are staged before committing. **Never** stage `.env`, `arbiter.db`, `static/comfyui_output/`, or anything matching `*.jks` / `credentials*.json`.
- `Co-authored-by:` for pairing.
- **Never push or open PRs without explicit permission** (root `CLAUDE.md`).

---

## 8. Build / Run Failure Analysis

1. **3-line summary** of the most likely cause.
2. **Failed checks** table: `| Check | Started | Completed | Duration |`.
3. **Per-failure**: suggested fix · relevant logs (collapse > 10 lines in `<details>`) · confidence (high/med/low). Low-confidence items skip detail.
4. For ComfyUI failures: include the queue ID, Windows host reachability check, and the workflow JSON name.
5. For voice failures: include browser console, `/api/events` SSE state, and whether wake-word vs clap path was used.

---

## 9. Commands

```bash
# Setup (once)
python -m venv venv
source venv/bin/activate                  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run locally
./start.sh                                # Mac/Linux
start.bat                                 # Windows

# Test
pytest                                    # all tests
pytest tests/test_persistence.py -v       # single file
pytest -k "save_and_retrieve"             # by name fragment
pytest --lf                               # rerun last failures

# Quick health checks
curl -s localhost:8000/api/agents | jq
curl -s localhost:8000/api/events         # SSE stream — Ctrl-C to exit

# Lint / type (add when first introduced)
# ruff check .
# mypy --strict <module>
```
