# Grow with Freya — Complete Setup Guide
### From zero to fully automated content creation and engagement

---

## What you'll have at the end

| System | What it does |
|---|---|
| **Content Pipeline** | Generates images and Reels using AI, posts them to Instagram and YouTube automatically at the best times |
| **Engagement Hub** | Reads every comment on your posts, replies in your brand voice, tracks every commenter as a CRM contact, sends follow-up DMs automatically |

Both run on your Windows PC (RTX 3080) with no monthly platform fees.

---

## Before you start — what you need

Go and create accounts for these now. They are all free.

- [ ] **Windows PC with RTX 3080** (you have this)
- [ ] **Instagram Professional account** — convert in Instagram app: Profile → Settings → Account → Switch to Professional
- [ ] **Facebook Page** for Grow with Freya — facebook.com/pages/create
- [ ] **Meta Developer account** — developers.facebook.com (log in with Facebook)
- [ ] **Google account** — for YouTube and Google Cloud Console
- [ ] **YouTube channel** — youtube.com (use your Google account)
- [ ] **OpenAI account** — platform.openai.com (you already pay for GPT Pro)
- [ ] **Railway account** — railway.app (for the webhook server, free tier)

---

## Part 1 — Install everything on your Windows PC

Do these once. They never need repeating.

### 1.1 Install Python

