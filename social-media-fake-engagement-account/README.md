# Grow with Freya — Engagement Hub

> Your ReplySync + GoHighLevel replacement. Responds to real comments in your brand voice,
> tracks every engager as a CRM contact, and moves them through a pipeline from stranger to customer —
> all automatically, for £0/month.

---

## What this does

Every time a real parent comments on your Instagram or Facebook post, this system:

1. **Reads the comment** in real time (or every 15 minutes on cron)
2. **Classifies it** — is it a question, a worry, a compliment, a story?
3. **Generates a reply** in your brand voice — warm, reassuring, specific to what they said
4. **Posts the reply** back to their comment automatically
5. **Adds them to your CRM** — they become a named contact with full interaction history
6. **Triggers a DM sequence** if their comment mentions bedtime, screen time, the app, or emotions
7. **Advances their pipeline stage** — from Discovered → Engaged → Warm → Lead → Customer

---

## Before you start — what you need

| Requirement | Where to get it | Free? |
|---|---|---|
| Instagram Professional account | Convert in Instagram settings | ✅ |
| Facebook Page | facebook.com/pages/create | ✅ |
| Meta Developer account | developers.facebook.com | ✅ |
| Meta App (with Instagram + Messenger) | Meta Developer Console | ✅ |
| OpenAI API key | platform.openai.com | Pay per use (minimal) |
| Python 3.11+ | python.org | ✅ |
| Railway account (for webhook) | railway.app | ✅ Free tier |

---

## Part 1 — Meta API Setup

This is the only complex part. Do it once and you never touch it again.

### Step 1: Create a Meta App

1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Click **My Apps → Create App**
3. Choose **Business** type
4. Name it anything (e.g. "Grow with Freya Hub")

### Step 2: Add Instagram Graph API

1. Inside your app → **Add Product → Instagram Graph API**
2. Go to **Instagram Graph API → Settings**
3. Add your Instagram Professional account
4. Generate a **User Access Token** with these permissions:
   - `instagram_basic`
   - `instagram_manage_comments`
   - `instagram_manage_messages`
   - `pages_read_engagement`
5. Convert it to a **Long-Lived Token** (lasts 60 days, refreshable):
   ```
   GET https://graph.facebook.com/oauth/access_token
     ?grant_type=fb_exchange_token
     &client_id={app_id}
     &client_secret={app_secret}
     &fb_exchange_token={short_lived_token}
   ```
6. Copy the token → this is your `META_ACCESS_TOKEN`

### Step 3: Get your Instagram Account ID

```
GET https://graph.instagram.com/v21.0/me?fields=id,username&access_token=YOUR_TOKEN
```

Copy the `id` → this is your `META_INSTAGRAM_ACCOUNT_ID`

### Step 4: Get your Facebook Page token

1. In your Meta App → **Tools → Graph API Explorer**
2. Select your Page from the dropdown
3. Click **Generate Access Token**
4. Copy → this is your `FB_PAGE_ACCESS_TOKEN`
5. Your `FB_PAGE_ID` is visible in your Facebook Page settings under **About**

---

## Part 2 — Local Setup

```bash
cd social-media-fake-engagement-account

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Copy and fill in your config
cp .env.example .env
notepad .env                 # Windows
```

Fill in `.env`:

```env
OPENAI_API_KEY=sk-...
META_ACCESS_TOKEN=EAAxxxx...
META_INSTAGRAM_ACCOUNT_ID=17841...
META_APP_SECRET=abc123...
FB_PAGE_ID=123456...
FB_PAGE_ACCESS_TOKEN=EAAxxxx...
WEBHOOK_VERIFY_TOKEN=growwithfreya_webhook_token
```

### Test it works

```bash
python scripts/orchestrator.py
```

You should see output like:
```
2026-06-12 10:00:01 [INFO] Engagement Hub — polling run started
2026-06-12 10:00:02 [INFO] Instagram: 3 new comments found.
2026-06-12 10:00:02 [INFO] Facebook: 1 new comments found.
2026-06-12 10:00:04 [INFO] Replied to sarah_mumof3 [concern]
2026-06-12 10:00:05 [INFO] Sequence 'bedtime_help' queued for contact 7
2026-06-12 10:00:06 [INFO] Pipeline: {'discovered': 12, 'engaged': 4, 'warm': 1}
```

---

## Part 3 — Running Modes

### Mode A: Polling (simplest — Windows Task Scheduler)

Runs every 15 minutes. Catches everything within a 20-minute window.
No deployment needed — runs entirely on your Windows PC.

