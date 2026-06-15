"""
AI Reply Engine — Grow with Freya Engagement Hub
Classifies incoming comments and generates brand-voice replies using GPT-4o.
Every reply is unique — uses the person's name, references what they said,
and always lands on reassurance.
"""
import os
import json
import logging
import yaml
from pathlib import Path

log = logging.getLogger(__name__)

CLASSIFY_PROMPT = """You are classifying a social media comment for Grow with Freya,
a parent-facing children's learning brand.

Classify the comment into ONE of these types:
- question: asking for advice, tips, or information
- concern: expressing worry, guilt, anxiety, or fear
- compliment: positive feedback, sharing a win, gratitude
- share_experience: sharing their own parenting story or moment
- generic: short reactions, emojis, "love this", single words
- negative: criticism, disagreement, or hostility

Also classify sentiment: positive | neutral | concern | negative

Also list any matching trigger keywords from this list:
bedtime_help, screen_time, app_interest, emotional_help, new_parent

Return ONLY valid JSON:
{
  "comment_type": "...",
  "sentiment": "...",
  "triggered_sequences": [],
  "escalate": false,
  "reasoning": "one sentence"
}"""

REPLY_PROMPT = """You are replying to a comment on behalf of Grow with Freya.

Brand voice rules — FOLLOW THESE EXACTLY:
- Warm, calm, genuine — like a knowledgeable friend
- Use their first name if known
- Acknowledge what they said BEFORE offering anything
- Validate their feeling first, educate second
- Keep replies to 1-3 sentences — never longer
- End with an open question or gentle invitation, not a hard sales push
- Max 1-2 emojis, only if natural
- NEVER say: "absolutely", "definitely", "great question", "of course"
- NEVER make medical or developmental claims
- NEVER shame any parenting choice
- The reply must feel human, not automated

Comment type: {comment_type}
Commenter name: {first_name}
Their comment: "{comment_text}"
Post context: {post_context}

Reply framework for this type:
{framework}

Write ONLY the reply text. No labels, no JSON, just the reply."""


class ReplyEngine:
    def __init__(self, config_dir: Path):
        with open(config_dir / "reply_frameworks.yaml") as f:
            self.config = yaml.safe_load(f)
        self._llm = self._init_llm()
        self.escalation_keywords = self.config.get("escalation_keywords", [])
        self.dm_trigger_keywords = self.config.get("dm_trigger_keywords", {})

    def classify(self, comment_text: str) -> dict:
        """Classify a comment. Returns type, sentiment, triggers, escalation flag."""
        # Fast-path: check escalation keywords before calling LLM
        lower = comment_text.lower()
        if any(kw in lower for kw in self.escalation_keywords):
            return {
                "comment_type": "negative",
                "sentiment": "negative",
                "triggered_sequences": [],
                "escalate": True,
                "reasoning": "Escalation keyword detected.",
            }

        raw = self._llm(
            system=CLASSIFY_PROMPT,
            user=f'Comment: "{comment_text}"',
            max_tokens=200,
        )
        try:
            result = json.loads(raw.strip())
        except json.JSONDecodeError:
            result = {"comment_type": "generic", "sentiment": "neutral",
                      "triggered_sequences": [], "escalate": False, "reasoning": "parse error"}

        # Also check DM trigger keywords locally
        for seq_name, keywords in self.dm_trigger_keywords.items():
            if any(kw.lower() in lower for kw in keywords):
                if seq_name not in result.get("triggered_sequences", []):
                    result.setdefault("triggered_sequences", []).append(seq_name)

        return result

    def generate_reply(self, comment_text: str, comment_type: str,
                       first_name: str = "", post_context: str = "") -> str | None:
        """Generate a brand-voice reply. Returns None for types that need human review."""
        framework_cfg = self.config["comment_types"].get(comment_type, {})

        # Never auto-reply to negative or generic comments
        if not framework_cfg.get("auto_reply", False):
            log.info(f"Comment type '{comment_type}' queued for human review.")
            return None

        framework_steps = "\n".join(
            f"  {i+1}. {step}"
            for i, step in enumerate(framework_cfg.get("response_structure", []))
        )
        example = framework_cfg.get("example_reply", "")

        user_prompt = REPLY_PROMPT.format(
            comment_type=comment_type,
            first_name=first_name or "there",
            comment_text=comment_text,
            post_context=post_context or "a parenting content post",
            framework=f"{framework_steps}\n\nExample tone (do NOT copy — just the feel):\n{example}",
        )

        reply = self._llm(system="You are a warm social media community manager.", user=user_prompt, max_tokens=150)
        return reply.strip()

    def process_comment(self, event: dict, contact: dict, post_context: str = "") -> dict:
        """Full pipeline: classify → generate reply → return result dict."""
        text = event.get("text", "")
        first_name = contact.get("first_name", "")

        classification = self.classify(text)
        comment_type = classification["comment_type"]

        reply = None
        if not classification.get("escalate"):
            reply = self.generate_reply(text, comment_type, first_name, post_context)

        return {
            "classification": classification,
            "reply": reply,
            "needs_review": reply is None,
            "triggered_sequences": classification.get("triggered_sequences", []),
        }

    # ── LLM initialisation ────────────────────────────────────────────
    def _init_llm(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY required for ReplyEngine.")
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o")

        def call(system: str, user: str, max_tokens: int = 300) -> str:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                max_tokens=max_tokens,
                temperature=0.7,
            )
            return resp.choices[0].message.content

        return call
