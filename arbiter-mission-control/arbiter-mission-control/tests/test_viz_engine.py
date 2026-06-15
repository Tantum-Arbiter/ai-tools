"""
Tests for the Intelligent Visualization Toolkit.

Tests intent classification, topic detection, viz selection rules,
panel structure validation, and ComfyUI creative action routing.

These tests validate the PLANNED engine (Phases 1-5).
Functions under test will be implemented in server.py during each phase.
Run: pytest tests/test_viz_engine.py -v
"""
import pytest


# ── Helpers (will be extracted from server.py in Phase 1) ──────────────
# Inline reference implementations for testing the design contract.

INTENT_PATTERNS = {
    "compare": ["compare", " vs ", "versus", "against", "better", "which is", "difference"],
    "trend":   ["trend", "over time", "this week", "this month", "history", "forecast", "projection"],
    "breakdown": ["breakdown", "break down", "split", "composition", "what makes up", "made up of"],
    "snapshot": ["how's", "how is", "what's", "status", "current", "right now", "overview"],
    "detail":  ["tell me about", "what is", "explain", "deep dive", "details on", "more about"],
    "rank":    ["top", "best", "worst", "highest", "lowest", "most", "least", "ranking"],
}

TOPIC_KEYWORDS = {
    "stocks":  ["stock", "the market", "stock market", "markets today", "ticker", "portfolio",
                " share price", "nasdaq", "s&p", "dow jones", "trading",
                "apple stock", "tesla stock", "microsoft stock", "nvidia stock"],
    "weather": ["weather", "forecast", "temperature", "rain", "wind", "humidity", "climate"],
    "revenue": ["revenue", "subscriber", "mrr", "churn", "revenuecat", "income", "earning"],
    "services": ["cloudflare", "service health", "service status", "uptime", "outage", "degraded",
                 "openai status", "github status", "aws status", "anthropic status", "claude status",
                 "services down", "services status", "all services"],
    "gcp":     ["gcp", "infrastructure", "cloud run", "app engine", "cloud sql", "kubernetes", "deploy"],
    "email":   ["email", "inbox", "gmail", "unread", "urgent mail"],
    "news":    ["news", "headline", "stories", "bbc"],
    "sports":  ["sport", "football", "score", "match", "league", "premier league"],
    "roadmap": ["roadmap", "milestone", "business plan", "mvp plan", "mvp launch",
                "launch plan", "go to market", "rollout", "deadline", "quarterly plan",
                "product roadmap", "strategic plan", "release plan", "timeline"],
    "comfyui": ["generate an image", "generate image", "generate a image",
                "create an image", "create image", "create a image",
                "generate a video", "generate video", "create a video", "create video",
                "render ", "draw ", "design a", "make a photo", "make a picture",
                "make an image", "make a video"],
}

# Best chart type for intent × topic
VIZ_MATRIX = {
    ("stocks", "compare"):   "hbar",
    ("stocks", "trend"):     "line",
    ("stocks", "breakdown"): "doughnut",
    ("stocks", "snapshot"):  "stat_cards",
    ("stocks", "rank"):      "hbar",
    ("weather", "snapshot"):  "hero",
    ("weather", "trend"):     "line",
    ("weather", "compare"):   "stat_cards",
    ("revenue", "snapshot"):  "stat_cards",
    ("revenue", "breakdown"): "doughnut",
    ("revenue", "trend"):     "line",
    ("revenue", "compare"):   "hbar",
    ("gcp", "snapshot"):      "status_grid",
    ("gcp", "detail"):        "status_grid",
    ("email", "snapshot"):    "stat_cards",
    ("email", "breakdown"):   "doughnut",
    ("services", "snapshot"):  "status_grid",
    ("services", "detail"):    "status_grid",
    ("services", "compare"):   "status_grid",
    ("roadmap", "snapshot"):   "table",
    ("roadmap", "detail"):     "table",
    ("roadmap", "trend"):      "table",
    ("news", "snapshot"):     "table",
    ("sports", "snapshot"):   "table",
}


def classify_intent(query: str) -> str:
    q = query.lower()
    for intent, patterns in INTENT_PATTERNS.items():
        if any(p in q for p in patterns):
            return intent
    return "snapshot"  # default


def detect_topic(query: str) -> str | None:
    q = query.lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(k in q for k in keywords):
            return topic
    return None


def select_viz(topic: str, intent: str) -> str:
    return VIZ_MATRIX.get((topic, intent), "stat_cards")


def is_comfyui_action(query: str) -> bool:
    q = query.lower()
    return any(k in q for k in TOPIC_KEYWORDS["comfyui"])


# ── Intent Classification Tests ───────────────────────────────────────

