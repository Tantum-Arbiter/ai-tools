"""Tests for ARBITER persistence layer — ensures all agent outputs survive restarts."""
import sys
import os
import json
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from persistence import ArbiterDB


@pytest.fixture
def db():
    """Create a fresh in-memory ArbiterDB for each test."""
    d = ArbiterDB(":memory:")
    yield d
    d.close()


# ══════════════════════════════════════════════════════════════════════
# Agent Results
# ══════════════════════════════════════════════════════════════════════

class TestAgentResults:
    def test_save_and_retrieve(self, db):
        rid = db.save_agent_result(
            agent_id="researcher", agent_name="Researcher",
            task="Analyse UK fintech market", response="The UK fintech market is...",
            model="gemini-2.5-pro", source="dispatch",
        )
        assert rid
        result = db.get_agent_result(rid)
        assert result is not None
        assert result["agent_id"] == "researcher"
        assert result["task"] == "Analyse UK fintech market"
        assert result["response"] == "The UK fintech market is..."
        assert result["model"] == "gemini-2.5-pro"
        assert result["source"] == "dispatch"
        assert result["error"] is None
        assert result["broadcast_id"] is None

    def test_save_error_result(self, db):
        rid = db.save_agent_result(
            agent_id="cmo", agent_name="CMO",
            task="Write campaign brief", error="API timeout",
            model="gpt-4.1",
        )
        result = db.get_agent_result(rid)
        assert result["error"] == "API timeout"
        assert result["response"] is None

    def test_list_results_ordered_by_date(self, db):
        db.save_agent_result("researcher", "Researcher", "Task 1", response="R1")
        db.save_agent_result("cmo", "CMO", "Task 2", response="R2")
        db.save_agent_result("researcher", "Researcher", "Task 3", response="R3")
        results = db.get_agent_results()
        assert len(results) == 3
        # Most recent first
        assert results[0]["task"] == "Task 3"
        assert results[2]["task"] == "Task 1"

    def test_filter_by_agent_id(self, db):
        db.save_agent_result("researcher", "Researcher", "Task 1", response="R1")
        db.save_agent_result("cmo", "CMO", "Task 2", response="R2")
        results = db.get_agent_results(agent_id="researcher")
        assert len(results) == 1
        assert results[0]["agent_id"] == "researcher"

    def test_search_results(self, db):
        db.save_agent_result("researcher", "Researcher", "UK fintech analysis",
                             response="The market is growing")
        db.save_agent_result("cmo", "CMO", "Write social copy",
                             response="Check out our new feature")
        results = db.get_agent_results(search="fintech")
        assert len(results) == 1
        assert "fintech" in results[0]["task"]

    def test_search_in_response(self, db):
        db.save_agent_result("analyst", "Analyst", "Revenue report",
                             response="MRR grew 15% to $4,500")
        results = db.get_agent_results(search="MRR")
        assert len(results) == 1

    def test_broadcast_grouping(self, db):
        bid = "broadcast123"
        db.save_agent_result("researcher", "Researcher", "Market scan",
                             response="R1", broadcast_id=bid, source="broadcast")
        db.save_agent_result("cmo", "CMO", "Market scan",
                             response="R2", broadcast_id=bid, source="broadcast")
        db.save_agent_result("cto", "CTO", "Market scan",
                             response="R3", broadcast_id=bid, source="broadcast")
        results = db.get_broadcast_results(bid)
        assert len(results) == 3

    def test_get_nonexistent_result(self, db):
        assert db.get_agent_result("nonexistent") is None

    def test_pagination(self, db):
        for i in range(10):
            db.save_agent_result("researcher", "Researcher", f"Task {i}", response=f"R{i}")
        page1 = db.get_agent_results(limit=3, offset=0)
        page2 = db.get_agent_results(limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        assert page1[0]["task"] != page2[0]["task"]


# ══════════════════════════════════════════════════════════════════════
# Briefings
# ══════════════════════════════════════════════════════════════════════

class TestBriefings:
    def test_save_and_retrieve(self, db):
        panel = {"title": "MORNING BRIEFING", "stats": [{"label": "Temp", "value": "18°C"}]}
        bid = db.save_briefing(
            title="MORNING BRIEFING", category="morning",
            message="Good morning, Sir. 18°C in London.", panel=panel,
        )
        assert bid
        briefings = db.get_briefings()
        assert len(briefings) == 1
        b = briefings[0]
        assert b["title"] == "MORNING BRIEFING"
        assert b["category"] == "morning"
        assert b["panel"]["stats"][0]["value"] == "18°C"
        assert "panel_json" not in b  # raw JSON field should be stripped

    def test_save_without_panel(self, db):
        bid = db.save_briefing(
            title="EVENING DIGEST", category="evening",
            message="All quiet this evening, Sir.",
        )
        briefings = db.get_briefings()
        assert len(briefings) == 1
        assert briefings[0].get("panel") is None

    def test_filter_by_category(self, db):
        db.save_briefing("MORNING BRIEFING", "morning", "Morning msg")
        db.save_briefing("MARKET CLOSE", "market", "Market msg")
        db.save_briefing("EVENING DIGEST", "evening", "Evening msg")
        morning = db.get_briefings(category="morning")
        assert len(morning) == 1
        assert morning[0]["category"] == "morning"

    def test_ordering(self, db):
        db.save_briefing("First", "morning", "msg1")
        db.save_briefing("Second", "evening", "msg2")
        briefings = db.get_briefings()
        assert briefings[0]["title"] == "Second"  # most recent first



# ══════════════════════════════════════════════════════════════════════
# Conversations
# ══════════════════════════════════════════════════════════════════════

class TestConversations:
    def test_save_and_retrieve_turns(self, db):
        sid = "session-abc"
        db.save_conversation_turn(sid, "user", "What's the weather?", topic="weather")
        db.save_conversation_turn(sid, "assistant", "18°C in London, Sir.", topic="weather")
        turns = db.get_conversation(sid)
        assert len(turns) == 2
        assert turns[0]["role"] == "user"
        assert turns[1]["role"] == "assistant"
        assert turns[0]["topic"] == "weather"

    def test_sessions_listing(self, db):
        db.save_conversation_turn("s1", "user", "Hello Arbiter")
        db.save_conversation_turn("s1", "assistant", "Good morning, Sir.")
        db.save_conversation_turn("s2", "user", "Show me stocks")
        sessions = db.get_sessions()
        assert len(sessions) == 2
        # Most recent first
        assert sessions[0]["session_id"] == "s2"
        assert sessions[0]["turn_count"] == 1
        assert sessions[1]["session_id"] == "s1"
        assert sessions[1]["turn_count"] == 2
        assert sessions[1]["first_query"] == "Hello Arbiter"

    def test_empty_conversation(self, db):
        turns = db.get_conversation("nonexistent")
        assert turns == []


# ══════════════════════════════════════════════════════════════════════
# Insights
# ══════════════════════════════════════════════════════════════════════

class TestInsights:
    def test_save_and_retrieve(self, db):
        iid = db.save_insight(
            insight_type="stock_move", title="NVDA surged 5.2%",
            message="Nvidia surged 5.2% to $1,234.",
            severity="high", topic="stocks",
            data={"symbol": "NVDA", "pct": 5.2, "price": 1234},
        )
        assert iid
        insights = db.get_insights()
        assert len(insights) == 1
        i = insights[0]
        assert i["insight_type"] == "stock_move"
        assert i["severity"] == "high"
        assert i["data"]["symbol"] == "NVDA"
        assert "data_json" not in i

    def test_filter_by_type(self, db):
        db.save_insight("stock_move", "NVDA up", "msg", severity="high")
        db.save_insight("churn_spike", "Churn spike", "msg", severity="high")
        results = db.get_insights(insight_type="stock_move")
        assert len(results) == 1

    def test_filter_by_severity(self, db):
        db.save_insight("stock_move", "NVDA up", "msg", severity="high")
        db.save_insight("trial_opportunity", "5 trials", "msg", severity="low")
        results = db.get_insights(severity="low")
        assert len(results) == 1
        assert results[0]["severity"] == "low"

    def test_without_data(self, db):
        db.save_insight("churn_spike", "Churn spike", "10 churned")
        insights = db.get_insights()
        assert insights[0].get("data") is None


# ══════════════════════════════════════════════════════════════════════
# Universal Search
# ══════════════════════════════════════════════════════════════════════

class TestUniversalSearch:
    def test_search_across_tables(self, db):
        db.save_agent_result("researcher", "Researcher", "marketing plan",
                             response="The marketing plan focuses on...")
        db.save_briefing("MORNING BRIEFING", "morning", "marketing metrics look good")
        db.save_conversation_turn("s1", "user", "Tell me about marketing")
        db.save_insight("trial_opportunity", "Marketing trials", "5 marketing trials active")

        results = db.search_all("marketing")
        assert len(results["agent_results"]) == 1
        assert len(results["briefings"]) == 1
        assert len(results["conversations"]) == 1
        assert len(results["insights"]) == 1

    def test_search_no_results(self, db):
        results = db.search_all("xyznonexistent")
        assert results["agent_results"] == []
        assert results["briefings"] == []
        assert results["conversations"] == []
        assert results["insights"] == []

    def test_search_limit(self, db):
        for i in range(10):
            db.save_agent_result("researcher", "Researcher", f"marketing task {i}",
                                 response=f"result {i}")
        results = db.search_all("marketing", limit=3)
        assert len(results["agent_results"]) == 3


# ══════════════════════════════════════════════════════════════════════
# File Persistence (survives restart)
# ══════════════════════════════════════════════════════════════════════

class TestFilePersistence:
    def test_data_survives_close_and_reopen(self, tmp_path):
        db_path = str(tmp_path / "test_arbiter.db")

        # First session — write data
        db1 = ArbiterDB(db_path)
        db1.save_agent_result("cmo", "CMO", "Write marketing plan",
                              response="Here is the comprehensive marketing plan...")
        db1.save_briefing("MORNING BRIEFING", "morning", "Good morning, Sir.")
        db1.save_conversation_turn("session-1", "user", "Create a marketing plan")
        db1.save_insight("trial_opportunity", "5 trials", "5 active trials")
        db1.close()

        # Second session — read data back (simulates laptop restart)
        db2 = ArbiterDB(db_path)
        assert len(db2.get_agent_results()) == 1
        assert db2.get_agent_results()[0]["response"] == "Here is the comprehensive marketing plan..."
        assert len(db2.get_briefings()) == 1
        assert len(db2.get_conversation("session-1")) == 1
        assert len(db2.get_insights()) == 1
        db2.close()

    def test_multiple_sessions_accumulate(self, tmp_path):
        db_path = str(tmp_path / "test_arbiter.db")

        db1 = ArbiterDB(db_path)
        db1.save_agent_result("researcher", "Researcher", "Task day 1", response="R1")
        db1.close()

        db2 = ArbiterDB(db_path)
        db2.save_agent_result("researcher", "Researcher", "Task day 2", response="R2")
        results = db2.get_agent_results()
        assert len(results) == 2
        db2.close()


# ══════════════════════════════════════════════════════════════════════
# ID Generation
# ══════════════════════════════════════════════════════════════════════

class TestIDGeneration:
    def test_ids_are_unique(self, db):
        ids = {db._new_id() for _ in range(100)}
        assert len(ids) == 100

    def test_ids_are_12_chars(self, db):
        assert len(db._new_id()) == 12