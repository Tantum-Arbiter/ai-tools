"""Standalone FastAPI server for work-ai-tools.

Run with:
    cd work-ai-tools
    uvicorn work_ai.server:app --port 8100 --reload
"""
from __future__ import annotations

import os
import secrets as _secrets
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).parent.parent / ".env")

from .routes import init_work_ai, router


@asynccontextmanager
async def lifespan(app: FastAPI):
    secret_hex = os.getenv("DAYJOB_HMAC_SECRET", "")
    if len(secret_hex) >= 64:
        secret = bytes.fromhex(secret_hex)
    else:
        secret = _secrets.token_bytes(32)
        print("[WORK-AI] DAYJOB_HMAC_SECRET not set — using ephemeral secret")

    init_work_ai(secret)
    print("[WORK-AI] Server ready")
    yield


app = FastAPI(
    title="work-ai-tools",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "work-ai-tools"}


@app.get("/api/llm/status")
async def llm_status() -> dict:
    import httpx

    base_url = os.getenv("WORK_AI_LLM_BASE_URL", "http://localhost:11434")
    model = os.getenv("WORK_AI_LLM_MODEL", "phi4:14b")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base_url}/api/tags")
            resp.raise_for_status()
            tags = resp.json()
            models = [m.get("name", "") for m in tags.get("models", [])]
            return {
                "ollama": "connected",
                "configured_model": model,
                "available_models": models,
                "model_loaded": any(model in m for m in models),
            }
    except Exception as exc:
        return {
            "ollama": "unavailable",
            "error": str(exc),
            "configured_model": model,
        }
