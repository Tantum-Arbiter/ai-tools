"""
Brief Generator — produces psychology-driven content briefs.
Uses AIDA framework + brand guidelines to generate hooks, captions,
image prompts, and video scripts via LLM.
"""
import os
import json
import random
import logging
import yaml
from pathlib import Path
from datetime import datetime

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a social media content strategist for Grow with Freya.

Brand: A warm, trusted, parent-facing children's learning app.
Audience: Parents and caregivers of 0-6 year olds.
Voice: Calm, reassuring, knowledgeable — like a trusted friend who is also a child development expert.

You understand parenting psychology deeply:
- Parents scroll fast and feel guilt, loneliness, and overwhelm
- They need permission to not be perfect
- They respond to content that SEES them before it teaches them
- The best hooks validate emotion before offering information

AIDA structure for all video/reel content:
- Attention (0-2s): Stop-scroll hook — visual + first spoken/text line
- Interest (2-8s): Deepen emotion or curiosity — make it personal
- Desire (8-20s): The insight, reframe, or actionable tip
- Action (20-28s): Follow, save, share — one clear CTA

Psychological hook patterns (rotate, never repeat consecutively):
1. Guilt relief: "You're not failing — you're [positive reframe]"
2. Identity validation: "The fact that you worry about this means you're [quality]"
3. Curiosity gap: "The one thing most parents don't know about [behaviour]"
4. Paradox: "Stop trying to [common advice] — here's what actually works"
5. Belonging: "If you've ever felt [emotion] as a parent, this is for you"
6. Practical hope: "In just [short time], you can [positive outcome]"

Visual style: warm, soft, photorealistic, golden hour lighting, calm home environment.
Palette: warm sand, sage green, soft terracotta. NO bright primary colours.
Subjects: parent silhouette with toddler, hands, books, cozy rooms. NEVER child faces.

IMPORTANT — always return valid JSON matching the schema exactly."""

BRIEF_SCHEMA = {
    "theme": "string — content theme from brand themes",
    "psychological_hook_type": "string — which hook pattern used",
    "hook": "string — the attention-grabbing first line (max 10 words)",
    "caption": "string — full Instagram/YouTube caption (150-200 words) with line breaks",
    "hashtags": "array of 9 hashtags following brand formula: 2 broad + 4 niche + 2 intent + 1 branded",
    "image_prompt": "string — detailed ComfyUI/Stable Diffusion prompt (50-80 words)",
    "negative_prompt": "string — what to avoid in the image",
    "video_script": "string — spoken voiceover script for 25-28s video, warm and conversational",
    "music_mood": "string — audio direction (e.g. soft piano, gentle acoustic)",
    "cta": "string — call to action line",
    "risk_level": "low | medium | high",
    "risk_notes": "string — any brand safety considerations",
}


class BriefGenerator:
    def __init__(self, config_dir: Path, fact_finder=None):
        with open(config_dir / "brand.yaml") as f:
            self.brand = yaml.safe_load(f)
        self._llm = self._init_llm()
        self._fact_finder = fact_finder
        self._used_hooks = []   # Prevents repeating same trigger 3 posts in a row
        self._used_themes = []  # Prevents repeating same theme 2 days in a row

    def generate(self, content_type: str = "reel", platform: str = "instagram") -> dict:
        """Generate a complete psychology-driven content brief.

        Flow:
          1. Pick psychology trigger (rotates, never repeats 3 in a row)
          2. Fetch a fact matched to that trigger (GPT-4o web search, cached by day+trigger)
          3. LLM builds the brief where the fact PROVES the trigger's emotional truth
        """
        trigger = self._pick_trigger()
        theme = self._pick_theme()

        # Fetch a fact that proves this trigger's emotional truth
        fact = None
        if self._fact_finder:
            try:
                fact = self._fact_finder.get_daily_fact(trigger)
            except Exception as e:
                log.warning(f"Fact finder failed ({e}). Generating without fact.")

        prompt = self._build_prompt(theme, trigger, content_type, platform, fact)
        raw = self._llm(prompt)

        brief = self._parse(raw)
        brief["content_type"] = content_type
        brief["platform"] = platform
        brief["generated_at"] = datetime.utcnow().isoformat()

        log.info(f"Brief generated: theme={brief['theme']}, trigger={trigger}")
        return brief

    def _pick_trigger(self) -> str:
        """Rotate through psychology triggers — never repeat within last 3 posts."""
        patterns = self.brand["psychology"]["primary_triggers"]
        available = [p["name"] for p in patterns if p["name"] not in self._used_hooks[-3:]]
        if not available:
            available = [p["name"] for p in patterns]
        chosen = random.choice(available)
        self._used_hooks.append(chosen)
        return chosen

    def _get_trigger_meta(self, trigger: str) -> dict:
        """Return the full trigger definition from brand.yaml."""
        patterns = self.brand["psychology"]["primary_triggers"]
        return next((p for p in patterns if p["name"] == trigger), {})

    def _pick_theme(self) -> str:
        """Pick a content theme — avoid repeating last 2."""
        themes = self.brand["content_themes"]
        available = [t for t in themes if t not in self._used_themes[-2:]]
        if not available:
            available = themes
        chosen = random.choice(available)
        self._used_themes.append(chosen)
        return chosen

    def _build_prompt(self, theme: str, trigger: str, content_type: str, platform: str, fact: dict | None) -> str:
        schema_str = json.dumps(BRIEF_SCHEMA, indent=2)
        trigger_meta = self._get_trigger_meta(trigger)
        duration = "25-28 seconds" if content_type in ("reel", "short") else "static image"

        # The emotional arc: trigger defines the journey, fact proves it's true
        fact_block = ""
        if fact:
            hook_ideas = "\n".join(f"  - {h}" for h in fact.get("content_hook_ideas", []))
            fact_block = f"""
