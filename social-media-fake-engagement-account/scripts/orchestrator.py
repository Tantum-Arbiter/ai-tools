"""
Engagement Hub Orchestrator
Cron entry point (every 15 minutes via Windows Task Scheduler or GitHub Actions).
Polls for new comments/DMs, processes them, sends due DMs.
Use this when webhooks are not available or as a safety net alongside them.
"""
import os
import sys
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from scripts.crm import CRM
from scripts.monitor import CommentMonitor
from scripts.reply_engine import ReplyEngine
from scripts.dm_automation import DMAutomation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(ROOT / "logs" / "engagement.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

CONFIG_DIR = ROOT / "config"
DB_PATH = os.getenv("ENGAGEMENT_DB_PATH", str(ROOT / "data" / "engagement.db"))


def run():
    log.info("=" * 60)
    log.info("Engagement Hub — polling run started")

    crm = CRM(DB_PATH)
    monitor = CommentMonitor()
    reply_engine = ReplyEngine(CONFIG_DIR)
    dm_auto = DMAutomation(crm, CONFIG_DIR)

    # ── Step 1: Poll for new comments and DMs ────────────────────────
    events = monitor.poll_all(since_minutes=20)
    log.info(f"Found {len(events)} new events across all platforms.")

    # ── Step 2: Process each event ───────────────────────────────────
    for event in events:
        try:
            _process_event(event, crm, reply_engine, dm_auto)
        except Exception as e:
            log.error(f"Failed to process event {event.get('comment_id')}: {e}", exc_info=True)

    # ── Step 3: Send any DMs that are now due ────────────────────────
    dm_auto.send_due_dms()

    # ── Step 4: Log pipeline summary ─────────────────────────────────
    summary = crm.pipeline_summary()
    log.info(f"Pipeline: {summary}")

    crm.close()
    log.info("Engagement Hub — run complete.")


def _process_event(event: dict, crm: CRM, reply_engine: ReplyEngine, dm_auto: DMAutomation):
    platform = event["platform"]
    event_type = event.get("type", "comment")
    sender = event.get("user", {})

    # Upsert contact into CRM
    contact = crm.upsert_contact(
        platform=platform,
        platform_id=sender.get("platform_id", ""),
        username=sender.get("username", ""),
        display_name=sender.get("username", ""),
    )

    text = event.get("text", "")

    # If this is a DM reply from them — stop all sequences immediately
    if event_type == "dm_received":
        crm.stop_sequences_for_contact(contact["id"])
        crm.log_interaction(contact_id=contact["id"], platform=platform,
                            type="dm_received", content=text)
        log.info(f"DM reply from {contact.get('username')} — sequences stopped.")
        return

    # Log the comment interaction
    interaction_id = crm.log_interaction(
        contact_id=contact["id"],
        platform=platform,
        type="comment",
        content=text,
        media_id=event.get("media_id"),
        comment_id=event.get("comment_id"),
    )

    # Classify + generate reply
    result = reply_engine.process_comment(event, contact)
    classification = result["classification"]

    # Update interaction record with classification
    crm.conn.execute(
        "UPDATE interactions SET sentiment=?, comment_type=?, escalated=? WHERE id=?",
        (classification["sentiment"], classification["comment_type"],
         1 if classification.get("escalate") else 0, interaction_id)
    )
    crm.conn.commit()

    if classification.get("escalate"):
        log.warning(f"ESCALATED comment from {contact.get('username')}: {text[:80]}")
        return

    # Post reply to comment
    if result["reply"]:
        try:
            dm_auto.post_comment_reply(platform, event["comment_id"], result["reply"])
            crm.mark_reply_sent(interaction_id, result["reply"])
            log.info(f"Replied to {contact.get('username')} [{classification['comment_type']}]")
        except Exception as e:
            log.error(f"Failed to post reply: {e}")
    else:
        log.info(f"Comment from {contact.get('username')} queued for human review.")

    # Trigger DM sequences based on keyword matches
    dm_auto.trigger_for_event(contact, result["triggered_sequences"])

    # Check if pipeline stage should advance
    dm_auto.check_pipeline_triggers(contact)


if __name__ == "__main__":
    run()
