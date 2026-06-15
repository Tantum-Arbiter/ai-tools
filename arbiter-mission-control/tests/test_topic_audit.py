"""Comprehensive audit of topic and intent detection - false-positive stress test."""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Inline the detection logic to avoid importing full server (heavy deps)
_TOPIC_RULES = {
    "stocks": {
        "phrases": ["stock market", "markets today", "share price", "dow jones",
                    "apple stock", "tesla stock", "microsoft stock", "nvidia stock",
                    "the market", "how are markets", "how's the market"],
        "words":   ["stock", "stocks", "ticker", "portfolio", "nasdaq", "s&p",
                    "trading", "shares", "dividend", "equity", "securities"],
        "negative": ["app market", "market research", "market analysis", "market size",
                     "market share", "market opportunity", "market segment",
                     "job market", "labour market", "labor market", "real estate market",
                     "housing market", "market strategy", "market fit", "market demand",
                     "market trend", "market report", "market study", "market growth",
                     "market landscape", "market overview", "market potential",
                     "go to market", "target market", "market niche", "market value",
                     "children market", "kids market", "child market",
                     "gaming market", "music market", "food market", "health market",
                     "fitness market", "education market", "crypto market",
                     "market plan", "marketplace", "market cap",
                     "trading card", "stock photo", "stock up", "stocking",
                     "restock", "overstock", "livestock", "woodstock",
                     "laughing stock", "rolling stock", "gunstock"],
    },
    "weather": {
        "phrases": ["weather today", "weather like", "weather in", "weather for",
                    "weather this", "weather tomorrow", "check weather",
                    "rain today", "rain tomorrow", "is it raining",
                    "wind speed", "wind chill"],
        "words":   ["weather"],
        "negative": ["forecast my", "forecast the revenue", "forecast sales",
                     "rain check", "brainstorm", "political climate",
                     "business climate", "climate of the", "climate change",
                     "wind down", "wind up the", "winding down",
                     "temperature of the debate", "humidity in code"],
    },
    "revenue": {
        "phrases": ["my revenue", "our revenue", "app revenue", "total revenue",
                    "revenue growth", "monthly revenue", "revenuecat",
                    "subscriber count", "active subscribers", "churn rate",
                    "my income", "our income", "my earnings", "mrr"],
        "words":   ["revenuecat"],
        "negative": ["earning potential", "earning a living", "income tax",
                     "income inequality", "passive income", "income ideas",
                     "national income", "revenue model for", "revenue of"],
    },
    "services": {
        "phrases": ["cloudflare", "service health", "service status", "uptime",
                    "openai status", "github status", "aws status",
                    "anthropic status", "claude status", "services down",
                    "services status", "all services", "is it down"],
        "words":   ["outage", "degraded"],
        "negative": [],
    },
    "gcp": {
        "phrases": ["cloud run", "app engine", "cloud sql", "google cloud",
                    "gcp project", "gcp infrastructure"],
        "words":   ["gcp", "kubernetes"],
        "negative": ["deploy my app", "deploy my react", "deploy to vercel",
                     "deploy to netlify", "deploy a website",
                     "infrastructure of", "infrastructure for"],
    },
    "email": {
        "phrases": ["my email", "my inbox", "check email", "check inbox",
                    "unread email", "urgent mail", "urgent email",
                    "read my email", "any emails"],
        "words":   ["inbox", "gmail", "unread"],
        "negative": ["email marketing", "email design", "email template",
                     "email strategy", "email campaign", "email list",
                     "email service", "email api", "email provider",
                     "email format", "email best practice"],
    },
    "news": {
        "phrases": ["latest news", "news today", "top news", "breaking news",
                    "news headlines", "bbc news", "in the news",
                    "what's in the news", "news stories"],
        "words":   ["bbc"],
        "negative": ["headline feature", "headline act", "stories about",
                     "user stories", "what is new in", "any news on my",
                     "news to me"],
    },
    "sports": {
        "phrases": ["premier league", "football results", "football scores",
                    "league table", "match results", "match score",
                    "sports news", "sports results", "sports scores",
                    "who won the", "who plays"],
        "words":   [],
        "negative": ["match these", "match the", "matching", "score this",
                     "score it", "scoring criteria", "league of legends",
                     "football shaped"],
    },
    "roadmap": {
        "phrases": ["the roadmap", "my roadmap", "our roadmap", "show roadmap",
                    "product roadmap", "strategic plan", "release plan",
                    "business plan", "mvp plan", "mvp launch",
                    "launch plan", "quarterly plan", "go-to-market plan"],
        "words":   ["roadmap"],
        "negative": ["timeline of", "timeline for ww", "timeline for world",
                     "milestone in human", "milestone in history",
                     "deploy my", "deploy a", "deploy to",
                     "deadline for the", "rollout of the"],
    },
    "comfyui": {
        "phrases": ["generate an image", "generate image", "generate a image",
                    "create an image", "create image", "create a image",
                    "generate a video", "generate video", "create a video",
                    "create video", "make a photo", "make a picture",
                    "make an image", "make a video"],
        "words":   [],
        "negative": ["render a react", "render a component", "render the page",
                     "render a view", "render this", "render that",
                     "design a database", "design a schema", "design a system",
                     "design a api", "design a class", "design a module",
                     "draw conclusions", "draw a diagram", "draw from"],
    },
}