class TestIntentClassification:
    @pytest.mark.parametrize("query,expected", [
        ("compare Apple and Tesla stocks", "compare"),
        ("AAPL vs GOOGL performance", "compare"),
        ("which stock is better", "compare"),
    ])
    def test_compare_intent(self, query, expected):
        assert classify_intent(query) == expected

    @pytest.mark.parametrize("query,expected", [
        ("stock trend this week", "trend"),
        ("revenue over time", "trend"),
        ("temperature forecast for London", "trend"),
        ("Microsoft projection this month", "trend"),
    ])
    def test_trend_intent(self, query, expected):
        assert classify_intent(query) == expected

    @pytest.mark.parametrize("query,expected", [
        ("break down my GCP costs", "breakdown"),
        ("revenue breakdown", "breakdown"),
        ("what makes up my expenses", "breakdown"),
    ])
    def test_breakdown_intent(self, query, expected):
        assert classify_intent(query) == expected

    @pytest.mark.parametrize("query,expected", [
        ("how's the market", "snapshot"),
        ("what's the weather", "snapshot"),
        ("GCP status right now", "snapshot"),
    ])
    def test_snapshot_intent(self, query, expected):
        assert classify_intent(query) == expected

    def test_default_intent_is_snapshot(self):
        assert classify_intent("hello there") == "snapshot"


# ── Topic Detection Tests ─────────────────────────────────────────────

class TestTopicDetection:
    @pytest.mark.parametrize("query,expected", [
        ("show me the stock market", "stocks"),
        ("what's the weather in Paris", "weather"),
        ("revenue breakdown", "revenue"),
        ("GCP infrastructure status", "gcp"),
        ("check my email", "email"),
        ("latest news headlines", "news"),
        ("football scores", "sports"),
        ("generate image of a sunset", "comfyui"),
        ("what's the cloudflare service uptime", "services"),
        ("are all services status green", "services"),
        ("is there an outage on anything", "services"),
        ("check service health", "services"),
    ])
    def test_topic_detection(self, query, expected):
        assert detect_topic(query) == expected

    def test_unknown_topic_returns_none(self):
        assert detect_topic("tell me a joke") is None

    @pytest.mark.parametrize("query", [
        "help me draft a business plan",
        "market rollout strategy for my app",
        "go to market plan",
        "plan my MVP launch",
    ])
    def test_business_queries_do_not_trigger_stocks(self, query):
        assert detect_topic(query) != "stocks"

    @pytest.mark.parametrize("query,expected", [
        ("show me the roadmap", "roadmap"),
        ("help me draft a business plan", "roadmap"),
        ("what milestones are coming up", "roadmap"),
        ("plan my MVP launch", "roadmap"),
        ("market rollout strategy for my app", "roadmap"),
        ("quarterly plan review", "roadmap"),
        ("show me the timeline", "roadmap"),
    ])
    def test_roadmap_topic_detection(self, query, expected):
        assert detect_topic(query) == expected


# ── Viz Selection Tests ───────────────────────────────────────────────

class TestVizSelection:
    def test_stocks_compare_returns_hbar(self):
        assert select_viz("stocks", "compare") == "hbar"

    def test_stocks_trend_returns_line(self):
        assert select_viz("stocks", "trend") == "line"

    def test_weather_snapshot_returns_hero(self):
        assert select_viz("weather", "snapshot") == "hero"

    def test_gcp_snapshot_returns_status_grid(self):
        assert select_viz("gcp", "snapshot") == "status_grid"

    def test_services_snapshot_returns_status_grid(self):
        assert select_viz("services", "snapshot") == "status_grid"

    def test_services_detail_returns_status_grid(self):
        assert select_viz("services", "detail") == "status_grid"

    def test_roadmap_snapshot_returns_table(self):
        assert select_viz("roadmap", "snapshot") == "table"

    def test_roadmap_detail_returns_table(self):
        assert select_viz("roadmap", "detail") == "table"

    def test_news_returns_table(self):
        assert select_viz("news", "snapshot") == "table"

    def test_unknown_combo_defaults_to_stat_cards(self):
        assert select_viz("news", "rank") == "stat_cards"


# ── ComfyUI Action Routing Tests ─────────────────────────────────────

class TestComfyUIRouting:
    @pytest.mark.parametrize("query", [
        "generate an image of a sunset over London",
        "create a video of a cat",
        "render a futuristic cityscape",
        "draw me a portrait",
        "design a logo for my app",
        "make a picture of the ocean",
    ])
    def test_comfyui_triggers(self, query):
        assert is_comfyui_action(query) is True

    @pytest.mark.parametrize("query", [
        "what's the stock market doing",
        "show me the weather",
        "how's my revenue",
        "tell me the news",
    ])
    def test_non_comfyui_queries(self, query):
        assert is_comfyui_action(query) is False


