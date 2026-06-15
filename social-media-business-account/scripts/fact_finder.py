"""
Fact Finder
Uses OpenAI GPT-4o with built-in web search (Responses API) to find a
fresh parenting or child development fact each day.

Called once per day by the orchestrator. Result is cached in SQLite
so all posts that day reference the same fact (brand consistency),
but the content angles vary.
"""
import os
import json
import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger(__name__)

# One search prompt per psychology trigger.
# Each prompt finds a fact that PROVES the emotional truth the trigger delivers.
# The fact becomes evidence, not decoration.
TRIGGER_SEARCH_PROMPTS = {
    "guilt_relief": """Search for a credible fact or research finding that REASSURES parents
they do not need to be perfect. Look for:
- Research showing children of 'good enough' parents thrive
- Studies on parental imperfection and child resilience
- Evidence that common parenting worries are unfounded
- Facts that reframe guilt into something positive
The fact must make a tired, worried parent feel LIGHTER — not more anxious.""",

    "identity_validation": """Search for a credible fact or research finding that confirms:
worrying about your child is itself a sign of good parenting.
Look for:
- Research linking parental attunement to child outcomes
- Studies showing that self-reflective parents raise emotionally healthier children
- Evidence that parents who question themselves are more responsive caregivers
The fact must make a parent think: 'The fact that I care this much means I'm doing it right.'""",

    "curiosity_gap": """Search for a surprising, counterintuitive, or little-known fact about
child development (ages 0-6) that most parents would not already know.
Look for:
- Unexpected brain development findings
- Surprising benefits of ordinary parenting moments (bath time, car journeys, messy play)
- Counterintuitive research about toddler behaviour
- Hidden developmental milestones parents often miss
Must be genuinely surprising — avoid well-known advice parents have heard before.""",

    "paradox_hook": """Search for a research finding that CONTRADICTS common parenting advice
but in a reassuring way. Look for:
- Studies showing popular parenting trends are unnecessary
- Evidence that simpler approaches outperform complex ones
- Research that gives parents permission to stop doing something stressful
- Findings that challenge 'perfect parenting' myths
Must be counterintuitive AND ultimately reassuring — not alarming.""",

    "social_proof_belonging": """Search for a fact or statistic that shows how COMMON and NORMAL
parenting struggles are. Look for:
- Statistics on how many parents feel overwhelmed, lonely, or guilty
- Research showing that parenting anxiety is universal, not a personal failure
- Data on how widespread specific struggles are (toddler tantrums, sleep issues, etc.)
- Studies showing parents systematically underestimate how much others struggle too
The fact must make a parent feel: 'It's not just me. We're all in this together.'""",

    "practical_hope": """Search for a fact showing that a SMALL, SIMPLE action has a significant
positive impact on child development. Look for:
- Research on micro-moments of connection (10 minutes of focused play, etc.)
- Studies on the outsized impact of small daily habits (reading, talking, singing)
- Evidence that imperfect but consistent parenting beats perfect but inconsistent
- Findings on how brief positive interactions shape brain development
The fact must give a parent a concrete reason to believe small efforts matter enormously.""",
}

# Shared requirements appended to every trigger-specific prompt
SHARED_REQUIREMENTS = """
Requirements for ALL facts:
- Must be specific and verifiable (cite a study, organisation, or expert)
- Must be REASSURING or EMPOWERING — never alarming or guilt-inducing
- Must be genuinely interesting and worth sharing
- Must NOT be generic advice parents have heard a thousand times

Return ONLY a JSON object:
{
  "fact": "The specific interesting fact in one or two sentences",
  "source": "Organisation, study, or expert name",
  "topic": "Brief topic label",
  "parent_angle": "One sentence on why this matters to a tired, worried parent",
  "emotional_truth": "The deeper emotional message this fact delivers (e.g. 'You are enough')",
  "content_hook_ideas": ["hook idea 1", "hook idea 2", "hook idea 3"]
}"""