_TOPIC_WORD_PATTERNS = {}
for _t, _r in _TOPIC_RULES.items():
    if _r["words"]:
        _pat = r'\b(' + '|'.join(re.escape(w) for w in _r["words"]) + r')\b'
        _TOPIC_WORD_PATTERNS[_t] = re.compile(_pat, re.IGNORECASE)


def _detect_topic(query):
    q = query.lower()
    for topic, rules in _TOPIC_RULES.items():
        matched = False
        if any(p in q for p in rules["phrases"]):
            matched = True
        if not matched and topic in _TOPIC_WORD_PATTERNS:
            if _TOPIC_WORD_PATTERNS[topic].search(q):
                matched = True
        if not matched:
            continue
        if rules["negative"] and any(neg in q for neg in rules["negative"]):
            continue
        return topic
    return None

def test_stocks_false_positives():
    """Phrases with 'market/stock/trading' that are NOT about financial stocks."""
    cases = [
        "children app market", "market research for my startup",
        "what is the saas market like", "is there a market for this",
        "market cap of the ai industry", "trading card game ideas",
        "stock photos for my website", "stock up on groceries",
        "restocking inventory", "overstock clearance",
        "livestock farming tips", "woodstock festival history",
        "laughing stock", "rolling stock of trains",
    ]
    for q in cases:
        result = _detect_topic(q.lower())
        assert result != "stocks", f'FALSE POS: "{q}" -> stocks'

def test_weather_false_positives():
    """Phrases with weather keywords that aren't about weather."""
    cases = [
        "forecast my revenue", "rain check on that meeting",
        "the political climate", "wind down the project",
        "climate of the office", "temperature of the debate",
        "humidity in code review",
    ]
    for q in cases:
        result = _detect_topic(q.lower())
        assert result != "weather", f'FALSE POS: "{q}" -> weather'

def test_news_false_positives():
    cases = [
        "what is new in react", "any news on my deploy",
        "headline features of the app",
    ]
    for q in cases:
        result = _detect_topic(q.lower())
        assert result != "news", f'FALSE POS: "{q}" -> news'

def test_sports_false_positives():
    cases = [
        "match these colors", "score this idea out of 10",
        "league of legends tips", "football shaped cake",
    ]
    for q in cases:
        result = _detect_topic(q.lower())
        assert result != "sports", f'FALSE POS: "{q}" -> sports'

def test_revenue_false_positives():
    cases = [
        "earning potential of ai careers", "income tax tips uk",
        "passive income ideas",
    ]
    for q in cases:
        result = _detect_topic(q.lower())
        assert result != "revenue", f'FALSE POS: "{q}" -> revenue'

def test_email_false_positives():
    cases = [
        "email marketing strategies", "best email design patterns",
        "email template for job application",
    ]
    for q in cases:
        result = _detect_topic(q.lower())
        assert result != "email", f'FALSE POS: "{q}" -> email'

def test_roadmap_false_positives():
    cases = [
        "timeline of world war 2", "deploy my react app to vercel",
        "milestone in human history",
    ]
    for q in cases:
        result = _detect_topic(q.lower())
        assert result != "roadmap", f'FALSE POS: "{q}" -> roadmap'

def test_comfyui_false_positives():
    cases = [
        "render a react component", "design a database schema",
        "draw conclusions from the data",
    ]
    for q in cases:
        result = _detect_topic(q.lower())
        assert result != "comfyui", f'FALSE POS: "{q}" -> comfyui'

def test_correct_detections():
    """These SHOULD correctly detect their topic."""
    expected = {
        "how are stocks doing": "stocks",
        "tesla stock price": "stocks",
        "stock market today": "stocks",
        "whats the weather like": "weather",
        "check my inbox": "email",
        "is cloudflare down": "services",
        "premier league results": "sports",
        "what is my mrr": "revenue",
        "show me the roadmap": "roadmap",
        "generate an image of a cat": "comfyui",
        "nasdaq is up today": "stocks",
        "dow jones performance": "stocks",
    }
    for q, exp in expected.items():
        result = _detect_topic(q.lower())
        assert result == exp, f'MISSED: "{q}" -> {result} (expected {exp})'

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
