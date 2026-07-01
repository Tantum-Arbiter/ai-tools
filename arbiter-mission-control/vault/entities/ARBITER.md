---
type: entity
tags: [infrastructure, ai, dashboard]
updated: 2026-07-01
---

# ARBITER

Voice-first AI ops dashboard (J.A.R.V.I.S. persona) for managing [[Early Roots]] ventures.

## Architecture
- Backend: Python / FastAPI / SQLite
- Frontend: Vanilla HTML/JS (React Native migration planned)
- LLM: phi4:14b local via Ollama, Claude Haiku fallback
- TTS: edge-tts (en-GB-RyanNeural)
- Image gen: ComfyUI on Windows RTX 3080

## Key Features
- Wake-word voice activation ("Arbiter")
- CEO pipeline with multi-agent orchestration
- Real-time monitoring (GCP, RevenueCat, email, stocks)
- Scheduled briefings and proactive alerts
- ComfyUI image/video generation

## Hardware
- Mac M1 Pro (32 GB) — primary dev + runtime
- Windows RTX 3080 — ComfyUI rendering
