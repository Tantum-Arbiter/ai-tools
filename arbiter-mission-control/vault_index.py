"""Vault knowledge-base indexer — SQLite FTS5 over Obsidian-style Markdown files.

Walks a vault directory of .md files, parses YAML frontmatter and [[wiki-links]],
and indexes content into an FTS5 virtual table for fast full-text retrieval.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"\A---\n(.+?)\n---\n", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

_SCHEMA = """\
CREATE VIRTUAL TABLE IF NOT EXISTS vault_fts USING fts5(
    path,
    title,
    body,
    tags,
    meta_json UNINDEXED,
    links_json UNINDEXED,
    tokenize='porter unicode61'
);
"""


@dataclass
class VaultDocument:
    path: str
    title: str
    body: str
    meta: dict = field(default_factory=dict)
    links: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    import yaml

    m = _FRONTMATTER_RE.match(raw)
    if not m:
        return {}, raw
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except Exception:
        meta = {}
    body = raw[m.end():]
    return meta, body


def _extract_title(body: str, filepath: Path) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return filepath.stem


def _extract_links(body: str) -> list[str]:
    return _WIKILINK_RE.findall(body)


class VaultIndex:
    def __init__(self, vault_dir: Path | str, db_path: str = ":memory:") -> None:
        self._vault_dir = Path(vault_dir)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def rebuild(self) -> int:
        self._conn.execute("DELETE FROM vault_fts")
        count = 0
        for md_file in self._vault_dir.rglob("*.md"):
            if md_file.parts and any(p.startswith(".") for p in md_file.parts):
                continue
            self._index_file(md_file)
            count += 1
        self._conn.commit()
        log.info("Vault indexed %d documents from %s", count, self._vault_dir)
        return count

    def _index_file(self, filepath: Path) -> None:
        import json

        raw = filepath.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(raw)
        title = _extract_title(body, filepath)
        links = _extract_links(body)
        tags = meta.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        rel_path = str(filepath.relative_to(self._vault_dir))

        self._conn.execute(
            "INSERT INTO vault_fts (path, title, body, tags, meta_json, links_json) VALUES (?, ?, ?, ?, ?, ?)",
            (
                rel_path,
                title,
                body.strip(),
                " ".join(tags),
                json.dumps(meta, default=str),
                json.dumps(links),
            ),
        )

    def search(self, query: str, limit: int = 5) -> list[VaultDocument]:
        import json

        safe_query = " ".join(
            f'"{w}"' for w in query.split() if w.strip()
        )
        if not safe_query:
            return []
        try:
            rows = self._conn.execute(
                "SELECT path, title, body, tags, meta_json, links_json "
                "FROM vault_fts WHERE vault_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (safe_query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

        docs: list[VaultDocument] = []
        for row in rows:
            path, title, body, tags_str, meta_json, links_json = row
            meta = json.loads(meta_json) if meta_json else {}
            links = json.loads(links_json) if links_json else []
            tag_list = tags_str.split() if tags_str else []
            docs.append(VaultDocument(
                path=path, title=title, body=body,
                meta=meta, links=links, tags=tag_list,
            ))
        return docs

    def write_session(self, date_str: str, summary: str, topics: list[str] | None = None) -> Path:
        """Write a session summary markdown file and re-index it."""
        sessions_dir = self._vault_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        tags_line = ", ".join(topics) if topics else "session"
        content = (
            f"---\ntype: session\ntags: [{tags_line}]\n"
            f"updated: {date_str}\n---\n\n"
            f"# Session {date_str}\n\n{summary}\n"
        )
        filepath = sessions_dir / f"{date_str}.md"
        filepath.write_text(content, encoding="utf-8")
        self._index_file(filepath)
        self._conn.commit()
        log.info("Session written: %s", filepath)
        return filepath

    def doc_count(self) -> int:
        row = self._conn.execute("SELECT count(*) FROM vault_fts").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        self._conn.close()
