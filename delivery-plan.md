# Windsurf SWE-1.6 QA Agent — Delivery Plan

## Overview
Set up Windsurf SWE-1.6 as a free, headless QA agent running in Docker via [windsurfinabox](https://github.com/pfcoperez/windsurfinabox). Triggered by GitHub Actions on PRs across 4 projects: **voiceclonenarration**, **strickrbook**, **colearn**, and **photoshop-ai**.

## Architecture

```
PR opened/updated
       │
       ▼
GitHub Actions ──► docker run windsurfinabox ──► SWE-1.6 (free, 200 tok/s)
       │                    │
       │              mounts project repo
       │              reads windsurf-instructions.txt
       │              writes windsurf-output.txt
       │                    │
       ▼                    ▼
Parse output ◄──── "WORK-COMPLETED" signal
       │
       ▼
Post QA report as PR comment
```

## Prerequisites
- Windsurf free account (SWE-1.6 free for 3 months)
- Windsurf auth token (extracted from desktop app: Ctrl+Shift+P → "Provide auth token")
- Docker available in GitHub Actions runner
- GitHub Actions access on all 4 repos

## Phase 1: Build the Headless Windsurf Docker Image (Day 1)

### 1.1 Fork and customise windsurfinabox
```bash
gh repo fork pfcoperez/windsurfinabox --clone
cd windsurfinabox
```

### 1.2 Verify it builds and runs locally
```bash
docker build . -t windsurf-qa
mkdir -p /tmp/qa-workspace
echo "List all files and describe the project structure" > /tmp/qa-workspace/windsurf-instructions.txt
docker run --rm -it --name windsurf-qa \
  -e WINDSURF_TOKEN=$WINDSURF_TOKEN \
  -v ~/.config/Windsurf:/home/ubuntu/.config/Windsurf \
  -v /tmp/qa-workspace:/home/ubuntu/workspace \
  windsurf-qa
```

### 1.3 Verify output
```bash
cat /tmp/qa-workspace/windsurf-output.txt
# Should end with "WORK-COMPLETED"
```

## Phase 2: Create Project-Specific QA Prompts (Day 2)
QA instruction files are located in each project module under `ai-tools/<project>/qa-instructions.md`.
Copy the relevant file into the project repo as `windsurf-instructions.txt` before running.

## Phase 3: GitHub Actions Reusable Workflow (Day 3)

### 3.1 Create reusable workflow: `.github/workflows/windsurf-qa.yml`
```yaml
name: Windsurf SWE-1.6 QA
on:
  workflow_call:
    secrets:
      WINDSURF_TOKEN:
        required: true

jobs:
  qa:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4

      - name: Build windsurfinabox
        run: |
          git clone https://github.com/<your-fork>/windsurfinabox.git /tmp/windsurfinabox
          cd /tmp/windsurfinabox
          docker build . -t windsurf-qa

      - name: Prepare QA instructions
        run: cp .windsurf/qa-instructions.md ${{ github.workspace }}/windsurf-instructions.txt

      - name: Run Windsurf QA
        run: |
          docker run --rm --name windsurf-qa \
            -e WINDSURF_TOKEN=${{ secrets.WINDSURF_TOKEN }} \
            -v ${{ github.workspace }}:/home/ubuntu/workspace \
            windsurf-qa

      - name: Post QA results to PR
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const output = fs.readFileSync('windsurf-output.txt', 'utf8');
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `## 🏄 Windsurf SWE-1.6 QA Report\n\n${output}`
            });
```

### 3.2 Call from each project
In each project's `.github/workflows/pr.yml`:
```yaml
jobs:
  windsurf-qa:
    uses: <your-org>/.github/.github/workflows/windsurf-qa.yml@main
    secrets:
      WINDSURF_TOKEN: ${{ secrets.WINDSURF_TOKEN }}
```

## Phase 4: Test & Iterate (Day 4-5)

| Test | Pass Criteria |
|------|---------------|
| Docker image builds in CI | < 5 min |
| SWE-1.6 authenticates headlessly | No auth errors in logs |
| QA runs against voiceclonenarration | windsurf-output.txt contains findings |
| QA runs against strickrbook | windsurf-output.txt contains findings |
| QA runs against colearn | windsurf-output.txt contains findings |
| QA runs against photoshop-ai | windsurf-output.txt contains findings |
| PR comment posted | QA report visible on PR |
| Timeout handling | Job fails gracefully at 30 min |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| SWE-1.6 free tier expires (3 months) | QA stops working | Monitor expiry; evaluate $15/mo Pro or switch to free LLM API |
| Windsurf token expires | Auth failure | Rotate token, store in GitHub Secrets |
| windsurfinabox is community/early-stage | Breaking changes | Pin to specific commit SHA in Dockerfile |
| Headless Xvfb flaky on GitHub runners | Random failures | Add retry logic; increase timeout |
| Free tier rate limits (200 tok/s) | Slow QA | Keep prompts focused; parallelize across projects |
| Windsurf config mount requirement | Extra setup | Track windsurfinabox updates that remove this need |

## Cost: $0/month
- SWE-1.6: Free (3-month promo)
- GitHub Actions: Free tier (2,000 min/month private, unlimited public)
- Docker: No cost (built in CI)

## Timeline
| Phase | Duration | Deliverable |
|-------|----------|-------------|
| 1. Docker image | Day 1 | Working local headless Windsurf |
| 2. QA prompts | Day 2 | Per-project instruction files |
| 3. GitHub Actions | Day 3 | Reusable workflow, integrated in 4 repos |
| 4. Test & iterate | Day 4-5 | All 4 projects passing QA in CI |