1. Go to [python.org/downloads](https://python.org/downloads)
2. Download **Python 3.12** (the big yellow button)
3. Run the installer
4. **IMPORTANT:** On the first screen, tick **"Add Python to PATH"** before clicking Install
5. When done, open **Command Prompt** (search "cmd" in Start menu) and type:
   ```
   python --version
   ```
   You should see `Python 3.12.x`. If you do, Python is working.

### 1.2 Install Git

1. Go to [git-scm.com/download/win](https://git-scm.com/download/win)
2. Download and run the installer — click Next through everything, defaults are fine
3. In Command Prompt, verify:
   ```
   git --version
   ```

### 1.3 Install FFmpeg

FFmpeg converts images into video. Open **PowerShell** (search "PowerShell" in Start menu) and run:

```powershell
winget install Gyan.FFmpeg
```

Close and reopen PowerShell, then verify:
```powershell
ffmpeg -version
```

You should see a wall of text starting with `ffmpeg version`. That means it worked.

> If `winget` gives an error, download manually from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) —
> get `ffmpeg-release-essentials.zip`, extract it to `C:\ffmpeg`, then add `C:\ffmpeg\bin` to your Windows PATH.
> (Search "environment variables" in Start menu → Edit system environment variables → PATH → New → `C:\ffmpeg\bin`)

### 1.4 Install ComfyUI (the image generation model)

ComfyUI is the software that runs Stable Diffusion on your RTX 3080 to generate images.

1. Go to [github.com/comfyanonymous/ComfyUI/releases](https://github.com/comfyanonymous/ComfyUI/releases)
2. Download `ComfyUI_windows_portable_nvidia.7z` (the latest release)
3. You need 7-Zip to extract it — download from [7-zip.org](https://www.7-zip.org) if you don't have it
4. Extract to `C:\ComfyUI`
5. Inside `C:\ComfyUI` you should see `run_nvidia_gpu.bat`

### 1.5 Download a model checkpoint

The checkpoint is the actual AI model that generates the images. Think of ComfyUI as the engine and the checkpoint as the fuel.

**Recommended: DreamShaper 8** — photorealistic, warm, excellent for people/home scenes

1. Go to [civitai.com/models/4384](https://civitai.com/models/4384)
2. Click **Download** next to DreamShaper 8 (the `.safetensors` file, ~2GB)
3. Move the downloaded file to: `C:\ComfyUI\models\checkpoints\`

### 1.6 Test ComfyUI

1. Double-click `C:\ComfyUI\run_nvidia_gpu.bat`
2. A black terminal window opens — wait for it to show `To see the GUI go to: http://127.0.0.1:8188`
3. Open your browser and go to `http://localhost:8188`
4. You should see the ComfyUI interface with a node graph

ComfyUI is working. You can minimise it — it needs to stay open whenever the pipeline runs.

---

## Part 2 — Get your API keys

### 2.1 OpenAI API key

You already pay for GPT Pro, but the scripts use the **API** (slightly different from ChatGPT).

1. Go to [platform.openai.com](https://platform.openai.com)
2. Click your profile (top right) → **API keys**
3. Click **Create new secret key** → name it "Grow with Freya"
4. Copy the key — it starts with `sk-` — **save it somewhere safe, you only see it once**

> Add at least £5 credit under Billing. At ~£0.01 per post generated, £5 lasts months.

### 2.2 Meta API setup (Instagram + Facebook)

This takes about 30 minutes but you only do it once.

**Create a Meta App:**
1. Go to [developers.facebook.com](https://developers.facebook.com) → **My Apps → Create App**
2. Select **Other** → **Business** → Next
3. Name: `Grow with Freya Hub` → Create App

**Add Instagram Graph API:**
1. Inside your app dashboard → **Add Product** → find **Instagram Graph API** → Set Up
2. Left sidebar → **Instagram Graph API → Settings**
3. Under **User Token Generator** → click **Add or Remove Instagram Accounts**
4. Connect your Instagram Professional account

**Generate your tokens:**
1. Left sidebar → **Tools → Graph API Explorer**
2. In the top right dropdown, select your App (`Grow with Freya Hub`)
3. Click **Generate Access Token** — log in with Facebook when prompted
4. In the **Permissions** box, add these one by one:
   - `instagram_basic`
   - `instagram_manage_comments`
   - `instagram_manage_messages`
   - `pages_manage_posts`
   - `pages_read_engagement`
5. Click **Generate Access Token** again
6. Copy the token shown — this is your **short-lived token** (valid 1 hour)

**Convert to a long-lived token (valid 60 days):**

Open your browser and paste this URL, filling in your values:
```
https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=YOUR_APP_ID&client_secret=YOUR_APP_SECRET&fb_exchange_token=YOUR_SHORT_TOKEN
```

- `YOUR_APP_ID` — found in your app dashboard under App Settings → Basic
- `YOUR_APP_SECRET` — same page, click Show next to App Secret
- `YOUR_SHORT_TOKEN` — the token you just copied

The response gives you a new token. **This is your `META_ACCESS_TOKEN`** — save it.

**Get your Instagram Account ID:**

Paste this in your browser (replace YOUR_TOKEN):
```
https://graph.instagram.com/v21.0/me?fields=id,username&access_token=YOUR_TOKEN
```

The `id` in the response is your **`META_INSTAGRAM_ACCOUNT_ID`**.

**Get your Facebook Page ID and Page token:**
1. Go to your Facebook Page → **About** → scroll down to find **Page ID** — save it as `FB_PAGE_ID`
2. Back in Graph API Explorer → top dropdown → switch from your user to your **Page**
3. Click **Generate Access Token** → copy it → this is your **`FB_PAGE_ACCESS_TOKEN`**

**Get your App Secret:**
- App Dashboard → **App Settings → Basic** → click **Show** next to App Secret → copy it → `META_APP_SECRET`

### 2.3 YouTube API setup

**Get a YouTube API key (for reading trends):**
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click **Select a Project → New Project** → name it "Grow with Freya"
3. Left sidebar → **APIs & Services → Library**
4. Search **YouTube Data API v3** → click it → **Enable**
5. Left sidebar → **Credentials → Create Credentials → API Key**
6. Copy the key → this is your **`YOUTUBE_API_KEY`**

**Get YouTube OAuth credentials (for uploading videos):**
1. **Credentials → Create Credentials → OAuth Client ID**
2. Application type: **Desktop App** → name it "GwF Upload" → Create
3. Download the JSON file → open it → you need `client_id` and `client_secret`
4. These are your **`YOUTUBE_CLIENT_ID`** and **`YOUTUBE_CLIENT_SECRET`**

---

## Part 3 — Set up the Content Pipeline

### 3.1 Download the code

Open Command Prompt and run:
```cmd
cd C:\Users\YourName\Documents
git clone https://github.com/YOUR_USERNAME/ai-tools.git
cd ai-tools
```

> If you don't have it on GitHub yet, just navigate to wherever the folder already is:
> `cd C:\path\to\ai-tools`

### 3.2 Set up Python environment

```cmd
cd social-media-business-account
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install kokoro soundfile
```

You should see packages installing. When done, your prompt shows `(venv)` at the start.

### 3.3 Fill in your configuration

```cmd
copy .env.example .env
notepad .env
```

Fill in every value:

```env
# LLM
OPENAI_API_KEY=sk-...your key here...
OPENAI_MODEL=gpt-4o

# YouTube (reading trends only - for now)
YOUTUBE_API_KEY=AIza...your key here...
YOUTUBE_REGION_CODE=GB

# YouTube upload (OAuth - fill in after Part 5)
YOUTUBE_CLIENT_ID=your_client_id
YOUTUBE_CLIENT_SECRET=your_client_secret
YOUTUBE_REFRESH_TOKEN=fill_in_after_step_5

# Instagram posting
META_ACCESS_TOKEN=EAA...your long-lived token...
META_INSTAGRAM_ACCOUNT_ID=17841...your id...

# ComfyUI
COMFYUI_BASE_URL=http://localhost:8188
COMFYUI_OUTPUT_DIR=C:/ComfyUI/output
COMFYUI_CHECKPOINT=dreamshaper_8.safetensors

# Brand
BRAND_NAME=Grow with Freya
BRANDED_HASHTAG=#growwithfreya

# Storage
DB_PATH=data/state.db
CONTENT_OUTPUT_DIR=data/content
REPORTS_DIR=reports
```

Save and close Notepad.

### 3.4 One-time YouTube auth

This opens a browser window, asks you to log in to Google, and saves a refresh token. You only do this once.

```cmd
python scripts/auth/youtube_auth.py
```

A browser window opens. Log in with your Google account → Allow access. 

Back in the terminal you'll see:
```
YOUTUBE_REFRESH_TOKEN=1//0g...your token...
```

Copy that token and paste it into your `.env` file under `YOUTUBE_REFRESH_TOKEN=`.

### 3.5 Test the content pipeline

Make sure ComfyUI is running (`run_nvidia_gpu.bat`), then:

```cmd
python scripts/orchestrator.py
```

Watch the output. A successful run looks like:
```
[INFO] Orchestrator starting
[INFO] Today's fact [guilt_relief]: Good enough parenting...
[INFO] Queue depth 0 < 2. Generating new content...
[INFO] Generating reel for instagram @ 2026-06-12 07:00:00
[INFO] Brief generated: theme=bedtime routines, trigger=guilt_relief
[INFO] Submitting ComfyUI job: 1080x1920
[INFO] Job submitted: abc-123. Waiting...
[INFO] ComfyUI generation complete: data/content/raw/gwf_00001.png
[INFO] Generating TTS voiceover...
[INFO] Video ready: data/content/videos/gwf_00001_reel.mp4
[INFO] Queued: gwf_00001_reel.mp4
[INFO] Orchestrator complete
```

Check `data/content/videos/` — your first Reel should be there.

---

## Part 4 — Set up the Engagement Hub

Open a **new** Command Prompt window (keep the first one for content pipeline).

```cmd
cd C:\path\to\ai-tools\social-media-fake-engagement-account
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 4.1 Fill in configuration

```cmd
copy .env.example .env
notepad .env
```

```env
OPENAI_API_KEY=sk-...same key as before...
OPENAI_MODEL=gpt-4o
META_ACCESS_TOKEN=EAA...same long-lived token...
META_INSTAGRAM_ACCOUNT_ID=17841...same id...
META_APP_SECRET=...your app secret...
FB_PAGE_ID=123456...your page id...
FB_PAGE_ACCESS_TOKEN=EAA...your page token...
WEBHOOK_VERIFY_TOKEN=growwithfreya_webhook_token
ENGAGEMENT_DB_PATH=data/engagement.db
```

### 4.2 Test the engagement hub

```cmd
python scripts/orchestrator.py
```

Expected output:
```
[INFO] Engagement Hub — polling run started
[INFO] Instagram: 0 new comments found.
[INFO] Facebook: 0 new comments found.
[INFO] DMs: 0 sent, 0 skipped.
[INFO] Pipeline: {}
[INFO] Engagement Hub — run complete.
```

Zero comments is fine — there are none yet. Post something on Instagram, wait a minute, run it again and you should see the comment get picked up and replied to.

---

## Part 5 — Automate everything

### 5.1 Create a startup script

Create a file called `start_comfyui.bat` anywhere convenient (e.g. your Desktop):

```bat
@echo off
start "" "C:\ComfyUI\run_nvidia_gpu.bat"
echo ComfyUI starting...
```

### 5.2 Open Task Scheduler

Search **"Task Scheduler"** in the Windows Start menu and open it.

You need to create **3 tasks** — one to start ComfyUI, one for the content pipeline, one for the engagement hub.

---

**Task 1 — Start ComfyUI at boot**

| Field | Value |
|---|---|
| Name | `GwF — Start ComfyUI` |
| Trigger | At log on (runs when you log into Windows) |
| Action → Program | `C:\ComfyUI\run_nvidia_gpu.bat` |
| Run whether user is logged on | Yes |

---

**Task 2 — Content Pipeline**

Click **Create Basic Task** in the right panel.

| Field | Value |
|---|---|
| Name | `GwF — Content Pipeline` |
| Trigger | Daily |
| Start time | `06:50 AM` |
| Action | Start a program |
| Program/script | `C:\path\to\social-media-business-account\venv\Scripts\python.exe` |
| Arguments | `scripts\orchestrator.py` |
| Start in | `C:\path\to\social-media-business-account` |

After creating it, right-click the task → **Properties → Triggers** → Edit:
- Tick **Repeat task every:** `30 minutes`
- For a duration of: `1 day`

---

**Task 3 — Engagement Hub**

Repeat the same process:

| Field | Value |
|---|---|
| Name | `GwF — Engagement Hub` |
| Program/script | `C:\path\to\social-media-fake-engagement-account\venv\Scripts\python.exe` |
| Arguments | `scripts\orchestrator.py` |
| Start in | `C:\path\to\social-media-fake-engagement-account` |
| Start time | `07:00 AM` |
| Repeat every | `15 minutes` for `1 day` |

---

## Part 6 — Optional: Real-time webhooks (strongly recommended)

The polling setup above checks for comments every 15 minutes. Webhooks make it instant.

### 6.1 Deploy the webhook server to Railway

Install the Railway CLI:
```powershell
npm install -g @railway/cli
```

> If you don't have Node.js, install it first from [nodejs.org](https://nodejs.org)

Log in and deploy:
```cmd
cd social-media-fake-engagement-account
railway login
railway init
railway up
```

Railway gives you a URL like `https://your-app.up.railway.app`. Copy it.

### 6.2 Register with Meta

1. Meta Developer Console → your app → left sidebar → **Webhooks**
2. Click **Add Callback URL**
3. Callback URL: `https://your-app.up.railway.app/webhook`
4. Verify Token: `growwithfreya_webhook_token` (must match your `.env`)
5. Click **Verify and Save**
6. Under **Subscriptions**, click **Add Subscriptions** next to **Instagram**:
   - Tick: `comments`, `messages`
7. Do the same for **Page**:
   - Tick: `feed`, `messages`

Comments now trigger replies within seconds instead of 15 minutes.

---

## Part 7 — What to check each day

You don't need to do anything daily — it all runs itself. But here's where to look to see it working.

### View today's content queue

```cmd
cd social-media-business-account
venv\Scripts\activate
python -c "
import sqlite3
conn = sqlite3.connect('data/state.db')
rows = conn.execute('SELECT platform, content_type, theme, status, scheduled_at FROM posts ORDER BY scheduled_at DESC LIMIT 10').fetchall()
for r in rows: print(r)
"
```

### View your engagement pipeline

```cmd
cd social-media-fake-engagement-account
venv\Scripts\activate
python -c "
from scripts.crm import CRM
crm = CRM('data/engagement.db')
print(crm.pipeline_summary())
"
```

### View comments waiting for your manual review

These are comments the AI flagged as needing a human — negative, escalated, or complex:

```cmd
python -c "
import sqlite3
conn = sqlite3.connect('data/engagement.db')
rows = conn.execute('''
  SELECT c.username, i.content, i.comment_type
  FROM interactions i JOIN contacts c ON i.contact_id = c.id
  WHERE i.reply_sent IS NULL AND i.escalated = 0
  ORDER BY i.created_at DESC
''').fetchall()
for r in rows: print(r)
"
```

### Watch the logs live

Open PowerShell and run:
```powershell
# Content pipeline
Get-Content C:\path\to\social-media-business-account\logs\orchestrator.log -Wait

# Engagement hub (new PowerShell window)
Get-Content C:\path\to\social-media-fake-engagement-account\logs\engagement.log -Wait
```

---

## Troubleshooting

| Problem | Most likely cause | Fix |
|---|---|---|
| `ComfyUI not reachable` | ComfyUI isn't running | Start `run_nvidia_gpu.bat` first |
| `No LLM configured` | Missing API key | Check `OPENAI_API_KEY` in `.env` |
| `META_ACCESS_TOKEN` errors | Token expired (60 days) | Re-generate in Graph API Explorer |
| Image generates but no video | FFmpeg not in PATH | Re-run `winget install Gyan.FFmpeg`, restart terminal |
| `YOUTUBE_REFRESH_TOKEN` error | Haven't run auth yet | Run `python scripts/auth/youtube_auth.py` |
| `0 new comments found` always | Wrong account ID | Double-check `META_INSTAGRAM_ACCOUNT_ID` |
| Task Scheduler not running | Wrong path in task | Right-click task → Run → check for errors |
| Posts queued but not publishing | CDN URL not set | Set `MEDIA_CDN_BASE_URL` (see Instagram CDN note below) |

### Instagram CDN note

Instagram requires images/videos to be at a public URL before it can post them.
You need one of:

- **Cloudflare R2** (recommended — free: 10GB storage) — [cloudflare.com/r2](https://www.cloudflare.com/developer-platform/r2/)
- **AWS S3 free tier** — 5GB free for 12 months

Once set up, add to your content pipeline `.env`:
```env
MEDIA_CDN_BASE_URL=https://your-bucket.r2.cloudflarestorage.com
```

---

## Token refresh reminder

Meta long-lived tokens expire after **60 days**. Set a calendar reminder.

When they expire:
1. Go to [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. Re-generate and re-exchange for a long-lived token (same steps as Part 2.2)
3. Update `META_ACCESS_TOKEN` and `FB_PAGE_ACCESS_TOKEN` in both `.env` files
4. Restart both Task Scheduler tasks

---

## Full file structure (for reference)

```
ai-tools/
├── SETUP_GUIDE.md                          ← you are here
│
├── social-media-business-account/          ← Content Pipeline
│   ├── .env                                ← your secrets (never commit)
│   ├── config/
│   │   ├── brand.yaml                      ← brand voice, psychology triggers
│   │   └── posting_schedule.yaml           ← when to post each day
│   ├── scripts/
│   │   ├── orchestrator.py                 ← main entry point (run this)
│   │   ├── brief_generator.py              ← GPT-4o writes content brief
│   │   ├── fact_finder.py                  ← GPT-4o searches for daily fact
│   │   ├── scheduler.py                    ← decides what to post when
│   │   ├── state_db.py                     ← tracks queue and posts
│   │   ├── generator/
│   │   │   ├── comfyui_client.py           ← talks to ComfyUI on localhost
│   │   │   └── video_assembler.py          ← FFmpeg + TTS = final Reel
│   │   ├── publisher/
│   │   │   ├── instagram_publisher.py      ← posts to Instagram
│   │   │   └── youtube_publisher.py        ← uploads to YouTube
│   │   └── auth/
│   │       └── youtube_auth.py             ← run once for OAuth token
│   └── data/
│       ├── state.db                        ← post queue and history
│       └── content/                        ← generated images and videos
│
└── social-media-fake-engagement-account/   ← Engagement Hub
    ├── .env                                ← your secrets (never commit)
    ├── config/
    │   ├── reply_frameworks.yaml           ← how to reply to each comment type
    │   └── dm_sequences.yaml               ← DM automation flows
    ├── scripts/
    │   ├── orchestrator.py                 ← main entry point (run this)
    │   ├── monitor.py                      ← polls IG + FB for comments
    │   ├── reply_engine.py                 ← GPT-4o generates replies
    │   ├── crm.py                          ← contact profiles + pipeline
    │   ├── dm_automation.py                ← sends DM sequences
    │   └── webhook.py                      ← real-time server (Railway)
    └── data/
        └── engagement.db                   ← contacts, interactions, DM queue
```