class FactFinder:
    def __init__(self, db_path: str = "data/state.db"):
        self.db_path = db_path
        self._ensure_table()

    def get_daily_fact(self, trigger: str) -> dict:
        """Return a fact matched to the psychology trigger.

        Cached by date+trigger — so each trigger gets its own fact per day,
        and repeated runs within the day are free (no extra API calls).
        """
        today = date.today().isoformat()
        cache_key = f"{today}:{trigger}"
        cached = self._load_from_cache(cache_key)
        if cached:
            log.info(f"Cached fact [{trigger}]: {cached['topic']}")
            return cached

        log.info(f"Searching for fact matched to trigger: {trigger}")
        fact = self._search_fact(trigger)
        self._save_to_cache(cache_key, fact)
        log.info(f"Fact found [{trigger}]: {fact['fact'][:80]}...")
        return fact

    def _search_fact(self, trigger: str) -> dict:
        """Call OpenAI Responses API with web_search_preview, using trigger-specific prompt."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY required for FactFinder.")

        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        trigger_prompt = TRIGGER_SEARCH_PROMPTS.get(trigger, TRIGGER_SEARCH_PROMPTS["guilt_relief"])
        full_prompt = f"{trigger_prompt}\n{SHARED_REQUIREMENTS}"

        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            tools=[{"type": "web_search_preview"}],
            input=full_prompt,
        )

        raw = response.output_text.strip()
        return self._parse(raw, trigger)

    def _parse(self, raw: str, trigger: str = "guilt_relief") -> dict:
        """Parse JSON response, stripping markdown fences if present."""
        text = raw
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            log.warning(f"Could not parse fact JSON for trigger '{trigger}'. Using fallback.")
            return self._fallback_fact(trigger)

    # Pre-written fallbacks — one per trigger — used if web search fails
    FALLBACK_FACTS = {
        "guilt_relief": {
            "fact": "Psychologist Donald Winnicott's research found that 'good enough' parenting — not perfect parenting — produces the most emotionally resilient children.",
            "source": "Donald Winnicott, paediatrician and psychoanalyst",
            "topic": "Parenting imperfection and child resilience",
            "parent_angle": "You are not supposed to be perfect. Science says so.",
            "emotional_truth": "You are enough, exactly as you are.",
            "content_hook_ideas": [
                "The researcher who proved perfect parenting is actually harmful",
                "You're not failing — you're 'good enough', and that's exactly right",
                "Stop trying to be a perfect parent — here's what your child actually needs",
            ],
        },
        "identity_validation": {
            "fact": "Research shows that parents who frequently reflect on their own childhood and parenting choices raise children with significantly stronger emotional intelligence.",
            "source": "Dr Daniel Siegel, UCLA School of Medicine",
            "topic": "Reflective parenting and child outcomes",
            "parent_angle": "The fact that you're thinking about this means you're already doing it right.",
            "emotional_truth": "Your self-awareness is your greatest parenting strength.",
            "content_hook_ideas": [
                "The fact that you worry about being a good parent means you already are one",
                "The one quality that predicts emotionally intelligent children",
                "You don't need to be calm all the time — you just need to do this",
            ],
        },
        "curiosity_gap": {
            "fact": "Babies as young as 6 months old can detect when an adult is being insincere — they watch who the adult looks at before deciding whether to trust them.",
            "source": "University of British Columbia developmental psychology research",
            "topic": "Infant social cognition",
            "parent_angle": "Your baby is reading you far more deeply than you realise.",
            "emotional_truth": "Your child sees you — and they like what they see.",
            "content_hook_ideas": [
                "Your 6-month-old already knows when you're faking it",
                "The one thing babies notice that most parents don't realise",
                "Babies can detect insincerity — what that means for bedtime",
            ],
        },
        "paradox_hook": {
            "fact": "Studies show that toddlers who are allowed to experience boredom develop stronger creativity and problem-solving skills than those with constantly structured activities.",
            "source": "Association for Psychological Science",
            "topic": "Benefits of unstructured time for toddlers",
            "parent_angle": "Doing less is often the most developmental thing you can do.",
            "emotional_truth": "You don't need to entertain them. You need to trust them.",
            "content_hook_ideas": [
                "Stop trying to entertain your toddler — here's what they actually need",
                "The activity most parents feel guilty about is actually great for development",
                "Why boredom is the most underrated parenting tool",
            ],
        },
        "social_proof_belonging": {
            "fact": "A 2023 survey found that 9 in 10 parents feel they are failing at least one aspect of parenting — yet rate other parents they know as doing 'much better' than themselves.",
            "source": "Parenting Research Centre, 2023",
            "topic": "Parenting guilt and social comparison",
            "parent_angle": "Every parent around you feels exactly the way you do. None of them are showing it.",
            "emotional_truth": "You are not alone. You never were.",
            "content_hook_ideas": [
                "9 in 10 parents feel like they're failing — are you one of them?",
                "Every parent you admire feels exactly the way you do right now",
                "If you've ever felt like the only one struggling, this is for you",
            ],
        },
        "practical_hope": {
            "fact": "Children who are read to for just 15 minutes a day hear approximately 1 million more words per year — directly linked to vocabulary, literacy, and school readiness.",
            "source": "Scholastic / American Academy of Pediatrics",
            "topic": "Benefits of reading with children",
            "parent_angle": "15 minutes is achievable — even on the hardest days.",
            "emotional_truth": "Small, consistent moments are enough. You are enough.",
            "content_hook_ideas": [
                "15 minutes tonight adds 1 million words to your child's future",
                "You don't need a perfect bedtime routine — just this one thing",
                "The simplest thing you can do for your child's brain, starting tonight",
            ],
        },
    }

    def _fallback_fact(self, trigger: str) -> dict:
        """Return a pre-written fallback matched to the trigger."""
        return self.FALLBACK_FACTS.get(trigger, self.FALLBACK_FACTS["guilt_relief"])

    # ── SQLite cache ──────────────────────────────────────────────────
    def _ensure_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_facts (
                    date        TEXT PRIMARY KEY,
                    fact_json   TEXT NOT NULL,
                    created_at  TEXT DEFAULT (datetime('now'))
                )
            """)

    def _load_from_cache(self, cache_key: str) -> dict | None:
        # cache_key format: "YYYY-MM-DD:trigger_name"
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT fact_json FROM daily_facts WHERE date = ?", (cache_key,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def _save_to_cache(self, cache_key: str, fact: dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO daily_facts (date, fact_json) VALUES (?, ?)",
                (cache_key, json.dumps(fact)),
            )