GROUNDING FACT (use this as evidence, not a headline):
Fact: {fact['fact']}
Source: {fact.get('source', 'Research')}
Emotional truth this fact proves: {fact.get('emotional_truth', fact.get('parent_angle', ''))}
Suggested hook angles:
{hook_ideas}

IMPORTANT: Do not open with the fact. Open with the EMOTION.
  1. Hook: make the parent feel SEEN (trigger: {trigger})
  2. Middle: introduce the fact naturally as proof of what they already feel
  3. End: land on the emotional truth — reassurance, not information
The fact is the backbone. The feeling is the content."""

        return f"""Generate a {content_type} content brief for {platform}.

PSYCHOLOGY TRIGGER: {trigger}
Description: {trigger_meta.get('description', '')}
Hook pattern: {trigger_meta.get('hook_pattern', '')}

CONTENT THEME: {theme}
DURATION: {duration}
DAY/TIME: {datetime.now().strftime("%A %I:%M %p")}

EMOTIONAL DIRECTION:
- Parents must feel REASSURED, not educated
- Lead with empathy, follow with evidence
- End with permission: 'You are enough. You are doing enough.'
- Safe, warm, non-alarmist tone throughout
- Never suggest a parent is failing — only that they are human
{fact_block}
Return ONLY a valid JSON object matching this schema exactly:
{schema_str}

No explanation, no markdown. Just the JSON object."""

    def _parse(self, raw: str) -> dict:
        # Strip markdown code fences if LLM added them
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())

    def _init_llm(self):
        """Returns a callable: prompt_str → response_str. Picks provider from env."""
        use_local = os.getenv("USE_LOCAL_LLM", "false").lower() == "true"

        if use_local:
            return self._ollama_call

        if os.getenv("ANTHROPIC_API_KEY"):
            import anthropic
            client = anthropic.Anthropic()
            model = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5")

            def claude_call(prompt: str) -> str:
                msg = client.messages.create(
                    model=model,
                    max_tokens=1500,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text
            return claude_call

        if os.getenv("OPENAI_API_KEY"):
            from openai import OpenAI
            client = OpenAI()
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

            def openai_call(prompt: str) -> str:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=1500,
                )
                return resp.choices[0].message.content
            return openai_call

        raise EnvironmentError("No LLM configured. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or USE_LOCAL_LLM=true")

    def _ollama_call(self, prompt: str) -> str:
        import httpx
        base = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434")
        model = os.getenv("LOCAL_LLM_MODEL", "llama3.2")
        resp = httpx.post(
            f"{base}/api/generate",
            json={"model": model, "prompt": f"{SYSTEM_PROMPT}\n\n{prompt}", "stream": False},
            timeout=120,
        )
        return resp.json()["response"]
