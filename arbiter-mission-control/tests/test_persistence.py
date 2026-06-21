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
# Business Profiles
# ══════════════════════════════════════════════════════════════════════

class TestBusinessProfiles:
    def test_create_and_retrieve(self, db):
        bid = db.save_business(
            name="Grow with Freya", slug="grow-with-freya",
            description="Parenting app", icon="🌱",
        )
        assert bid
        biz = db.get_business(bid)
        assert biz["name"] == "Grow with Freya"
        assert biz["slug"] == "grow-with-freya"
        assert biz["icon"] == "🌱"

    def test_list_businesses(self, db):
        db.save_business("Biz A", "biz-a")
        db.save_business("Biz B", "biz-b")
        businesses = db.get_businesses()
        assert len(businesses) == 2
        assert businesses[0]["name"] == "Biz A"

    def test_update_business(self, db):
        bid = db.save_business("Old Name", "old-name")
        db.update_business(bid, name="New Name", icon="🚀")
        biz = db.get_business(bid)
        assert biz["name"] == "New Name"
        assert biz["icon"] == "🚀"

    def test_delete_business(self, db):
        bid = db.save_business("To Delete", "to-delete")
        assert db.delete_business(bid)
        assert db.get_business(bid) is None
        assert len(db.get_businesses()) == 0

    def test_cicd_config(self, db):
        cicd = [
            {"name": "App Build", "key": "app_build", "url": "#", "status": "success"},
            {"name": "Deploy", "key": "deploy", "url": "#", "status": "unknown"},
        ]
        bid = db.save_business("With CI/CD", "with-cicd", cicd_config=cicd)
        biz = db.get_business(bid)
        assert biz["cicd_config"] is not None
        assert len(biz["cicd_config"]) == 2
        assert biz["cicd_config"][0]["name"] == "App Build"

    def test_nonexistent_business(self, db):
        assert db.get_business("nonexistent") is None
        assert not db.delete_business("nonexistent")


# ══════════════════════════════════════════════════════════════════════
# Business-scoped data (business_id filtering)
# ══════════════════════════════════════════════════════════════════════

class TestBusinessScoping:
    def test_agent_results_by_business(self, db):
        db.save_agent_result("r1", "Researcher", "Task A", response="R1", business_id="biz1")
        db.save_agent_result("r1", "Researcher", "Task B", response="R2", business_id="biz2")
        db.save_agent_result("r1", "Researcher", "Task C", response="R3")
        all_results = db.get_agent_results()
        assert len(all_results) == 3
        biz1 = db.get_agent_results(business_id="biz1")
        assert len(biz1) == 1
        assert biz1[0]["task"] == "Task A"

    def test_briefings_by_business(self, db):
        db.save_briefing("Morning", "morning", "msg1", business_id="biz1")
        db.save_briefing("Evening", "evening", "msg2", business_id="biz2")
        all_b = db.get_briefings()
        assert len(all_b) == 2
        biz1 = db.get_briefings(business_id="biz1")
        assert len(biz1) == 1

    def test_conversations_by_business(self, db):
        db.save_conversation_turn("s1", "user", "Hello", business_id="biz1")
        db.save_conversation_turn("s2", "user", "Bye", business_id="biz2")
        sessions = db.get_sessions(business_id="biz1")
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "s1"

    def test_insights_by_business(self, db):
        db.save_insight("alert", "Alert 1", "msg", business_id="biz1")
        db.save_insight("alert", "Alert 2", "msg", business_id="biz2")
        biz1 = db.get_insights(business_id="biz1")
        assert len(biz1) == 1

    def test_pipelines_by_business(self, db):
        db.save_pipeline("Do X", [{"agent_id": "r"}], business_id="biz1")
        db.save_pipeline("Do Y", [{"agent_id": "r"}], business_id="biz2")
        biz1 = db.get_pipelines(business_id="biz1")
        assert len(biz1) == 1
        assert biz1[0]["directive"] == "Do X"

    def test_pipeline_report_save_and_retrieve(self, db):
        stages = [{"agent_id": "r", "status": "complete", "output": "analysis"}]
        pid = db.save_pipeline("Analyse market", stages)
        report = {"title": "EXECUTIVE REPORT", "summary": "Good outlook"}

        db.save_pipeline_report(pid, report)

        under_test = db.get_pipeline(pid)
        assert under_test is not None
        assert under_test["report"] == report
        assert under_test["report"]["title"] == "EXECUTIVE REPORT"

    def test_pipeline_report_none_before_save(self, db):
        pid = db.save_pipeline("Directive", [{"agent_id": "r"}])

        under_test = db.get_pipeline(pid)

        assert under_test is not None
        assert under_test["report"] is None

    def test_pipeline_report_in_list(self, db):
        pid = db.save_pipeline("Directive", [{"agent_id": "r"}])
        report = {"title": "REPORT", "stats": []}
        db.save_pipeline_report(pid, report)

        under_test = db.get_pipelines()

        assert len(under_test) == 1
        assert under_test[0]["report"] == report

    def test_search_all_by_business(self, db):
        db.save_agent_result("r1", "Researcher", "marketing plan", response="R", business_id="biz1")
        db.save_agent_result("r1", "Researcher", "marketing strategy", response="R", business_id="biz2")
        results = db.search_all("marketing", business_id="biz1")
        assert len(results["agent_results"]) == 1


# ══════════════════════════════════════════════════════════════════════
# Settings (key-value store)
# ══════════════════════════════════════════════════════════════════════

class TestSettings:
    def test_set_and_get(self, db):
        db.set_setting("theme", "dark")
        assert db.get_setting("theme") == "dark"

    def test_get_missing(self, db):
        assert db.get_setting("nonexistent") is None

    def test_upsert(self, db):
        db.set_setting("key", "v1")
        db.set_setting("key", "v2")
        assert db.get_setting("key") == "v2"

    def test_bulk_set(self, db):
        db.set_settings({"a": "1", "b": "2", "c": "3"})
        assert db.get_setting("a") == "1"
        assert db.get_setting("c") == "3"

    def test_get_by_prefix(self, db):
        db.set_settings({"email_host": "imap.gmail.com", "email_port": "993", "theme": "dark"})
        email_settings = db.get_settings("email_")
        assert len(email_settings) == 2
        assert "email_host" in email_settings

    def test_get_all(self, db):
        db.set_settings({"x": "1", "y": "2"})
        all_s = db.get_settings()
        assert len(all_s) == 2

    def test_delete(self, db):
        db.set_setting("tmp", "val")
        assert db.delete_setting("tmp")
        assert db.get_setting("tmp") is None
        assert not db.delete_setting("tmp")


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