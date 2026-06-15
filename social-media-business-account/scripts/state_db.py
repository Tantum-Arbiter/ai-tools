"""
State Database (SQLite)
Tracks content queue, published posts, and trend history.
"""
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    platform    TEXT NOT NULL,
    content_type TEXT NOT NULL,
    theme       TEXT,
    hook        TEXT,
    caption     TEXT,
    hashtags    TEXT,           -- JSON array
    asset_path  TEXT,
    scheduled_at TEXT,          -- ISO datetime
    published_at TEXT,          -- ISO datetime, NULL if not yet published
    status      TEXT DEFAULT 'queued',  -- queued | published | failed
    result      TEXT,           -- JSON from publisher (media_id, url, etc.)
    error       TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trends (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT,           -- youtube | instagram | google_trends
    term        TEXT,
    score       REAL,
    metadata    TEXT,           -- JSON
    collected_at TEXT DEFAULT (datetime('now'))
);
"""


class StateDB:
    def __init__(self, db_path: str = "data/state.db"):
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        log.info(f"StateDB ready: {path}")

    def queue_post(self, slot: dict, brief: dict, asset_path: str):
        """Add a generated post to the queue."""
        self.conn.execute(
            """INSERT INTO posts
               (platform, content_type, theme, hook, caption, hashtags, asset_path, scheduled_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                slot["platform"],
                brief.get("content_type", "reel"),
                brief.get("theme"),
                brief.get("hook"),
                brief.get("caption"),
                json.dumps(brief.get("hashtags", [])),
                asset_path,
                slot["time"].isoformat(),
            ),
        )
        self.conn.commit()

    def get_due_posts(self, now: datetime, window_minutes: int = 15) -> list[dict]:
        """Return queued posts scheduled within the next window_minutes."""
        window_start = now.isoformat()
        window_end = (now + timedelta(minutes=window_minutes)).isoformat()
        rows = self.conn.execute(
            """SELECT * FROM posts
               WHERE status = 'queued'
               AND scheduled_at BETWEEN ? AND ?
               ORDER BY scheduled_at ASC""",
            (window_start, window_end),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_queue_depth(self) -> int:
        """Return number of posts waiting to be published."""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM posts WHERE status = 'queued'"
        ).fetchone()
        return row["cnt"]

    def slot_has_content(self, slot: dict) -> bool:
        """Check if a slot already has content queued."""
        scheduled = slot["time"].isoformat()
        row = self.conn.execute(
            "SELECT id FROM posts WHERE platform = ? AND scheduled_at = ? AND status != 'failed'",
            (slot["platform"], scheduled),
        ).fetchone()
        return row is not None

    def mark_published(self, post_id: int, result: dict):
        self.conn.execute(
            "UPDATE posts SET status='published', published_at=?, result=? WHERE id=?",
            (datetime.utcnow().isoformat(), json.dumps(result), post_id),
        )
        self.conn.commit()

    def mark_failed(self, post_id: int, error: str):
        self.conn.execute(
            "UPDATE posts SET status='failed', error=? WHERE id=?",
            (error, post_id),
        )
        self.conn.commit()

    def save_trend(self, source: str, term: str, score: float, metadata: dict = None):
        self.conn.execute(
            "INSERT INTO trends (source, term, score, metadata) VALUES (?, ?, ?, ?)",
            (source, term, score, json.dumps(metadata or {})),
        )
        self.conn.commit()

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        if d.get("hashtags"):
            try:
                d["hashtags"] = json.loads(d["hashtags"])
            except (json.JSONDecodeError, TypeError):
                pass
        if d.get("result"):
            try:
                d["result"] = json.loads(d["result"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    def close(self):
        self.conn.close()
