"""
ARBITER — Persistence Layer
SQLite-backed storage for all agent outputs, briefings, conversations, and insights.
Everything survives restarts — nothing is lost when the laptop sleeps.
"""
import json
import sqlite3
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_results (
    id          TEXT PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    agent_name  TEXT NOT NULL,
    model       TEXT,
    task        TEXT NOT NULL,
    response    TEXT,
    error       TEXT,
    source      TEXT DEFAULT 'dispatch',
    broadcast_id TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS briefings (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,
    message     TEXT,
    panel_json  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    topic       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS insights (
    id          TEXT PRIMARY KEY,
    insight_type TEXT NOT NULL,
    severity    TEXT,
    title       TEXT NOT NULL,
    message     TEXT,
    topic       TEXT,
    data_json   TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pipelines (
    id          TEXT PRIMARY KEY,
    directive   TEXT NOT NULL,
    stages_json TEXT NOT NULL,
    current_idx INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'pending',
    report_json TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_agent_results_agent ON agent_results(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_results_created ON agent_results(created_at);
CREATE INDEX IF NOT EXISTS idx_agent_results_broadcast ON agent_results(broadcast_id);
CREATE INDEX IF NOT EXISTS idx_briefings_category ON briefings(category);
CREATE INDEX IF NOT EXISTS idx_briefings_created ON briefings(created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at);
CREATE INDEX IF NOT EXISTS idx_insights_type ON insights(insight_type);
CREATE INDEX IF NOT EXISTS idx_insights_created ON insights(created_at);
CREATE INDEX IF NOT EXISTS idx_pipelines_status ON pipelines(status);
CREATE INDEX IF NOT EXISTS idx_pipelines_created ON pipelines(created_at);
"""


class ArbiterDB:
    """Unified persistence for all ARBITER agent outputs."""

    def __init__(self, db_path: str = "arbiter.db"):
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrent read/write performance
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")  # wait up to 5s on lock contention
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        # Migrations for existing databases
        self._migrate(path)
        log.info(f"ArbiterDB ready: {path}")

    def _migrate(self, path: Path):
        """Apply schema migrations for existing databases."""
        try:
            cols = [r[1] for r in self.conn.execute("PRAGMA table_info(pipelines)").fetchall()]
            if "report_json" not in cols:
                self.conn.execute("ALTER TABLE pipelines ADD COLUMN report_json TEXT")
                self.conn.commit()
                log.info("Migration: added report_json column to pipelines")
        except Exception as e:
            log.warning(f"Migration check failed (non-fatal): {e}")

    def close(self):
        self.conn.close()

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex[:12]

    # ── Agent Results ─────────────────────────────────────────────

    def save_agent_result(
        self, agent_id: str, agent_name: str, task: str,
        response: Optional[str] = None, error: Optional[str] = None,
        model: Optional[str] = None, source: str = "dispatch",
        broadcast_id: Optional[str] = None,
    ) -> str:
        rid = self._new_id()
        self.conn.execute(
            """INSERT INTO agent_results
               (id, agent_id, agent_name, model, task, response, error, source, broadcast_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rid, agent_id, agent_name, model, task, response, error,
             source, broadcast_id, datetime.utcnow().isoformat()),
        )
        self.conn.commit()
        return rid

    def get_agent_results(
        self, agent_id: Optional[str] = None, limit: int = 50, offset: int = 0,
        search: Optional[str] = None,
    ) -> list[dict]:
        sql = "SELECT * FROM agent_results WHERE 1=1"
        params: list = []
        if agent_id:
            sql += " AND agent_id = ?"
            params.append(agent_id)
        if search:
            sql += " AND (task LIKE ? OR response LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_agent_result(self, result_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM agent_results WHERE id = ?", (result_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_broadcast_results(self, broadcast_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM agent_results WHERE broadcast_id = ? ORDER BY agent_id",
            (broadcast_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Briefings ─────────────────────────────────────────────────

    def save_briefing(
        self, title: str, category: str, message: str,
        panel: Optional[dict] = None,
    ) -> str:
        bid = self._new_id()
        self.conn.execute(
            """INSERT INTO briefings (id, title, category, message, panel_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (bid, title, category, message,
             json.dumps(panel) if panel else None,
             datetime.utcnow().isoformat()),
        )
        self.conn.commit()
        return bid

    def get_briefings(
        self, category: Optional[str] = None, limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        sql = "SELECT * FROM briefings WHERE 1=1"
        params: list = []
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.conn.execute(sql, params).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            if d.get("panel_json"):
                d["panel"] = json.loads(d["panel_json"])
            d.pop("panel_json", None)
            results.append(d)
        return results

    # ── Conversations ─────────────────────────────────────────────

    def save_conversation_turn(
        self, session_id: str, role: str, content: str,
        topic: Optional[str] = None,
    ) -> str:
        cid = self._new_id()
        self.conn.execute(
            """INSERT INTO conversations (id, session_id, role, content, topic, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cid, session_id, role, content, topic,
             datetime.utcnow().isoformat()),
        )
        self.conn.commit()
        return cid

    def get_conversation(self, session_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM conversations WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_sessions(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Return distinct sessions with their first message and turn count."""
        rows = self.conn.execute(
            """SELECT session_id,
                      MIN(created_at) as started_at,
                      MAX(created_at) as last_at,
                      COUNT(*) as turn_count,
                      MIN(CASE WHEN role='user' THEN content END) as first_query
               FROM conversations
               GROUP BY session_id
               ORDER BY started_at DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Insights ──────────────────────────────────────────────────

    def save_insight(
        self, insight_type: str, title: str, message: str,
        severity: Optional[str] = None, topic: Optional[str] = None,
        data: Optional[dict] = None,
    ) -> str:
        iid = self._new_id()
        self.conn.execute(
            """INSERT INTO insights (id, insight_type, severity, title, message, topic, data_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (iid, insight_type, severity, title, message, topic,
             json.dumps(data) if data else None,
             datetime.utcnow().isoformat()),
        )
        self.conn.commit()
        return iid

    def get_insights(
        self, insight_type: Optional[str] = None, severity: Optional[str] = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        sql = "SELECT * FROM insights WHERE 1=1"
        params: list = []
        if insight_type:
            sql += " AND insight_type = ?"
            params.append(insight_type)
        if severity:
            sql += " AND severity = ?"
            params.append(severity)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.conn.execute(sql, params).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            if d.get("data_json"):
                d["data"] = json.loads(d["data_json"])
            d.pop("data_json", None)
            results.append(d)
        return results

    # ── Pipelines ─────────────────────────────────────────────────

    def save_pipeline(self, directive: str, stages: list[dict]) -> str:
        """Create a new pipeline with stages. Each stage dict has:
        agent_id, agent_name, task_template, status ('pending'), output (None).
        """
        pid = self._new_id()
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT INTO pipelines (id, directive, stages_json, current_idx, status, created_at, updated_at)
               VALUES (?, ?, ?, 0, 'pending', ?, ?)""",
            (pid, directive, json.dumps(stages), now, now),
        )
        self.conn.commit()
        return pid

    def get_pipeline(self, pipeline_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM pipelines WHERE id = ?", (pipeline_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["stages"] = json.loads(d.pop("stages_json"))
        if d.get("report_json"):
            d["report"] = json.loads(d.pop("report_json"))
        else:
            d.pop("report_json", None)
            d["report"] = None
        return d

    def get_pipelines(self, status: Optional[str] = None, limit: int = 20) -> list[dict]:
        sql = "SELECT * FROM pipelines WHERE 1=1"
        params: list = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["stages"] = json.loads(d.pop("stages_json"))
            if d.get("report_json"):
                d["report"] = json.loads(d.pop("report_json"))
            else:
                d.pop("report_json", None)
                d["report"] = None
            results.append(d)
        return results

    def update_pipeline(self, pipeline_id: str, stages: list[dict],
                        current_idx: int, status: str) -> None:
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """UPDATE pipelines SET stages_json = ?, current_idx = ?, status = ?, updated_at = ?
               WHERE id = ?""",
            (json.dumps(stages), current_idx, status, now, pipeline_id),
        )
        self.conn.commit()

    def save_pipeline_report(self, pipeline_id: str, report: dict) -> None:
        """Store the generated report for a completed pipeline."""
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """UPDATE pipelines SET report_json = ?, updated_at = ? WHERE id = ?""",
            (json.dumps(report), now, pipeline_id),
        )
        self.conn.commit()

    # ── Universal Search ──────────────────────────────────────────

    def search_all(self, query: str, limit: int = 20) -> dict:
        """Search across all tables for a query string."""
        like = f"%{query}%"
        agents = self.conn.execute(
            "SELECT * FROM agent_results WHERE task LIKE ? OR response LIKE ? ORDER BY created_at DESC LIMIT ?",
            (like, like, limit),
        ).fetchall()
        briefs = self.conn.execute(
            "SELECT * FROM briefings WHERE title LIKE ? OR message LIKE ? ORDER BY created_at DESC LIMIT ?",
            (like, like, limit),
        ).fetchall()
        convos = self.conn.execute(
            "SELECT * FROM conversations WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
            (like, limit),
        ).fetchall()
        ins = self.conn.execute(
            "SELECT * FROM insights WHERE title LIKE ? OR message LIKE ? ORDER BY created_at DESC LIMIT ?",
            (like, like, limit),
        ).fetchall()
        return {
            "agent_results": [dict(r) for r in agents],
            "briefings": [dict(r) for r in briefs],
            "conversations": [dict(r) for r in convos],
            "insights": [dict(r) for r in ins],
        }