# ── Scheduler Tests ──────────────────────────────────────────────────

from datetime import datetime


def cron_matches(cron: str, dt: datetime) -> bool:
    """Inline copy of _Scheduler._cron_matches for testing."""
    parts = cron.strip().split()
    if len(parts) != 5:
        return False
    fields = [dt.minute, dt.hour, dt.day, dt.month, (dt.weekday() + 1) % 7]
    for part, val in zip(parts, fields):
        if part == "*":
            continue
        allowed = set()
        for segment in part.split(","):
            if "-" in segment:
                lo, hi = segment.split("-", 1)
                allowed.update(range(int(lo), int(hi) + 1))
            else:
                allowed.add(int(segment))
        if val not in allowed:
            return False
    return True


class TestSchedulerCron:
    def test_exact_minute_hour(self):
        dt = datetime(2026, 6, 14, 8, 0)  # Saturday 8:00 AM
        assert cron_matches("0 8 * * *", dt) is True

    def test_wrong_minute(self):
        dt = datetime(2026, 6, 14, 8, 15)
        assert cron_matches("0 8 * * *", dt) is False

    def test_wrong_hour(self):
        dt = datetime(2026, 6, 14, 9, 0)
        assert cron_matches("0 8 * * *", dt) is False

    def test_weekday_filter_mon_fri(self):
        # Monday = weekday 0 in Python → (0+1)%7 = 1 in cron
        mon = datetime(2026, 6, 15, 8, 0)  # Monday
        sat = datetime(2026, 6, 20, 8, 0)  # Saturday
        assert cron_matches("0 8 * * 1-5", mon) is True
        assert cron_matches("0 8 * * 1-5", sat) is False

    def test_wildcard_all_match(self):
        dt = datetime(2026, 1, 1, 0, 0)
        assert cron_matches("* * * * *", dt) is True

    def test_comma_list(self):
        dt_8 = datetime(2026, 6, 14, 8, 0)
        dt_12 = datetime(2026, 6, 14, 12, 0)
        dt_18 = datetime(2026, 6, 14, 18, 0)
        dt_10 = datetime(2026, 6, 14, 10, 0)
        assert cron_matches("0 8,12,18 * * *", dt_8) is True
        assert cron_matches("0 8,12,18 * * *", dt_12) is True
        assert cron_matches("0 8,12,18 * * *", dt_18) is True
        assert cron_matches("0 8,12,18 * * *", dt_10) is False

    def test_market_close_time(self):
        dt = datetime(2026, 6, 15, 16, 30)  # Monday 4:30 PM
        assert cron_matches("30 16 * * 1-5", dt) is True

    def test_evening_digest_daily(self):
        dt = datetime(2026, 6, 14, 21, 0)  # Saturday 9:00 PM
        assert cron_matches("0 21 * * *", dt) is True

    def test_invalid_cron(self):
        dt = datetime(2026, 6, 14, 8, 0)
        assert cron_matches("0 8 *", dt) is False  # only 3 fields

    def test_sunday_cron_zero(self):
        # Sunday = weekday 6 in Python → (6+1)%7 = 0 in cron
        sun = datetime(2026, 6, 14, 8, 0)  # This is actually a Sunday
        # June 14 2026 is a Sunday
        assert cron_matches("0 8 * * 0", sun) is True
        assert cron_matches("0 8 * * 1-5", sun) is False


class TestScheduleVoiceCommands:
    """Test schedule/reminder command parsing patterns."""

    SCHED_RX = __import__('re').compile(
        r'(?:remind me|set a reminder|schedule)\s+(?:to\s+)?(.+?)\s+'
        r'(?:at|every day at|daily at|every)\s+(\d{1,2}(?::\d{2})?(?:\s*(?:am|pm))?)',
        __import__('re').IGNORECASE,
    )

    @pytest.mark.parametrize("query,expected_msg,expected_time", [
        ("remind me to check emails at 9am", "check emails", "9am"),
        ("set a reminder to call the dentist at 14:30", "call the dentist", "14:30"),
        ("remind me to review pipeline at 8:00am", "review pipeline", "8:00am"),
        ("schedule daily standup every day at 10am", "daily standup", "10am"),
    ])
    def test_schedule_parsing(self, query, expected_msg, expected_time):
        m = self.SCHED_RX.search(query)
        assert m is not None, f"Failed to match: {query}"
        assert m.group(1).strip().rstrip('.,') == expected_msg
        assert m.group(2).strip() == expected_time

    @pytest.mark.parametrize("query", [
        "what's the weather like",
        "show me stocks",
        "how's my revenue doing",
    ])
    def test_non_schedule_queries(self, query):
        m = self.SCHED_RX.search(query)
        assert m is None
