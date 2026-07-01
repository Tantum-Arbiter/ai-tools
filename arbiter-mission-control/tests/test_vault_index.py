"""Tests for the Vault knowledge-base indexer (FTS5 + frontmatter + wiki-links)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from vault_index import VaultIndex, VaultDocument


# ── Helpers ──────────────────────────────────────────────────────────

SAMPLE_MD = """\
---
type: entity
tags: [product, mobile, revenue]
updated: 2026-06-30
---

# Grow with Freya

Early childhood development app. Built with React Native / Expo.
Revenue via RevenueCat subscriptions.

## Tech Stack
- Frontend: React Native, Expo Router, Zustand
- Backend: GCP Cloud Run, Firestore

## Related
- [[Early Roots]] — parent brand
- [[Competitor Analysis]]
"""

MINIMAL_MD = """\
# Quick Note

No frontmatter here. Just plain text about deployment steps.
"""


@pytest.fixture
def vault_dir(tmp_path: Path) -> Path:
    entities = tmp_path / "entities"
    entities.mkdir()
    (entities / "Grow with Freya.md").write_text(SAMPLE_MD)
    (tmp_path / "notes.md").write_text(MINIMAL_MD)
    return tmp_path


@pytest.fixture
def under_test(vault_dir: Path) -> VaultIndex:
    idx = VaultIndex(vault_dir=vault_dir, db_path=":memory:")
    idx.rebuild()
    return idx


# ══════════════════════════════════════════════════════════════════════
# Frontmatter Parsing
# ══════════════════════════════════════════════════════════════════════


class TestFrontmatterParsing:
    def test_parses_yaml_frontmatter(self, under_test: VaultIndex):
        results = under_test.search("Freya")

        assert len(results) >= 1
        doc = results[0]
        assert doc.meta.get("type") == "entity"
        assert "product" in doc.meta.get("tags", [])

    def test_no_frontmatter_returns_empty_meta(self, under_test: VaultIndex):
        results = under_test.search("deployment")

        assert len(results) >= 1
        doc = results[0]
        assert doc.meta == {}


# ══════════════════════════════════════════════════════════════════════
# Wiki-link Extraction
# ══════════════════════════════════════════════════════════════════════


class TestWikiLinks:
    def test_extracts_wiki_links(self, under_test: VaultIndex):
        results = under_test.search("Freya")

        doc = results[0]
        assert "Early Roots" in doc.links
        assert "Competitor Analysis" in doc.links

    def test_no_links_returns_empty_list(self, under_test: VaultIndex):
        results = under_test.search("deployment")

        doc = results[0]
        assert doc.links == []


# ══════════════════════════════════════════════════════════════════════
# FTS5 Search
# ══════════════════════════════════════════════════════════════════════


class TestFTS5Search:
    def test_search_by_content_keyword(self, under_test: VaultIndex):
        results = under_test.search("RevenueCat")

        assert len(results) == 1
        assert "Freya" in results[0].title

    def test_search_returns_empty_for_no_match(self, under_test: VaultIndex):
        results = under_test.search("xyznonexistent")

        assert results == []

    def test_search_ranks_by_relevance(self, vault_dir: Path):
        (vault_dir / "extra.md").write_text("# Unrelated\n\nSome text about nothing.\n")

        under_test = VaultIndex(vault_dir=vault_dir, db_path=":memory:")
        under_test.rebuild()
        results = under_test.search("React Native Expo")

        assert len(results) >= 1
        assert "Freya" in results[0].title

    def test_search_limit(self, under_test: VaultIndex):
        results = under_test.search("text", limit=1)

        assert len(results) <= 1

    def test_search_by_tag(self, under_test: VaultIndex):
        results = under_test.search("product mobile")

        assert len(results) >= 1


# ══════════════════════════════════════════════════════════════════════
# Rebuild / Re-index
# ══════════════════════════════════════════════════════════════════════


class TestReindex:
    def test_rebuild_picks_up_new_files(self, under_test: VaultIndex, vault_dir: Path):
        (vault_dir / "new_doc.md").write_text("# New Doc\n\nBrand new knowledge about quantum computing.\n")

        under_test.rebuild()
        results = under_test.search("quantum computing")

        assert len(results) == 1

    def test_rebuild_removes_deleted_files(self, under_test: VaultIndex, vault_dir: Path):
        (vault_dir / "notes.md").unlink()

        under_test.rebuild()
        results = under_test.search("deployment")

        assert results == []

    def test_rebuild_updates_changed_content(self, under_test: VaultIndex, vault_dir: Path):
        (vault_dir / "notes.md").write_text("# Updated\n\nNow about kubernetes orchestration.\n")

        under_test.rebuild()
        results = under_test.search("kubernetes")

        assert len(results) == 1


# ══════════════════════════════════════════════════════════════════════
# Document Count
# ══════════════════════════════════════════════════════════════════════


class TestSessionWriteBack:
    def test_writes_session_file(self, under_test: VaultIndex, vault_dir: Path):
        filepath = under_test.write_session(
            "2026-07-01", "Discussed vault architecture and token efficiency.",
            topics=["vault", "architecture"],
        )

        assert filepath.exists()
        assert "vault architecture" in filepath.read_text()

    def test_session_is_searchable_after_write(self, under_test: VaultIndex):
        under_test.write_session(
            "2026-07-01", "Implemented FTS5 search for knowledge base retrieval.",
            topics=["search", "fts5"],
        )

        results = under_test.search("FTS5 knowledge base")

        assert len(results) >= 1
        assert "2026-07-01" in results[0].title

    def test_session_has_frontmatter(self, under_test: VaultIndex, vault_dir: Path):
        under_test.write_session("2026-06-30", "Test session.", topics=["test"])

        content = (vault_dir / "sessions" / "2026-06-30.md").read_text()

        assert "type: session" in content
        assert "tags: [test]" in content


class TestDocumentCount:
    def test_count_after_index(self, under_test: VaultIndex):
        assert under_test.doc_count() == 2
