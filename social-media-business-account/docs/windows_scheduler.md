# Windows Task Scheduler Setup

Run the orchestrator every 30 minutes automatically.

## Method 1: Task Scheduler (Recommended)

1. Open **Task Scheduler** (search in Start menu)
2. Click **Create Basic Task**
3. Name: `Grow with Freya - Content Pipeline`
4. Trigger: **Daily**
5. Click **Next** → set start time to `07:00`
6. Action: **Start a program**
7. Program: `C:\path\to\social-media-business-account\venv\Scripts\python.exe`
8. Arguments: `scripts/orchestrator.py`
9. Start in: `C:\path\to\social-media-business-account`
10. Finish, then open the task and edit **Triggers**:
    - Edit the daily trigger
    - Check **Repeat task every: 30 minutes**
    - For a duration of: **1 day**

This runs the orchestrator every 30 min. It checks the schedule and only
posts when a slot is due — so running frequently is safe.

## Method 2: PowerShell Script (Alternative)

Create `run_pipeline.ps1`:
```powershell
$env:PATH += ";C:\path\to\ffmpeg\bin"
Set-Location "C:\path\to\social-media-business-account"
& ".\venv\Scripts\python.exe" "scripts\orchestrator.py"
```

Then schedule this script instead of calling Python directly.

## Method 3: Windows Service (Advanced)

For production reliability, wrap the orchestrator as a Windows service
using NSSM (Non-Sucking Service Manager):

```bash
# Download NSSM from https://nssm.cc
nssm install "GrowWithFreya" "C:\path\to\venv\Scripts\python.exe" "scripts\orchestrator.py"
nssm set "GrowWithFreya" AppDirectory "C:\path\to\social-media-business-account"
nssm start "GrowWithFreya"
```

## Verifying It Works

Check logs after first scheduled run:
```
logs\orchestrator.log
```

Expected output:
```
2026-06-12 07:00:01 [INFO] Orchestrator starting
2026-06-12 07:00:02 [INFO] Queue depth 0 < 2. Generating new content...
2026-06-12 07:00:02 [INFO] Generating reel for instagram @ 2026-06-12 07:00:00
2026-06-12 07:00:05 [INFO] Brief: screen time reassurance — Hook: You're not failing...
2026-06-12 07:00:45 [INFO] Job submitted: abc123. Waiting...
2026-06-12 07:02:10 [INFO] ComfyUI generation complete: data/content/raw/gwf_00001.png
2026-06-12 07:02:30 [INFO] Video ready: data/content/videos/gwf_00001_reel.mp4
2026-06-12 07:02:31 [INFO] Queued: gwf_00001_reel.mp4
2026-06-12 07:02:31 [INFO] Orchestrator complete
```
