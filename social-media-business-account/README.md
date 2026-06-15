# Social Media Trend Analyzer Agent 🎯

**Free-tier AI-powered trend analysis for parent-focused content discovery**

## Overview

Automated daily trend analysis that surfaces hashtags, audio trends, content hooks, and video ideas tailored for parent-facing children's learning content.

**Target Audience**: Parents & caregivers (not children directly)  
**Content Focus**: Early years learning, bedtime routines, emotional literacy, calm parenting, screen-time guidance

---

## Architecture

```
GitHub Actions (Daily Cron)
        ↓
Trend Collectors (TikTok, YouTube, Instagram, Google Trends)
        ↓
SQLite Storage (local) or JSON files
        ↓
Scoring Engine (relevance + safety filters)
        ↓
LLM Analysis (Claude/GPT/Gemini)
        ↓
Markdown Daily Report
        ↓
Optional: Slack/Email/Notion notification
```

---

## Cost: $0/month

- **GitHub Actions**: 2,000 free minutes/month (this uses ~5 min/day = 150 min/month)
- **YouTube Data API**: 10,000 quota units/day (free)
- **TikTok Creative Center**: Free web scraping or manual export
- **Instagram Graph API**: Free with Meta Developer account
- **LLM**: Use Claude Code Pro or Windsurf free tier locally
- **Storage**: SQLite (local) or commit JSON to repo

---

## Quick Start

### 1. Install Dependencies

```bash
cd social-media-business-account
pip install -r requirements.txt
```

### 2. Configure API Keys

Copy `.env.example` to `.env` and add your keys:

```bash
cp .env.example .env
```

Required:
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` (choose one)
- `YOUTUBE_API_KEY` (free from Google Cloud Console)
- `META_ACCESS_TOKEN` (optional, for Instagram)

### 3. Run Manually

```bash
python scripts/generate_trend_report.py
```

This generates `reports/YYYY-MM-DD-trend-report.md`

### 4. Enable Daily Automation

Push to GitHub with secrets configured:

```bash
gh secret set OPENAI_API_KEY
gh secret set YOUTUBE_API_KEY
gh secret set META_ACCESS_TOKEN
```

GitHub Actions will run daily at 8 AM UTC.

---

## What It Analyzes

| Source | What We Collect | Notes |
|--------|----------------|-------|
| **TikTok Creative Center** | Trending hashtags, songs, creators | Manual export or scraping |
| **YouTube Data API** | Most popular videos by region | `chart=mostPopular` |
| **Instagram Graph API** | Hashtag recent/top media | Hashtag search endpoint |
| **Google Trends** | Parent search intent trends | Manual CSV export or API alpha |
| **Your Posts** | Historical performance data | Most valuable over time |

---

## Scoring Logic

Each trend is scored on:

```
Trend Score =
  platform_growth_score          (0-20)
+ relevance_to_parenting_score   (0-30)
+ content_fit_score              (0-20)
+ commercial_safety_score        (0-15)
+ low_competition_score          (0-15)
- brand_risk_score               (0-20)
- child_safety_risk_score        (0-20)
```

**Prioritize:**
- Discoverability
- Parent relevance
- Calm tone
- Early years learning
- Co-engagement themes

**Avoid:**
- Manipulative tactics
- Controversial parenting debates (unless educational)
- Overstimulating content
- Unverified developmental claims

---

## Output Format

Daily report includes:

1. **Best Content Opportunities** (top 5 trends)
   - Why it matters
   - Suggested hook
   - Suggested visual
   - Suggested caption
   - Hashtag strategy (3 layers)
   - Audio/music direction
   - Risk level

2. **Hashtag Strategy**
   - 2 broad discovery hashtags
   - 4 niche relevance hashtags
   - 2 problem/intent hashtags
   - 1 branded hashtag

3. **Audio Recommendations**
   - Calm instrumentals
   - Commercial-safe music
   - Bedtime-appropriate vibes

4. **Risk Warnings**
   - Brand safety alerts
   - Child privacy concerns

---

## Project Structure

```
social-media-business-account/
├── README.md                     # This file
├── requirements.txt              # Python dependencies
├── .env.example                  # API key template
├── config/
│   ├── brand_guidelines.yaml     # Parent-focused content rules
│   ├── seed_hashtags.yaml        # Initial hashtags to track
│   └── prompt_templates.yaml     # LLM system prompts
├── scripts/
│   ├── generate_trend_report.py  # Main orchestrator
│   ├── collectors/
│   │   ├── tiktok_collector.py   # TikTok Creative Center
│   │   ├── youtube_collector.py  # YouTube Data API
│   │   ├── instagram_collector.py # Instagram Graph API
│   │   └── google_trends_collector.py
│   ├── scoring/
│   │   ├── trend_scorer.py       # Scoring engine
│   │   └── safety_filters.py     # Risk detection
│   └── llm/
│       ├── analyzer.py           # LLM analysis layer
│       └── report_generator.py   # Markdown output
├── data/
│   ├── trends.db                 # SQLite storage
│   └── historical/               # Past performance data
├── reports/                      # Daily Markdown reports
└── .github/
    └── workflows/
        └── daily-trend-report.yml # GitHub Actions automation
```

---

## Next Steps

1. **MVP (Version 1)**: Manual CSV exports + YouTube API + LLM → Markdown report
2. **Version 2**: Store trend history, detect rising hashtags, compare your posts
3. **Version 3**: Add dashboard, competitor tracking, content calendar

---

## Example Report

See `reports/example-trend-report.md` for sample output.
