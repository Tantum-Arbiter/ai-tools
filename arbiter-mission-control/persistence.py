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
CREATE TABLE IF NOT EXISTS business_profiles (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    slug             TEXT NOT NULL UNIQUE,
    description      TEXT,
    icon             TEXT DEFAULT '🏢',
    cicd_config      TEXT,
    github_repo      TEXT,
    business_context TEXT,
    active_prompt_mode TEXT DEFAULT 'default',
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

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
    business_id TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS briefings (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,
    message     TEXT,
    panel_json  TEXT,
    business_id TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    topic       TEXT,
    business_id TEXT,
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
    business_id TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pipelines (
    id          TEXT PRIMARY KEY,
    directive   TEXT NOT NULL,
    stages_json TEXT NOT NULL,
    current_idx INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'pending',
    report_json TEXT,
    business_id TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_business_profiles_slug ON business_profiles(slug);
CREATE INDEX IF NOT EXISTS idx_agent_results_agent ON agent_results(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_results_created ON agent_results(created_at);
CREATE INDEX IF NOT EXISTS idx_agent_results_broadcast ON agent_results(broadcast_id);
CREATE INDEX IF NOT EXISTS idx_briefings_category ON briefings(category);
CREATE INDEX IF NOT EXISTS idx_briefings_created ON briefings(created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at);
CREATE INDEX IF NOT EXISTS idx_insights_type ON insights(insight_type);
CREATE INDEX IF NOT EXISTS idx_insights_created ON insights(created_at);
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pipelines_status ON pipelines(status);
CREATE INDEX IF NOT EXISTS idx_pipelines_created ON pipelines(created_at);

CREATE TABLE IF NOT EXISTS prompt_versions (
    id           TEXT PRIMARY KEY,
    business_id  TEXT NOT NULL,
    mode         TEXT NOT NULL DEFAULT 'default',
    version_num  INTEGER NOT NULL,
    content      TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'user',
    summary      TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (business_id) REFERENCES business_profiles(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_prompt_ver_biz ON prompt_versions(business_id);
CREATE INDEX IF NOT EXISTS idx_prompt_ver_mode ON prompt_versions(business_id, mode, version_num);
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

        # Migration: add business_id to all data tables + create indexes
        _biz_tables = ["agent_results", "briefings", "conversations", "insights", "pipelines"]
        for tbl in _biz_tables:
            try:
                cols = [r[1] for r in self.conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
                if "business_id" not in cols:
                    self.conn.execute(f"ALTER TABLE {tbl} ADD COLUMN business_id TEXT")
                    self.conn.commit()
                    log.info(f"Migration: added business_id column to {tbl}")
            except Exception as e:
                log.warning(f"Migration ({tbl} business_id) failed (non-fatal): {e}")

        # Create business_id indexes (safe after columns exist)
        for tbl in _biz_tables:
            try:
                self.conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{tbl}_business ON {tbl}(business_id)"
                )
                self.conn.commit()
            except Exception:
                pass  # non-fatal — column may not exist on very old DBs

        # Migration: add github_repo, business_context, active_prompt_mode to business_profiles
        try:
            cols = [r[1] for r in self.conn.execute("PRAGMA table_info(business_profiles)").fetchall()]
            if "github_repo" not in cols:
                self.conn.execute("ALTER TABLE business_profiles ADD COLUMN github_repo TEXT")
                self.conn.commit()
                log.info("Migration: added github_repo column to business_profiles")
            if "business_context" not in cols:
                self.conn.execute("ALTER TABLE business_profiles ADD COLUMN business_context TEXT")
                self.conn.commit()
                log.info("Migration: added business_context column to business_profiles")
            if "active_prompt_mode" not in cols:
                self.conn.execute("ALTER TABLE business_profiles ADD COLUMN active_prompt_mode TEXT DEFAULT 'default'")
                self.conn.commit()
                log.info("Migration: added active_prompt_mode column to business_profiles")
        except Exception as e:
            log.warning(f"Migration (business_profiles) failed (non-fatal): {e}")

        # Migration: seed existing business_context into prompt_versions table
        try:
            rows = self.conn.execute(
                "SELECT id, business_context FROM business_profiles WHERE business_context IS NOT NULL AND business_context != ''"
            ).fetchall()
            for row in rows:
                existing = self.conn.execute(
                    "SELECT 1 FROM prompt_versions WHERE business_id = ? LIMIT 1", (row[0],)
                ).fetchone()
                if not existing:
                    self.conn.execute(
                        """INSERT INTO prompt_versions (id, business_id, mode, version_num, content, source, summary, created_at)
                           VALUES (?, ?, 'default', 1, ?, 'migration', 'Migrated from business profile', datetime('now'))""",
                        (self._new_id(), row[0], row[1]),
                    )
                    self.conn.commit()
                    log.info(f"Migration: seeded prompt v1 for business {row[0]}")
        except Exception as e:
            log.warning(f"Migration (prompt_versions seed) failed (non-fatal): {e}")

    def close(self):
        self.conn.close()

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex[:12]

    # ── Business Profiles ────────────────────────────────────────

    def save_business(
        self, name: str, slug: str, description: str = "",
        icon: str = "🏢", cicd_config: Optional[list] = None,
        github_repo: str = "", business_context: str = "",
    ) -> str:
        bid = self._new_id()
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT INTO business_profiles
               (id, name, slug, description, icon, cicd_config, github_repo, business_context, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (bid, name, slug, description, icon,
             json.dumps(cicd_config) if cicd_config else None,
             github_repo or None, business_context or None, now, now),
        )
        self.conn.commit()
        return bid

    def get_businesses(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM business_profiles ORDER BY created_at ASC"
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            if d.get("cicd_config"):
                d["cicd_config"] = json.loads(d["cicd_config"])
            results.append(d)
        return results

    def get_business(self, business_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM business_profiles WHERE id = ?", (business_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("cicd_config"):
            d["cicd_config"] = json.loads(d["cicd_config"])
        return d

    def update_business(
        self, business_id: str, name: Optional[str] = None,
        description: Optional[str] = None, icon: Optional[str] = None,
        cicd_config: Optional[list] = None, github_repo: Optional[str] = None,
        business_context: Optional[str] = None,
    ) -> bool:
        biz = self.get_business(business_id)
        if not biz:
            return False
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """UPDATE business_profiles SET name=?, description=?, icon=?, cicd_config=?,
               github_repo=?, business_context=?, updated_at=? WHERE id=?""",
            (
                name if name is not None else biz["name"],
                description if description is not None else biz.get("description", ""),
                icon if icon is not None else biz.get("icon", "🏢"),
                json.dumps(cicd_config) if cicd_config is not None else (
                    json.dumps(biz["cicd_config"]) if biz.get("cicd_config") else None
                ),
                github_repo if github_repo is not None else biz.get("github_repo", ""),
                business_context if business_context is not None else biz.get("business_context", ""),
                now, business_id,
            ),
        )
        self.conn.commit()
        return True

    def delete_business(self, business_id: str) -> bool:
        # Cascade: remove prompt versions for this business
        self.conn.execute(
            "DELETE FROM prompt_versions WHERE business_id = ?", (business_id,)
        )
        cur = self.conn.execute(
            "DELETE FROM business_profiles WHERE id = ?", (business_id,)
        )
        self.conn.commit()
        return cur.rowcount > 0

    # ── Prompt Versioning ─────────────────────────────────────────

    def save_prompt_version(
        self, business_id: str, content: str,
        mode: str = "default", source: str = "user",
        summary: str = "",
    ) -> dict:
        """Create a new prompt version. Auto-increments version_num per business+mode.

        source: 'user' (manual edit), 'agent' (AI-generated), 'pipeline' (auto-refined),
                'migration' (seeded from legacy business_context).
        Returns the new version dict.
        """
        # Get next version number for this business + mode
        row = self.conn.execute(
            "SELECT MAX(version_num) FROM prompt_versions WHERE business_id = ? AND mode = ?",
            (business_id, mode),
        ).fetchone()
        next_ver = (row[0] or 0) + 1

        vid = self._new_id()
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT INTO prompt_versions (id, business_id, mode, version_num, content, source, summary, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (vid, business_id, mode, next_ver, content, source, summary or "", now),
        )
        # Also update the business_context column (keeps backwards compat + single source of truth for active prompt)
        active_mode = self._get_active_mode(business_id)
        if mode == active_mode:
            self.conn.execute(
                "UPDATE business_profiles SET business_context = ?, updated_at = ? WHERE id = ?",
                (content, now, business_id),
            )
        self.conn.commit()
        return {"id": vid, "business_id": business_id, "mode": mode,
                "version_num": next_ver, "content": content, "source": source,
                "summary": summary or "", "created_at": now}

    def get_prompt_versions(
        self, business_id: str, mode: Optional[str] = None, limit: int = 20,
    ) -> list[dict]:
        """Get prompt version history for a business. Newest first."""
        sql = "SELECT * FROM prompt_versions WHERE business_id = ?"
        params: list = [business_id]
        if mode:
            sql += " AND mode = ?"
            params.append(mode)
        sql += " ORDER BY version_num DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def get_active_prompt(self, business_id: str) -> Optional[dict]:
        """Get the latest prompt version for the business's active mode."""
        active_mode = self._get_active_mode(business_id)
        row = self.conn.execute(
            """SELECT * FROM prompt_versions
               WHERE business_id = ? AND mode = ?
               ORDER BY version_num DESC LIMIT 1""",
            (business_id, active_mode),
        ).fetchone()
        return dict(row) if row else None

    def get_prompt_modes(self, business_id: str) -> list[dict]:
        """List all modes for a business with their latest version info."""
        rows = self.conn.execute(
            """SELECT mode, MAX(version_num) as latest_version,
                      COUNT(*) as total_versions,
                      MAX(created_at) as last_updated
               FROM prompt_versions
               WHERE business_id = ?
               GROUP BY mode
               ORDER BY mode""",
            (business_id,),
        ).fetchall()
        active_mode = self._get_active_mode(business_id)
        return [
            {**dict(r), "is_active": r["mode"] == active_mode}
            for r in rows
        ]

    def set_active_mode(self, business_id: str, mode: str) -> bool:
        """Switch the active prompt mode for a business.
        Also updates business_context to the latest version of the new mode."""
        biz = self.get_business(business_id)
        if not biz:
            return False
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            "UPDATE business_profiles SET active_prompt_mode = ?, updated_at = ? WHERE id = ?",
            (mode, now, business_id),
        )
        # Sync business_context with latest version of the new mode
        latest = self.conn.execute(
            """SELECT content FROM prompt_versions
               WHERE business_id = ? AND mode = ?
               ORDER BY version_num DESC LIMIT 1""",
            (business_id, mode),
        ).fetchone()
        if latest:
            self.conn.execute(
                "UPDATE business_profiles SET business_context = ?, updated_at = ? WHERE id = ?",
                (latest[0], now, business_id),
            )
        self.conn.commit()
        return True

    def get_prompt_version_by_id(self, version_id: str) -> Optional[dict]:
        """Get a specific prompt version by its ID."""
        row = self.conn.execute(
            "SELECT * FROM prompt_versions WHERE id = ?", (version_id,)
        ).fetchone()
        return dict(row) if row else None

    def restore_prompt_version(self, version_id: str) -> Optional[dict]:
        """Restore a previous version by creating a new version with its content.
        Returns the new version dict, or None if version_id not found."""
        old = self.get_prompt_version_by_id(version_id)
        if not old:
            return None
        return self.save_prompt_version(
            business_id=old["business_id"],
            content=old["content"],
            mode=old["mode"],
            source="user",
            summary=f"Restored from v{old['version_num']}",
        )

    def _get_active_mode(self, business_id: str) -> str:
        """Get the active prompt mode for a business (default: 'default')."""
        row = self.conn.execute(
            "SELECT active_prompt_mode FROM business_profiles WHERE id = ?",
            (business_id,),
        ).fetchone()
        return (row[0] if row and row[0] else "default")

    # ── Agent Results ─────────────────────────────────────────────

    def save_agent_result(
        self, agent_id: str, agent_name: str, task: str,
        response: Optional[str] = None, error: Optional[str] = None,
        model: Optional[str] = None, source: str = "dispatch",
        broadcast_id: Optional[str] = None,
        business_id: Optional[str] = None,
    ) -> str:
        rid = self._new_id()
        self.conn.execute(
            """INSERT INTO agent_results
               (id, agent_id, agent_name, model, task, response, error, source, broadcast_id, business_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rid, agent_id, agent_name, model, task, response, error,
             source, broadcast_id, business_id, datetime.utcnow().isoformat()),
        )
        self.conn.commit()
        return rid

    def get_agent_results(
        self, agent_id: Optional[str] = None, limit: int = 50, offset: int = 0,
        search: Optional[str] = None, business_id: Optional[str] = None,
    ) -> list[dict]:
        sql = "SELECT * FROM agent_results WHERE 1=1"
        params: list = []
        if agent_id:
            sql += " AND agent_id = ?"
            params.append(agent_id)
        if business_id:
            sql += " AND business_id = ?"
            params.append(business_id)
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
        panel: Optional[dict] = None, business_id: Optional[str] = None,
    ) -> str:
        bid = self._new_id()
        self.conn.execute(
            """INSERT INTO briefings (id, title, category, message, panel_json, business_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (bid, title, category, message,
             json.dumps(panel) if panel else None,
             business_id, datetime.utcnow().isoformat()),
        )
        self.conn.commit()
        return bid

    def get_briefings(
        self, category: Optional[str] = None, limit: int = 50, offset: int = 0,
        business_id: Optional[str] = None,
    ) -> list[dict]:
        sql = "SELECT * FROM briefings WHERE 1=1"
        params: list = []
        if category:
            sql += " AND category = ?"
            params.append(category)
        if business_id:
            sql += " AND business_id = ?"
            params.append(business_id)
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
        topic: Optional[str] = None, business_id: Optional[str] = None,
    ) -> str:
        cid = self._new_id()
        self.conn.execute(
            """INSERT INTO conversations (id, session_id, role, content, topic, business_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (cid, session_id, role, content, topic,
             business_id, datetime.utcnow().isoformat()),
        )
        self.conn.commit()
        return cid

    def get_conversation(self, session_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM conversations WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_sessions(self, limit: int = 50, offset: int = 0,
                     business_id: Optional[str] = None) -> list[dict]:
        """Return distinct sessions with their first message and turn count."""
        where = ""
        params: list = []
        if business_id:
            where = "WHERE business_id = ?"
            params.append(business_id)
        rows = self.conn.execute(
            f"""SELECT session_id,
                      MIN(created_at) as started_at,
                      MAX(created_at) as last_at,
                      COUNT(*) as turn_count,
                      MIN(CASE WHEN role='user' THEN content END) as first_query
               FROM conversations
               {where}
               GROUP BY session_id
               ORDER BY started_at DESC
               LIMIT ? OFFSET ?""",
            (*params, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Insights ──────────────────────────────────────────────────

    def save_insight(
        self, insight_type: str, title: str, message: str,
        severity: Optional[str] = None, topic: Optional[str] = None,
        data: Optional[dict] = None, business_id: Optional[str] = None,
    ) -> str:
        iid = self._new_id()
        self.conn.execute(
            """INSERT INTO insights (id, insight_type, severity, title, message, topic, data_json, business_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (iid, insight_type, severity, title, message, topic,
             json.dumps(data) if data else None,
             business_id, datetime.utcnow().isoformat()),
        )
        self.conn.commit()
        return iid

    def get_insights(
        self, insight_type: Optional[str] = None, severity: Optional[str] = None,
        limit: int = 50, offset: int = 0, business_id: Optional[str] = None,
    ) -> list[dict]:
        sql = "SELECT * FROM insights WHERE 1=1"
        params: list = []
        if insight_type:
            sql += " AND insight_type = ?"
            params.append(insight_type)
        if severity:
            sql += " AND severity = ?"
            params.append(severity)
        if business_id:
            sql += " AND business_id = ?"
            params.append(business_id)
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

    def save_pipeline(self, directive: str, stages: list[dict],
                      business_id: Optional[str] = None) -> str:
        """Create a new pipeline with stages. Each stage dict has:
        agent_id, agent_name, task_template, status ('pending'), output (None).
        """
        pid = self._new_id()
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT INTO pipelines (id, directive, stages_json, current_idx, status, business_id, created_at, updated_at)
               VALUES (?, ?, ?, 0, 'pending', ?, ?, ?)""",
            (pid, directive, json.dumps(stages), business_id, now, now),
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

    def get_pipelines(self, status: Optional[str] = None, limit: int = 20,
                      business_id: Optional[str] = None) -> list[dict]:
        sql = "SELECT * FROM pipelines WHERE 1=1"
        params: list = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if business_id:
            sql += " AND business_id = ?"
            params.append(business_id)
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

    def search_all(self, query: str, limit: int = 20,
                   business_id: Optional[str] = None) -> dict:
        """Search across all tables for a query string."""
        like = f"%{query}%"
        biz_clause = " AND business_id = ?" if business_id else ""
        biz_param = (business_id,) if business_id else ()

        agents = self.conn.execute(
            f"SELECT * FROM agent_results WHERE (task LIKE ? OR response LIKE ?){biz_clause} ORDER BY created_at DESC LIMIT ?",
            (like, like, *biz_param, limit),
        ).fetchall()
        briefs = self.conn.execute(
            f"SELECT * FROM briefings WHERE (title LIKE ? OR message LIKE ?){biz_clause} ORDER BY created_at DESC LIMIT ?",
            (like, like, *biz_param, limit),
        ).fetchall()
        convos = self.conn.execute(
            f"SELECT * FROM conversations WHERE content LIKE ?{biz_clause} ORDER BY created_at DESC LIMIT ?",
            (like, *biz_param, limit),
        ).fetchall()
        ins = self.conn.execute(
            f"SELECT * FROM insights WHERE (title LIKE ? OR message LIKE ?){biz_clause} ORDER BY created_at DESC LIMIT ?",
            (like, like, *biz_param, limit),
        ).fetchall()
        return {
            "agent_results": [dict(r) for r in agents],
            "briefings": [dict(r) for r in briefs],
            "conversations": [dict(r) for r in convos],
            "insights": [dict(r) for r in ins],
        }

    # ── Settings ──────────────────────────────────────────────────────

    def get_setting(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,),
        ).fetchone()
        return row["value"] if row else None

    def get_settings(self, prefix: str = "") -> dict[str, str]:
        if prefix:
            rows = self.conn.execute(
                "SELECT key, value FROM settings WHERE key LIKE ? ORDER BY key",
                (f"{prefix}%",),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT key, value FROM settings ORDER BY key",
            ).fetchall()
        return {r["key"]: r["value"] for r in rows}

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value),
        )
        self.conn.commit()

    def set_settings(self, data: dict[str, str]) -> None:
        for k, v in data.items():
            self.conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (k, v),
            )
        self.conn.commit()

    def delete_setting(self, key: str) -> bool:
        cur = self.conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        self.conn.commit()
        return cur.rowcount > 0
