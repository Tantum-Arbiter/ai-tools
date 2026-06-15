"""
DM Automation — Grow with Freya Engagement Hub
Sends triggered DM sequences via Instagram Messaging API and Facebook Messenger.
ALWAYS stops immediately if the contact replies — never interrupts a real conversation.
"""
import os
import logging
import yaml
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from scripts.crm import CRM

log = logging.getLogger(__name__)

IG_API = "https://graph.instagram.com/v21.0"
FB_API = "https://graph.facebook.com/v21.0"


class DMAutomation:
    def __init__(self, crm: CRM, config_dir: Path):
        with open(config_dir / "dm_sequences.yaml") as f:
            self.config = yaml.safe_load(f)
        self.sequences = self.config.get("sequences", {})
        self.stage_triggers = self.config.get("pipeline_stage_triggers", {})
        self.crm = crm
        self.ig_token = os.getenv("META_ACCESS_TOKEN")
        self.ig_account_id = os.getenv("META_INSTAGRAM_ACCOUNT_ID")
        self.fb_page_token = os.getenv("FB_PAGE_ACCESS_TOKEN")

    # ── Trigger a sequence ────────────────────────────────────────────
    def trigger_sequence(self, contact: dict, sequence_name: str):
        """Enqueue all messages in a sequence for a contact."""
        if contact.get("dm_stopped"):
            log.info(f"Sequence skipped — contact {contact['id']} previously replied.")
            return

        if sequence_name not in self.sequences:
            log.warning(f"Unknown sequence: {sequence_name}")
            return

        # Don't re-trigger the same sequence twice
        if contact.get("dm_sequence") == sequence_name:
            log.debug(f"Sequence '{sequence_name}' already active for contact {contact['id']}.")
            return

        seq = self.sequences[sequence_name]
        now = datetime.utcnow()

        for msg_config in seq.get("messages", []):
            condition = msg_config.get("condition")
            if condition == "no_reply":
                # This step only sends if they haven't replied — enforced at send time
                pass

            day = msg_config.get("day", 0)
            delay_h = msg_config.get("delay_hours", 0)
            send_at = now + timedelta(days=day, hours=delay_h)

            text = self._render_message(msg_config["message"], contact)
            self.crm.queue_dm(
                contact_id=contact["id"],
                sequence_name=sequence_name,
                step=msg_config.get("day", 0),
                message_text=text,
                send_at=send_at,
            )

        # Mark active sequence on contact
        self.crm.conn.execute(
            "UPDATE contacts SET dm_sequence=? WHERE id=?",
            (sequence_name, contact["id"])
        )
        self.crm.conn.commit()
        log.info(f"Sequence '{sequence_name}' queued for contact {contact['id']} ({contact.get('username')})")

    def trigger_for_event(self, contact: dict, triggered_sequences: list[str]):
        """Called when comment classifier returns triggered_sequences."""
        for seq_name in triggered_sequences:
            self.trigger_sequence(contact, seq_name)

    # ── Send due DMs ──────────────────────────────────────────────────
    def send_due_dms(self):
        """Called on cron — sends all DMs that are scheduled for now."""
        now = datetime.utcnow()
        due = self.crm.get_due_dms(now)
        sent, skipped = 0, 0

        for dm in due:
            if dm.get("dm_stopped"):
                self.crm.conn.execute(
                    "UPDATE dm_queue SET status='skipped' WHERE id=?", (dm["id"],)
                )
                self.crm.conn.commit()
                skipped += 1
                continue

            try:
                if dm["platform"] == "instagram":
                    self._send_ig_dm(dm["platform_id"], dm["message_text"])
                elif dm["platform"] == "facebook":
                    self._send_fb_message(dm["platform_id"], dm["message_text"])

                self.crm.mark_dm_sent(dm["id"])
                sent += 1
                log.info(f"DM sent to {dm.get('username')} via {dm['platform']}: {dm['sequence_name']} step {dm['step']}")

            except Exception as e:
                log.error(f"DM send failed for contact {dm['contact_id']}: {e}")
                self.crm.conn.execute(
                    "UPDATE dm_queue SET status='failed' WHERE id=?", (dm["id"],)
                )
                self.crm.conn.commit()

        log.info(f"DMs: {sent} sent, {skipped} skipped (contact replied).")

    # ── Pipeline stage advancement ────────────────────────────────────
    def check_pipeline_triggers(self, contact: dict):
        """Advance pipeline stage based on interaction count and behaviour."""
        stage = contact.get("pipeline_stage", "discovered")
        count = self.crm.get_interaction_count(contact["id"])

        # discovered → engaged after 1 comment
        if stage == "discovered" and count >= 1:
            self.crm.advance_pipeline(contact["id"], "engaged")
            self.trigger_sequence(contact, "welcome_first_comment")

        # engaged → warm after 3 interactions
        elif stage == "engaged" and count >= 3:
            self.crm.advance_pipeline(contact["id"], "warm")

    # ── Platform senders ─────────────────────────────────────────────
    def _send_ig_dm(self, recipient_ig_id: str, text: str):
        """Send a DM via Instagram Messaging API."""
        r = httpx.post(
            f"{IG_API}/{self.ig_account_id}/messages",
            json={
                "recipient": {"id": recipient_ig_id},
                "message": {"text": text},
            },
            params={"access_token": self.ig_token},
            timeout=15,
        )
        r.raise_for_status()

    def _send_fb_message(self, recipient_psid: str, text: str):
        """Send a message via Facebook Messenger API."""
        r = httpx.post(
            f"{FB_API}/me/messages",
            json={
                "recipient": {"id": recipient_psid},
                "message": {"text": text},
            },
            params={"access_token": self.fb_page_token},
            timeout=15,
        )
        r.raise_for_status()

    # ── Comment reply sender ──────────────────────────────────────────
    def post_comment_reply(self, platform: str, comment_id: str, reply_text: str):
        """Post a reply directly to a comment (not a DM)."""
        if platform == "instagram":
            r = httpx.post(
                f"{IG_API}/{comment_id}/replies",
                params={"message": reply_text, "access_token": self.ig_token},
                timeout=15,
            )
        elif platform == "facebook":
            r = httpx.post(
                f"{FB_API}/{comment_id}/comments",
                params={"message": reply_text, "access_token": self.fb_page_token},
                timeout=15,
            )
        else:
            return
        r.raise_for_status()

    @staticmethod
    def _render_message(template: str, contact: dict) -> str:
        """Replace {first_name} and other placeholders."""
        return template.format(
            first_name=contact.get("first_name") or contact.get("username") or "there"
        ).strip()
