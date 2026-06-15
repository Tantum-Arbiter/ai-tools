"""
Webhook Server — Grow with Freya Engagement Hub
FastAPI server that receives real-time events from Meta (Instagram + Facebook).
Deploy on any always-on service: Railway, Fly.io, Render (all have free tiers).
Meta requires HTTPS — these platforms provide it automatically.

Setup:
  1. Deploy this server (get your public HTTPS URL)
  2. Go to Meta Developer Console → Webhooks
  3. Add callback URL: https://your-app.railway.app/webhook
  4. Set verify token (same as WEBHOOK_VERIFY_TOKEN in .env)
  5. Subscribe to: instagram → comments, messages
                   page → feed (comments), messages
"""
import os
import logging
import hmac
import hashlib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse

from scripts.crm import CRM
from scripts.monitor import CommentMonitor
from scripts.reply_engine import ReplyEngine
from scripts.dm_automation import DMAutomation

log = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "config"
DB_PATH = os.getenv("ENGAGEMENT_DB_PATH", "data/engagement.db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.crm = CRM(DB_PATH)
    app.state.reply_engine = ReplyEngine(CONFIG_DIR)
    app.state.dm_automation = DMAutomation(app.state.crm, CONFIG_DIR)
    log.info("Engagement Hub webhook server started.")
    yield
    app.state.crm.close()


app = FastAPI(title="Grow with Freya — Engagement Hub", lifespan=lifespan)


# ── Webhook verification (Meta requires this on setup) ────────────────
@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify.token"),
):
    expected = os.getenv("WEBHOOK_VERIFY_TOKEN", "growwithfreya_webhook_token")
    if hub_mode == "subscribe" and hub_verify_token == expected:
        log.info("Webhook verified by Meta.")
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed.")


# ── Incoming events ───────────────────────────────────────────────────
@app.post("/webhook")
async def receive_webhook(request: Request):
    # Verify signature
    raw_body = await request.body()
    _verify_signature(raw_body, request.headers.get("X-Hub-Signature-256", ""))

    payload = await request.json()
    crm: CRM = request.app.state.crm
    reply_engine: ReplyEngine = request.app.state.reply_engine
    dm_auto: DMAutomation = request.app.state.dm_automation

    for entry in payload.get("entry", []):
        # ── Instagram comments ──
        for change in entry.get("changes", []):
            field = change.get("field")
            value = change.get("value", {})

            if field == "comments":
                await _handle_comment(value, "instagram", crm, reply_engine, dm_auto)

            elif field == "feed" and value.get("item") == "comment":
                await _handle_comment(value, "facebook", crm, reply_engine, dm_auto)

        # ── DMs (Instagram Messaging / Facebook Messenger) ──
        for messaging in entry.get("messaging", []):
            if "message" in messaging and not messaging["message"].get("is_echo"):
                await _handle_dm(messaging, entry.get("id"), crm, dm_auto)

    return {"status": "ok"}


async def _handle_comment(value: dict, platform: str, crm: CRM,
                           reply_engine: ReplyEngine, dm_auto: DMAutomation):
    """Process a new comment event."""
    comment_id = value.get("id")
    text = value.get("text") or value.get("message", "")
    media_id = value.get("media", {}).get("id") or value.get("post_id", "")
    sender = value.get("from", {})

    if not text or not sender:
        return

    contact = crm.upsert_contact(
        platform=platform,
        platform_id=sender.get("id", ""),
        username=sender.get("username") or sender.get("name", ""),
        display_name=sender.get("name", ""),
    )

    interaction_id = crm.log_interaction(
        contact_id=contact["id"],
        platform=platform,
        type="comment",
        content=text,
        media_id=media_id,
        comment_id=comment_id,
    )

    result = reply_engine.process_comment({"text": text}, contact)
    classification = result["classification"]

    # Update interaction with classification
    crm.conn.execute(
        "UPDATE interactions SET sentiment=?, comment_type=?, escalated=? WHERE id=?",
        (classification["sentiment"], classification["comment_type"],
         1 if classification.get("escalate") else 0, interaction_id)
    )
    crm.conn.commit()

    # Post reply if auto-approved
    if result["reply"] and not classification.get("escalate"):
        dm_auto.post_comment_reply(platform, comment_id, result["reply"])
        crm.mark_reply_sent(interaction_id, result["reply"])

    # Trigger DM sequences if keywords matched
    dm_auto.trigger_for_event(contact, result["triggered_sequences"])

    # Advance pipeline
    dm_auto.check_pipeline_triggers(contact)


async def _handle_dm(messaging: dict, page_id: str, crm: CRM, dm_auto: DMAutomation):
    """When someone replies to a DM — stop their sequence immediately."""
    sender_id = messaging.get("sender", {}).get("id", "")
    if not sender_id or sender_id == page_id:
        return

    contact = crm.get_contact("instagram", sender_id) or crm.get_contact("facebook", sender_id)
    if contact:
        crm.stop_sequences_for_contact(contact["id"])
        crm.log_interaction(
            contact_id=contact["id"],
            platform="instagram",
            type="dm_received",
            content=messaging.get("message", {}).get("text", ""),
        )


def _verify_signature(body: bytes, signature_header: str):
    """Verify Meta webhook signature to prevent spoofed requests."""
    secret = os.getenv("META_APP_SECRET", "")
    if not secret:
        return  # Skip verification in dev
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=401, detail="Invalid signature.")


# ── Health + pipeline dashboard ───────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "Grow with Freya Engagement Hub"}


@app.get("/pipeline")
async def pipeline_summary(request: Request):
    crm: CRM = request.app.state.crm
    return crm.pipeline_summary()
