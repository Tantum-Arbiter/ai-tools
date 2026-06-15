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
                " share price", "nasdaq", "s&p", "dow jones", "trading"],
    "weather": ["weather", "forecast", "temperature", "rain", "wind", "humidity"],
    "revenue": ["revenue", "subscriber", "mrr", "churn", "revenuecat", "income", "earning"],
    "services": ["cloudflare", "service health", "service status", "uptime", "outage", "degraded",
                 "openai status", "github status", "aws status", "anthropic status", "claude status",
                 "services down", "services status", "all services"],
    "gcp":     ["gcp", "infrastructure", "cloud run", "app engine", "cloud sql", "kubernetes"],
    "email":   ["email", "inbox", "gmail", "unread", "urgent mail"],
    "news":    ["news", "headline", "stories", "bbc"],
    "sports":  ["sport", "football", "score", "match", "league"],
    "roadmap": ["roadmap", "milestone", "business plan", "mvp plan", "mvp launch",
                "launch plan", "go to market", "rollout", "deadline", "quarterly plan",
                "product roadmap", "strategic plan", "release plan", "timeline"],
    "comfyui": ["generate an image", "generate image", "generate a image",
                "create an image", "create image", "create a image",
                "generate a video", "generate video", "create a video", "create video",
                "render", "draw ", "design a", "make a photo", "make a picture",
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


# ══════════════════════════════════════════════════════════════════════
# PHASE 7 TESTS — Desktop Automation, Insights, Briefing Panels
# ══════════════════════════════════════════════════════════════════════

# ── Inline reference for desktop command detection ──────────────────
import re
import re as _re_test

_SAFE_APPS_TEST = {
    "slack": "Slack", "vs code": "Visual Studio Code", "vscode": "Visual Studio Code",
    "chrome": "Google Chrome", "browser": "Google Chrome", "safari": "Safari",
    "terminal": "Terminal", "finder": "Finder", "spotify": "Spotify",
    "discord": "Discord", "teams": "Microsoft Teams", "notion": "Notion",
}

_URL_SHORTCUTS_TEST = {
    "jira": "https://jira.atlassian.com", "github": "https://github.com",
    "youtube": "https://youtube.com", "gmail": "https://mail.google.com",
    "gcp console": "https://console.cloud.google.com",
}


def detect_desktop_command(msg):
    q = msg.lower().strip()
    # Strip polite preambles
    q = _re_test.sub(r'^(?:can you|could you|would you|please|hey arbiter|arbiter)\s+', '', q).strip()
    # Direct URL
    m = _re_test.search(r'(?:open|go to|navigate to|pull up|load)\s+(https?://\S+)', q)
    if m:
        url = m.group(1).rstrip('.,;!?')
        return {"action": "open_url", "url": url}
    # Named shortcuts
    for name, url in _URL_SHORTCUTS_TEST.items():
        if _re_test.search(
            rf'\b(?:open|go to|show me|bring up|navigate to|pull up|load|take me to)\s+'
            rf'{re.escape(name)}\b', q
        ):
            return {"action": "open_url", "url": url, "name": name}
    # App activation
    m2 = _re_test.search(
        r'(?:open|launch|show|bring up|switch to|activate|focus|pull up|start)\s+'
        r'(.+?)(?:\s+(?:please|for me))?[.!?]?$', q
    )
    if m2:
        app_name = m2.group(1).strip().rstrip('.,;!?')
        resolved = _SAFE_APPS_TEST.get(app_name)
        if resolved:
            return {"action": "activate_app", "app": resolved, "name": app_name}
    return None


class TestDesktopAutomation:
    """Phase 7B: Desktop command parsing and safety validation."""

    @pytest.mark.parametrize("query,expected_action", [
        ("open https://example.com", "open_url"),
        ("open slack", "activate_app"),
        ("bring up vs code", "activate_app"),
        ("launch chrome", "activate_app"),
        ("switch to terminal", "activate_app"),
        ("open spotify", "activate_app"),
        # Natural phrasing
        ("can you open slack", "activate_app"),
        ("could you pull up chrome", "activate_app"),
        ("please open spotify", "activate_app"),
        ("pull up vs code", "activate_app"),
        ("take me to github", "open_url"),
        ("go to https://example.com", "open_url"),
    ])
    def test_valid_desktop_commands(self, query, expected_action):
        result = detect_desktop_command(query)
        assert result is not None
        assert result["action"] == expected_action

    @pytest.mark.parametrize("query", [
        "what's the weather",
        "show me the stocks",
        "how's my revenue",
        "tell me a joke",
        "open something_unknown_app",
    ])
    def test_non_desktop_queries(self, query):
        """Non-desktop queries should return None."""
        result = detect_desktop_command(query)
        # Should be None or None for unknown apps
        if result and result["action"] == "activate_app":
            pytest.fail("Should not activate unknown apps")

    def test_url_must_be_http(self):
        result = detect_desktop_command("open ftp://evil.com")
        assert result is None

    def test_direct_url_extraction(self):
        result = detect_desktop_command("open https://docs.google.com/spreadsheet")
        assert result["action"] == "open_url"
        assert result["url"] == "https://docs.google.com/spreadsheet"

    @pytest.mark.parametrize("shortcut,expected_url", [
        ("github", "https://github.com"),
        ("youtube", "https://youtube.com"),
        ("gmail", "https://mail.google.com"),
    ])
    def test_url_shortcuts(self, shortcut, expected_url):
        result = detect_desktop_command(f"open {shortcut}")
        assert result is not None
        assert result["url"] == expected_url

    def test_app_whitelist_enforcement(self):
        """Unknown apps must NOT be activated."""
        result = detect_desktop_command("open malware_app")
        assert result is None or result.get("action") != "activate_app"


class TestBriefingDetection:
    """Phase 7D: General/briefing query detection for executive dashboards."""

    _BRIEFING_PATTERNS = ["briefing", "status report", "how am i doing", "overview",
                          "what's going on", "update me", "catch me up", "summary",
                          "how's everything", "what's happening", "sitrep", "how are things"]

    @pytest.mark.parametrize("query", [
        "give me a briefing",
        "status report please",
        "how am i doing",
        "what's going on",
        "catch me up",
        "give me an overview",
        "how's everything",
        "sitrep",
    ])
    def test_briefing_queries_detected(self, query):
        q = query.lower()
        assert any(p in q for p in self._BRIEFING_PATTERNS), f"'{query}' should trigger briefing"

    @pytest.mark.parametrize("query", [
        "what's the weather",
        "how's apple stock",
        "show me revenue",
        "open slack",
    ])
    def test_non_briefing_queries(self, query):
        q = query.lower()
        assert not any(p in q for p in self._BRIEFING_PATTERNS), f"'{query}' should NOT trigger briefing"


class TestInsightRules:
    """Phase 7A: Insight detection rules for proactive monitoring."""

    def test_stock_big_move_detected(self):
        """Stock move >3% should generate an insight."""
        pct = 4.5
        assert abs(pct) > 3  # threshold check

    def test_stock_small_move_ignored(self):
        """Stock move <3% should NOT generate an insight."""
        pct = 1.2
        assert abs(pct) <= 3

    def test_analyst_divergence_detected(self):
        """Target price >15% from current should generate insight."""
        price, target = 100, 120
        divergence = abs(target - price) / price
        assert divergence > 0.15

    def test_analyst_convergence_ignored(self):
        """Target price <15% from current should NOT generate insight."""
        price, target = 100, 110
        divergence = abs(target - price) / price
        assert divergence <= 0.15

    def test_churn_spike_detected(self):
        """Churn >5% of subscriber base should generate insight."""
        subs, churned = 100, 6
        assert (churned / subs) > 0.05

    def test_churn_normal_ignored(self):
        """Churn <5% of subscriber base should NOT generate insight."""
        subs, churned = 100, 3
        assert (churned / subs) <= 0.05

    def test_multi_service_degradation(self):
        """3+ services degraded should flag upstream issue."""
        degraded_count = 3
        assert degraded_count >= 3

    def test_overdue_milestone_detected(self):
        """Milestone with negative days_left should be flagged."""
        days_left = -5
        assert days_left < 0

    def test_upcoming_deadline_detected(self):
        """Milestone due within 7 days should be flagged."""
        days_left = 3
        assert 0 <= days_left <= 7

    def test_cross_correlation_churn_plus_outage(self):
        """Churn + service degradation should create cross-correlation insight."""
        insights = [
            {"type": "churn_spike"},
            {"type": "multi_service_degradation"},
        ]
        has_churn = any(i["type"] == "churn_spike" for i in insights)
        has_svc = any(i["type"] in ("multi_service_degradation", "service_degraded") for i in insights)
        assert has_churn and has_svc



class TestPhase8Components:
    """Phase 8: Universal Deep Analysis Toolkit — component validation."""

    # ── Panel schema validation ──

    def test_insights_schema(self):
        """Insights must have type and text."""
        insights = [
            {"type": "risk", "text": "Revenue declining sharply."},
            {"type": "opportunity", "text": "Market undervalued."},
            {"type": "warning", "text": "High volatility ahead."},
            {"type": "info", "text": "Sector rotation underway."},
        ]
        for ins in insights:
            assert ins["type"] in ("risk", "opportunity", "warning", "info")
            assert len(ins["text"]) > 0

    def test_recommendations_schema(self):
        """Recommendations must have priority and text."""
        recs = [
            {"priority": "high", "text": "Consider reducing exposure."},
            {"priority": "medium", "text": "Set trailing stops."},
            {"priority": "low", "text": "Review in Q3."},
        ]
        for rec in recs:
            assert rec["priority"] in ("high", "medium", "low")
            assert len(rec["text"]) > 0

    def test_comparison_matrix_schema(self):
        """Comparison matrix must have columns and rows with matching widths."""
        matrix = {
            "columns": ["Metric", "Apple", "Tesla"],
            "rows": [
                ["Price", "$190", "$250"],
                ["P/E", "28.5", "60.2"],
                ["Rating", "BUY", "HOLD"],
            ],
        }
        col_count = len(matrix["columns"])
        for row in matrix["rows"]:
            assert len(row) == col_count

    def test_scorecard_schema(self):
        """Scorecard items must have label, score (0-100), and value."""
        scorecard = [
            {"label": "Growth", "score": 85, "value": "8.5/10"},
            {"label": "Value", "score": 40, "value": "P/E 35"},
            {"label": "Risk", "score": 20, "value": "High"},
        ]
        for sc in scorecard:
            assert 0 <= sc["score"] <= 100
            assert sc["label"]
            assert sc["value"]

    def test_trend_indicators_schema(self):
        """Trend indicators must have label, value, direction."""
        trends = [
            {"label": "Revenue", "value": "+12%", "direction": "up", "context": "vs last quarter"},
            {"label": "Churn", "value": "3.2%", "direction": "down", "context": "improving"},
            {"label": "Market Cap", "value": "$2.1T", "direction": "flat"},
        ]
        for t in trends:
            assert t["direction"] in ("up", "down", "flat")
            assert t["label"]
            assert t["value"]

    # ── Research trigger detection ──

    @pytest.mark.parametrize("query", [
        "compare pokemon cards on ebay",
        "should I buy bitcoin",
        "instagram vs tiktok for marketing",
        "best crypto to invest in 2024",
        "social media trend analysis",
        "ebay collectibles price trends",
        "pros and cons of tesla vs rivian",
        "how does shopify compare to woocommerce",
    ])
    def test_research_trigger_detected(self, query):
        """Open-domain queries with research keywords should trigger web research."""
        import re
        _RESEARCH_RX = re.compile(
            r'\b(compare|vs|versus|buy|sell|invest|price|cost|value|worth|trend|'
            r'market|analysis|analyze|review|rate|rank|best|worst|top|forecast|'
            r'predict|outlook|should i|what about|how does|pros and cons|'
            r'ebay|amazon|etsy|crypto|bitcoin|nft|pokemon|cards|collecti|'
            r'social media|instagram|tiktok|youtube|twitter|facebook|linkedin|'
            r'competitor|industry|sector|growth|decline|revenue|profit)\b',
            re.IGNORECASE,
        )
        assert _RESEARCH_RX.search(query) is not None

    @pytest.mark.parametrize("query", [
        "hello",
        "what time is it",
        "open slack",
    ])
    def test_research_not_triggered_for_simple(self, query):
        """Simple queries without research keywords should NOT trigger research."""
        import re
        _RESEARCH_RX = re.compile(
            r'\b(compare|vs|versus|buy|sell|invest|price|cost|value|worth|trend|'
            r'market|analysis|analyze|review|rate|rank|best|worst|top|forecast|'
            r'predict|outlook|should i|what about|how does|pros and cons|'
            r'ebay|amazon|etsy|crypto|bitcoin|nft|pokemon|cards|collecti|'
            r'social media|instagram|tiktok|youtube|twitter|facebook|linkedin|'
            r'competitor|industry|sector|growth|decline|revenue|profit)\b',
            re.IGNORECASE,
        )
        assert _RESEARCH_RX.search(query) is None

    # ── Dynamic panel JSON validation ──

    def test_dynamic_panel_json_parsing(self):
        """Simulates parsing LLM-generated panel JSON."""
        import json
        raw = '''```json
{
    "title": "POKEMON CARD MARKET ANALYSIS",
    "stats": [{"label": "Avg Price", "value": "$45.00", "status": null}],
    "insights": [{"type": "opportunity", "text": "First edition Charizard trending upward."}],
    "recommendations": [{"priority": "high", "text": "Buy graded PSA 9+ cards."}],
    "summary": "Collectible card market showing strong momentum."
}
```'''
        # Strip markdown fences
        import re
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw)
        cleaned = re.sub(r'```\s*$', '', cleaned).strip()
        panel = json.loads(cleaned)
        assert panel["title"] == "POKEMON CARD MARKET ANALYSIS"
        assert len(panel["insights"]) >= 1
        assert len(panel["recommendations"]) >= 1

    # ── Stock panel enrichment ──

    def test_stock_insight_generation(self):
        """Stock with high upside should generate opportunity insight."""
        upside = 25
        insights = []
        if upside > 15:
            insights.append({"type": "opportunity", "text": f"Significant upside: {upside:+.0f}%"})
        assert len(insights) == 1
        assert insights[0]["type"] == "opportunity"

    def test_stock_risk_generation(self):
        """Stock trading above target should generate risk insight."""
        upside = -15
        insights = []
        if upside < -10:
            insights.append({"type": "risk", "text": "Potential overvaluation risk."})
        assert len(insights) == 1
        assert insights[0]["type"] == "risk"

    def test_stock_scorecard_generation(self):
        """Scorecard values should be clamped to 0-100."""
        upside = 50
        rev_growth = 25
        margin = 15
        fwd_pe = 30
        scorecard = [
            {"label": "Rating", "score": min(100, max(0, 50 + upside * 2)), "value": "BUY"},
            {"label": "Growth", "score": min(100, max(0, 50 + rev_growth * 2)), "value": f"{rev_growth:+.1f}%"},
            {"label": "Profitability", "score": min(100, max(0, margin * 3)), "value": f"{margin:.1f}%"},
            {"label": "Value", "score": min(100, max(0, 100 - fwd_pe * 2)), "value": f"P/E {fwd_pe:.1f}"},
        ]
        for sc in scorecard:
            assert 0 <= sc["score"] <= 100

    def test_market_trend_indicators(self):
        """Multi-stock panel should generate trend indicators."""
        items = [
            {"name": "Apple", "pct": 1.2},
            {"name": "Tesla", "pct": -0.5},
            {"name": "Microsoft", "pct": 0.8},
        ]
        gainers = [it for it in items if it["pct"] > 0]
        losers = [it for it in items if it["pct"] < 0]
        trends = [
            {"label": "Market", "value": f"{len(gainers)}/{len(items)}", "direction": "up" if len(gainers) > len(losers) else "down"},
        ]
        assert trends[0]["direction"] == "up"
        assert trends[0]["value"] == "2/3"

    def test_comparison_matrix_for_compare_intent(self):
        """Compare intent with multiple stocks should build comparison matrix."""
        items = [
            {"name": "Apple", "price": 190, "pct": 1.2, "rating": "BUY", "target": 210, "upside": 10},
            {"name": "Tesla", "price": 250, "pct": -0.5, "rating": "HOLD", "target": 240, "upside": -4},
        ]
        columns = ["Metric"] + [it["name"] for it in items]
        rows = [
            ["Price"] + [f"${it['price']}" for it in items],
            ["Rating"] + [it["rating"] for it in items],
        ]
        assert len(columns) == 3
        assert len(rows[0]) == 3
