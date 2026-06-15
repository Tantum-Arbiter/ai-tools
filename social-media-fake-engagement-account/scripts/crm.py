"""
CRM — Grow with Freya Engagement Hub
GoHighLevel-style contact management in SQLite.
Tracks every person who engages, their pipeline stage, and full interaction history.
"""
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL,          -- instagram | facebook
    platform_id     TEXT NOT NULL,          -- platform user ID
    username        TEXT,
    display_name    TEXT,
    first_name      TEXT,                   -- parsed from display_name
    pipeline_stage  TEXT DEFAULT 'discovered',
    tags            TEXT DEFAULT '[]',      -- JSON array
    notes           TEXT,
    dm_sequence     TEXT,                   -- active sequence name
    dm_step         INTEGER DEFAULT 0,
    dm_stopped      INTEGER DEFAULT 0,      -- 1 if they replied (stop sequence)
    last_seen_at    TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(platform, platform_id)
);

CREATE TABLE IF NOT EXISTS interactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id      INTEGER REFERENCES contacts(id),
    platform        TEXT,
    type            TEXT,   -- comment | dm_received | dm_sent | like | story_reply
    content         TEXT,   -- the comment or message text
    media_id        TEXT,   -- post/media the interaction was on
    comment_id      TEXT,   -- platform comment ID (for replying)
    reply_sent      TEXT,   -- our reply text
    reply_sent_at   TEXT,
    sentiment       TEXT,   -- positive | neutral | concern | negative
    comment_type    TEXT,   -- question | compliment | concern | share_experience | generic | negative
    escalated       INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dm_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id      INTEGER REFERENCES contacts(id),
    sequence_name   TEXT,
    step            INTEGER,
    scheduled_at    TEXT,
    sent_at         TEXT,
    status          TEXT DEFAULT 'pending',  -- pending | sent | skipped | failed
    message_text    TEXT
);
"""

PIPELINE_STAGES = ["discovered", "engaged", "warm", "lead", "trial", "customer"]


class CRM:
    def __init__(self, db_path: str = "data/engagement.db"):
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ── Contacts ─────────────────────────────────────────────────────
    def upsert_contact(self, platform: str, platform_id: str, username: str = None,
                       display_name: str = None) -> dict:
        """Create or update a contact. Returns the contact dict."""
        first_name = (display_name or username or "").split()[0].strip() if (display_name or username) else ""
        now = datetime.utcnow().isoformat()
        self.conn.execute("""
            INSERT INTO contacts (platform, platform_id, username, display_name, first_name, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(platform, platform_id) DO UPDATE SET
                username=excluded.username,
                display_name=excluded.display_name,
                first_name=excluded.first_name,
                last_seen_at=excluded.last_seen_at
        """, (platform, platform_id, username, display_name, first_name, now))
        self.conn.commit()
        return self.get_contact(platform, platform_id)

    def get_contact(self, platform: str, platform_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM contacts WHERE platform=? AND platform_id=?",
            (platform, platform_id)
        ).fetchone()
        return dict(row) if row else None

    def advance_pipeline(self, contact_id: int, to_stage: str):
        if to_stage not in PIPELINE_STAGES:
            return
        self.conn.execute(
            "UPDATE contacts SET pipeline_stage=? WHERE id=?", (to_stage, contact_id)
        )
        self.conn.commit()
        log.info(f"Contact {contact_id} advanced to stage: {to_stage}")

    def add_tag(self, contact_id: int, tag: str):
        row = self.conn.execute("SELECT tags FROM contacts WHERE id=?", (contact_id,)).fetchone()
        tags = json.loads(row["tags"] or "[]")
        if tag not in tags:
            tags.append(tag)
            self.conn.execute("UPDATE contacts SET tags=? WHERE id=?", (json.dumps(tags), contact_id))
            self.conn.commit()

    # ── Interactions ─────────────────────────────────────────────────
    def log_interaction(self, contact_id: int, platform: str, type: str,
                        content: str = None, media_id: str = None,
                        comment_id: str = None, sentiment: str = None,
                        comment_type: str = None, escalated: bool = False) -> int:
        cur = self.conn.execute("""
            INSERT INTO interactions
            (contact_id, platform, type, content, media_id, comment_id,
             sentiment, comment_type, escalated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (contact_id, platform, type, content, media_id, comment_id,
              sentiment, comment_type, 1 if escalated else 0))
        self.conn.commit()
        return cur.lastrowid

    def mark_reply_sent(self, interaction_id: int, reply_text: str):
        self.conn.execute("""
            UPDATE interactions SET reply_sent=?, reply_sent_at=? WHERE id=?
        """, (reply_text, datetime.utcnow().isoformat(), interaction_id))
        self.conn.commit()

    def get_interaction_count(self, contact_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM interactions WHERE contact_id=?", (contact_id,)
        ).fetchone()
        return row["cnt"]

    # ── DM Queue ──────────────────────────────────────────────────────
    def queue_dm(self, contact_id: int, sequence_name: str, step: int,
                 message_text: str, send_at: datetime):
        self.conn.execute("""
            INSERT INTO dm_queue (contact_id, sequence_name, step, message_text, scheduled_at)
            VALUES (?, ?, ?, ?, ?)
        """, (contact_id, sequence_name, step, message_text, send_at.isoformat()))
        self.conn.commit()

    def get_due_dms(self, now: datetime) -> list[dict]:
        rows = self.conn.execute("""
            SELECT q.*, c.platform, c.platform_id, c.first_name, c.dm_stopped
            FROM dm_queue q JOIN contacts c ON q.contact_id = c.id
            WHERE q.status = 'pending' AND q.scheduled_at <= ?
            ORDER BY q.scheduled_at ASC
        """, (now.isoformat(),)).fetchall()
        return [dict(r) for r in rows]

    def mark_dm_sent(self, dm_id: int):
        self.conn.execute(
            "UPDATE dm_queue SET status='sent', sent_at=? WHERE id=?",
            (datetime.utcnow().isoformat(), dm_id)
        )
        self.conn.commit()

    def stop_sequences_for_contact(self, contact_id: int):
        """Call when a contact replies — stop all pending DMs immediately."""
        self.conn.execute(
            "UPDATE contacts SET dm_stopped=1 WHERE id=?", (contact_id,)
        )
        self.conn.execute(
            "UPDATE dm_queue SET status='skipped' WHERE contact_id=? AND status='pending'",
            (contact_id,)
        )
        self.conn.commit()
        log.info(f"DM sequences stopped for contact {contact_id} — they replied.")

    # ── Pipeline reporting ────────────────────────────────────────────
    def pipeline_summary(self) -> dict:
        rows = self.conn.execute("""
            SELECT pipeline_stage, COUNT(*) as count FROM contacts GROUP BY pipeline_stage
        """).fetchall()
        return {r["pipeline_stage"]: r["count"] for r in rows}

    def get_contacts_by_stage(self, stage: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM contacts WHERE pipeline_stage=? ORDER BY last_seen_at DESC",
            (stage,)
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