**Setup:**
1. Open **Task Scheduler** → Create Basic Task
2. Name: `Grow with Freya — Engagement Hub`
3. Trigger: Daily, repeat every **15 minutes** for 1 day
4. Action: Start a program
   - Program: `C:\path\to\venv\Scripts\python.exe`
   - Arguments: `scripts\orchestrator.py`
   - Start in: `C:\path\to\social-media-fake-engagement-account`

### Mode B: Webhooks (best — real-time, deploy to Railway)

Responds to comments within seconds. Recommended for best parent experience.

**Deploy to Railway (free):**

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

Railway gives you a public HTTPS URL like `https://your-app.railway.app`

**Register with Meta:**
1. Meta Developer Console → your App → **Webhooks**
2. Add callback URL: `https://your-app.railway.app/webhook`
3. Verify token: `growwithfreya_webhook_token` (must match your `.env`)
4. Subscribe to fields:
   - **Instagram**: `comments`, `messages`
   - **Page**: `feed`, `messages`
5. Click **Verify and Save**

**Run locally (for testing):**
```bash
uvicorn scripts.webhook:app --reload --port 8000
# Use ngrok to expose: ngrok http 8000
```

---

## Part 4 — What you'll see day to day

### Comment replies

When a parent comments *"I feel so guilty about screen time"*, within seconds (webhook)
or within 15 minutes (polling) they receive:

> *"Oh Sarah, I hear you — that feeling is so real and so exhausting.*
> *You're not failing. The fact that you're worried about this already*
> *tells me so much about the parent you are. 💛"*

Then 2 hours later, they get a DM:

> *"Hi Sarah — I saw your comment about screen time and I just wanted to say:*
> *the guilt you're feeling? That's your love showing up...*"*

### Your CRM

Check who's in your pipeline at any time:

```bash
# From Python
python -c "
from scripts.crm import CRM
crm = CRM('data/engagement.db')
print(crm.pipeline_summary())
"
```

Output:
```python
{'discovered': 47, 'engaged': 12, 'warm': 5, 'lead': 2, 'customer': 0}
```

Or via the webhook server dashboard (if deployed):
```
GET https://your-app.railway.app/pipeline
```

### Review queue

Some comments are held for your manual review — never auto-replied:
- **Negative / hostile** comments
- **Generic** reactions (emojis, "love this")
- **Escalated** keywords (safeguarding, legal, medical)

Check the database to see them:
```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/engagement.db')
rows = conn.execute(\"SELECT username, content, comment_type FROM interactions i JOIN contacts c ON i.contact_id=c.id WHERE reply_sent IS NULL AND escalated=0\").fetchall()
for r in rows: print(r)
"
```

### Logs

All activity is logged to `logs/engagement.log`:
```
tail -f logs/engagement.log      # Mac/Linux
Get-Content logs\engagement.log -Wait   # Windows PowerShell
```

---

## Part 5 — Customising

### Change how replies sound

Edit `config/reply_frameworks.yaml`:
- `brand_voice` — what to always/never say
- `comment_types` — structure and example for each reply type
- `escalation_keywords` — words that flag for human review
- `dm_trigger_keywords` — words that start a DM sequence

### Change DM sequences

Edit `config/dm_sequences.yaml`:
- Add new sequences under `sequences:`
- Each sequence has `messages:` with `day:`, `delay_hours:`, and `message:`
- Add new keyword triggers under `dm_trigger_keywords:` in `reply_frameworks.yaml`

### Stop a sequence for someone manually

```python
from scripts.crm import CRM
crm = CRM('data/engagement.db')
contact = crm.get_contact('instagram', 'their_ig_user_id')
crm.stop_sequences_for_contact(contact['id'])
```

---

## Cost breakdown

| Component | Cost |
|---|---|
| OpenAI GPT-4o | ~£0.01 per 10 comments classified + replied |
| Railway webhook hosting | Free tier (sufficient for this scale) |
| Meta APIs | Free |
| Storage (SQLite) | Free |
| **Total at 100 comments/day** | **~£0.10/day** |

---

## Pipeline stage definitions

| Stage | Meaning | What triggers it |
|---|---|---|
| **Discovered** | First ever comment or like | Automatic on first contact |
| **Engaged** | Has commented 3+ times | Interaction count ≥ 3 |
| **Warm** | Clicked link or saved a post | Webhook event or manual tag |
| **Lead** | Replied to a DM or signed up | DM reply detected |
| **Trial** | Downloaded the app | Manual update or app webhook |
| **Customer** | Converted to paid | Manual update |
