"""
Email Monitor — IMAP/SMTP email intelligence for ARBITER.
Uses Gmail App Password (no OAuth needed).
Reads inbox (full bodies), classifies emails, drafts replies, sends via SMTP.
"""
import os
import re
import imaplib
import smtplib
import email
import email.utils
import logging
from datetime import datetime, timedelta
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass, field, asdict
from html.parser import HTMLParser

log = logging.getLogger(__name__)


class _HTMLStripper(HTMLParser):
    """Minimal HTML-to-text converter."""
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
    def handle_data(self, d):
        self._parts.append(d)
    def get_text(self):
        return " ".join(self._parts)


def _strip_html(html: str) -> str:
    s = _HTMLStripper()
    s.feed(html)
    return s.get_text()


# ── Confidential Data Redaction ──────────────────────────────────────
# Applied to ALL email bodies before caching, display, or LLM routing.
# Patterns are intentionally broad — false positives are preferable to leaks.

_REDACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Credit/debit card numbers (13-19 digits, with optional separators)
    (re.compile(r'\b(?:\d[ -]?){13,19}\b'), '[CARD_REDACTED]'),
    # Card numbers with common prefixes (Visa, MC, Amex, Discover)
    (re.compile(r'\b(?:4\d{3}|5[1-5]\d{2}|3[47]\d{2}|6(?:011|5\d{2}))[ -]?\d{4}[ -]?\d{4}[ -]?\d{2,4}\b'), '[CARD_REDACTED]'),
    # CVV / CVC / Security codes (standalone 3-4 digit codes near card keywords)
    (re.compile(r'(?:cvv|cvc|cvv2|csc|security code)[:\s]*\d{3,4}', re.IGNORECASE), '[CVV_REDACTED]'),
    # Expiry dates in card context (MM/YY or MM/YYYY)
    (re.compile(r'(?:exp(?:iry|iration)?|valid (?:thru|until))[:\s]*\d{1,2}[/\-]\d{2,4}', re.IGNORECASE), '[EXPIRY_REDACTED]'),
    # Bank account numbers (UK sort code + account)
    (re.compile(r'\b\d{2}[ -]?\d{2}[ -]?\d{2}\s+\d{6,8}\b'), '[BANK_ACCT_REDACTED]'),
    # Sort codes (XX-XX-XX pattern)
    (re.compile(r'(?:sort\s*code)[:\s]*\d{2}[ -]?\d{2}[ -]?\d{2}', re.IGNORECASE), '[SORTCODE_REDACTED]'),
    # IBAN numbers
    (re.compile(r'\b[A-Z]{2}\d{2}[ ]?[A-Z0-9]{4}[ ]?(?:\d{4}[ ]?){2,7}\d{1,4}\b'), '[IBAN_REDACTED]'),
    # SWIFT/BIC codes
    (re.compile(r'(?:swift|bic)[:\s]*[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?', re.IGNORECASE), '[SWIFT_REDACTED]'),
    # UK National Insurance numbers
    (re.compile(r'\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b', re.IGNORECASE), '[NI_NUMBER_REDACTED]'),
    # US Social Security Numbers
    (re.compile(r'\b\d{3}[ -]?\d{2}[ -]?\d{4}\b'), '[SSN_REDACTED]'),
    # API keys / tokens (long hex or base64 strings, 20+ chars)
    (re.compile(r'(?:api[_ ]?key|token|secret|bearer|authorization)[:\s="\']*[A-Za-z0-9_\-\.]{20,}', re.IGNORECASE), '[API_KEY_REDACTED]'),
    # Generic key=value secrets
    (re.compile(r'(?:password|passwd|pwd|secret|private[_ ]?key|access[_ ]?key|client[_ ]?secret)[:\s="\']+\S{4,}', re.IGNORECASE), '[CREDENTIAL_REDACTED]'),
    # PEM private keys
    (re.compile(r'-----BEGIN (?:RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----'), '[PRIVATE_KEY_REDACTED]'),
    # AWS access key IDs
    (re.compile(r'\bAKIA[0-9A-Z]{16}\b'), '[AWS_KEY_REDACTED]'),
    # Generic long secrets (40+ hex chars — likely hashes, tokens, keys)
    (re.compile(r'\b[0-9a-fA-F]{40,}\b'), '[LONG_HEX_REDACTED]'),
    # PayPal / Stripe / payment references with amounts
    (re.compile(r'(?:paypal|stripe|payment)[:\s]*(?:id|ref|reference|transaction)[:\s]*\S+', re.IGNORECASE), '[PAYMENT_REF_REDACTED]'),
]

# Additional aggressive patterns for LLM-bound content (never shown to models)
_REDACT_LLM_EXTRA: list[tuple[re.Pattern, str]] = [
    # Any standalone monetary amounts with currency (£123.45, $1,234.56, €50)
    (re.compile(r'[£$€]\s?\d[\d,]*\.?\d{0,2}'), '[AMOUNT_REDACTED]'),
    # Account numbers (keyword + digits)
    (re.compile(r'(?:account|acct|a/c)[\s#:]*\d{4,}', re.IGNORECASE), '[ACCT_NUM_REDACTED]'),
    # Reference numbers (keyword + alphanumeric)
    (re.compile(r'(?:ref(?:erence)?|order|invoice|transaction|confirmation)[\s#:]*[A-Z0-9\-]{6,}', re.IGNORECASE), '[REF_REDACTED]'),
    # Phone numbers (UK and international formats)
    (re.compile(r'(?:\+?\d{1,3}[ -]?)?\(?\d{2,5}\)?[ -]?\d{3,4}[ -]?\d{3,4}'), '[PHONE_REDACTED]'),
    # Embedded URLs with auth tokens
    (re.compile(r'https?://\S*(?:token|key|auth|secret|password|session)=\S+', re.IGNORECASE), '[AUTH_URL_REDACTED]'),
]


def redact_sensitive(text: str) -> str:
    """Remove confidential patterns from text. Applied to all cached email bodies."""
    if not text:
        return text
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_for_llm(text: str) -> str:
    """Aggressively redact text before sending to any LLM model.
    Applies base redaction + extra financial/PII patterns."""
    text = redact_sensitive(text)
    for pattern, replacement in _REDACT_LLM_EXTRA:
        text = pattern.sub(replacement, text)
    return text


# ── Classification categories ──
EMAIL_CATEGORIES = {
    "customer_inquiry": "Customer or prospect reaching out about services/products",
    "business":         "Business communication — partners, suppliers, operations",
    "personal":         "Personal email from known contacts",
    "newsletter":       "Newsletter, marketing, promotional",
    "notification":     "Automated notification — receipts, alerts, confirmations",
    "spam":             "Spam or unsolicited commercial email",
}

# Fast heuristic patterns to skip classification LLM call
_SKIP_SENDERS = re.compile(
    r"no-?reply|noreply|mailer-daemon|notifications?@|news(letter)?@|promo|marketing|"
    r"updates?@|digest@|alerts?@|notify@|do-not-reply",
    re.IGNORECASE,
)
_SKIP_SUBJECTS = re.compile(
    r"unsubscribe|newsletter|weekly digest|daily summary|promotional|"
    r"your (receipt|order|invoice|statement)|verify your|confirm your (email|account)",
    re.IGNORECASE,
)


@dataclass
class EmailItem:
    uid: str = ""
    subject: str = ""
    sender: str = ""
    date: str = ""
    snippet: str = ""
    body: str = ""
    category: str = ""          # customer_inquiry | business | personal | newsletter | notification | spam
    is_read: bool = False
    is_replied: bool = False
    is_urgent: bool = False
    message_id: str = ""        # for threading / In-Reply-To
    to: str = ""
    labels: list = field(default_factory=list)


class EmailMonitor:
    def __init__(self):
        self.host = os.getenv("IMAP_HOST", "imap.gmail.com")
        self.port = int(os.getenv("IMAP_PORT", "993"))
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.user = os.getenv("EMAIL_ADDRESS", "")
        self.password = os.getenv("EMAIL_APP_PASSWORD", "")
        self._cache: list[EmailItem] = []
        self._last_fetch: datetime | None = None
        self._cache_ttl = 120  # seconds
        self._body_cache: dict[str, str] = {}  # uid → full body text
        self._classification_cache: dict[str, str] = {}  # uid → category

    @property
    def configured(self) -> bool:
        return bool(self.user and self.password)

    def _connect(self) -> imaplib.IMAP4_SSL | None:
        if not self.configured:
            return None
        try:
            conn = imaplib.IMAP4_SSL(self.host, self.port)
            conn.login(self.user, self.password)
            return conn
        except Exception as e:
            log.error(f"IMAP connection failed: {e}")
            return None

    def _decode_header(self, raw: str) -> str:
        parts = decode_header(raw or "")
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(str(part))
        return " ".join(decoded)

    def _is_urgent(self, subject: str, flags: str) -> bool:
        urgent_keywords = ["urgent", "asap", "critical", "important", "action required",
                           "deadline", "immediately", "time sensitive"]
        subj_lower = subject.lower()
        return any(k in subj_lower for k in urgent_keywords) or "\\Flagged" in flags

    def _extract_body(self, msg: email.message.Message, max_chars: int = 8000) -> str:
        """Extract plain-text body from an email message. Falls back to HTML stripping."""
        text_parts = []
        html_parts = []
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                disp = str(part.get("Content-Disposition", ""))
                if "attachment" in disp:
                    continue
                try:
                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue
                    charset = part.get_content_charset() or "utf-8"
                    text = payload.decode(charset, errors="replace")
                    if ct == "text/plain":
                        text_parts.append(text)
                    elif ct == "text/html":
                        html_parts.append(text)
                except Exception:
                    continue
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    text = payload.decode(charset, errors="replace")
                    if msg.get_content_type() == "text/html":
                        html_parts.append(text)
                    else:
                        text_parts.append(text)
            except Exception:
                pass

        body = "\n".join(text_parts) if text_parts else _strip_html("\n".join(html_parts))
        # ── Redact confidential data before caching ──
        body = redact_sensitive(body)
        return body[:max_chars].strip()

    def _quick_classify(self, sender: str, subject: str) -> str | None:
        """Fast heuristic classification — returns category or None if LLM needed."""
        if _SKIP_SENDERS.search(sender):
            return "notification"
        if _SKIP_SUBJECTS.search(subject):
            return "newsletter"
        return None

    def fetch_emails(self, max_count: int = 50, force: bool = False) -> list[EmailItem]:
        """Fetch recent emails with full bodies. Cached for _cache_ttl seconds."""
        if not force and self._last_fetch and \
           (datetime.utcnow() - self._last_fetch).total_seconds() < self._cache_ttl:
            return self._cache

        conn = self._connect()
        if not conn:
            return []

        items = []
        try:
            conn.select("INBOX", readonly=True)
            since = (datetime.utcnow() - timedelta(days=7)).strftime("%d-%b-%Y")
            _, msg_ids = conn.search(None, f'(SINCE {since})')
            ids = msg_ids[0].split()[-max_count:] if msg_ids[0] else []

            for uid in ids:
                _, data = conn.fetch(uid, "(FLAGS RFC822)")
                if not data or not data[0]:
                    continue
                flags_raw = ""
                raw_msg = b""
                for part in data:
                    if isinstance(part, tuple):
                        if b"FLAGS" in part[0]:
                            flags_raw = part[0].decode(errors="replace")
                        raw_msg = part[1] if len(part) > 1 else raw_msg
                    elif isinstance(part, bytes):
                        flags_raw += part.decode(errors="replace")

                msg = email.message_from_bytes(raw_msg)
                subject = self._decode_header(msg.get("Subject", ""))
                sender = self._decode_header(msg.get("From", ""))
                date_str = msg.get("Date", "")
                is_read = "\\Seen" in flags_raw
                is_replied = "\\Answered" in flags_raw
                message_id = msg.get("Message-ID", "")
                to_addr = self._decode_header(msg.get("To", ""))

                body = self._extract_body(msg)
                uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)

                # Cache body for detail retrieval
                self._body_cache[uid_str] = body

                # Quick classification (heuristic)
                cat = self._quick_classify(sender, subject)
                if cat:
                    self._classification_cache[uid_str] = cat

                items.append(EmailItem(
                    uid=uid_str,
                    subject=subject[:200],
                    sender=sender[:100],
                    date=date_str[:50],
                    snippet=body[:200],
                    body="",  # Don't include full body in list — fetch on demand
                    category=self._classification_cache.get(uid_str, ""),
                    is_read=is_read,
                    is_replied=is_replied,
                    is_urgent=self._is_urgent(subject, flags_raw),
                    message_id=message_id[:200],
                    to=to_addr[:100],
                ))
            conn.logout()
        except Exception as e:
            log.error(f"Email fetch error: {e}")
            try:
                conn.logout()
            except Exception:
                pass

        self._cache = list(reversed(items))  # newest first
        self._last_fetch = datetime.utcnow()
        return self._cache

    def get_email_detail(self, uid: str) -> dict | None:
        """Get full email detail including body for a specific UID."""
        emails = self.fetch_emails()
        for e in emails:
            if e.uid == uid:
                d = asdict(e)
                d["body"] = self._body_cache.get(uid, e.snippet)
                return d
        return None

    def get_emails_needing_classification(self) -> list[dict]:
        """Return emails that haven't been classified yet (no heuristic match)."""
        return [
            asdict(e) for e in self.fetch_emails()
            if not e.category and not e.is_replied
        ]

    def set_classification(self, uid: str, category: str):
        """Store classification result for an email."""
        if category not in EMAIL_CATEGORIES:
            log.warning(f"Invalid category '{category}' for uid {uid}")
            return
        self._classification_cache[uid] = category
        # Update cached item
        for e in self._cache:
            if e.uid == uid:
                e.category = category
                break

    def customer_emails(self, limit: int = 20) -> list[dict]:
        """Return emails classified as customer inquiries or business."""
        return [
            asdict(e) for e in self.fetch_emails()
            if e.category in ("customer_inquiry", "business")
        ][:limit]

    def send_email(self, to: str, subject: str, body: str,
                   in_reply_to: str = "", html: bool = False) -> dict:
        """Send an email via SMTP. Returns {"ok": True} or {"error": "..."}."""
        if not self.configured:
            return {"error": "Email not configured (EMAIL_ADDRESS / EMAIL_APP_PASSWORD missing)"}

        # Basic input validation
        if not to or not subject or not body:
            return {"error": "Missing required fields: to, subject, body"}
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', to):
            return {"error": f"Invalid recipient address: {to}"}

        try:
            msg = MIMEMultipart("alternative") if html else MIMEText(body, "plain")
            if html:
                msg.attach(MIMEText(body, "plain"))
                msg.attach(MIMEText(body, "html"))
            msg["From"] = self.user
            msg["To"] = to
            msg["Subject"] = subject
            if in_reply_to:
                msg["In-Reply-To"] = in_reply_to
                msg["References"] = in_reply_to

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.sendmail(self.user, [to], msg.as_string())

            log.info(f"Email sent to {to}: {subject[:60]}")
            return {"ok": True, "to": to, "subject": subject}
        except Exception as e:
            log.error(f"SMTP send failed: {e}")
            return {"error": str(e)}

    def summary(self) -> dict:
        emails = self.fetch_emails()
        total = len(emails)
        unread = sum(1 for e in emails if not e.is_read)
        replied = sum(1 for e in emails if e.is_replied)
        urgent = sum(1 for e in emails if e.is_urgent)
        customer = sum(1 for e in emails if e.category in ("customer_inquiry", "business"))
        return {"total": total, "unread": unread, "replied": replied,
                "urgent": urgent, "customer": customer, "configured": self.configured}

    def urgent_items(self) -> list[dict]:
        return [asdict(e) for e in self.fetch_emails() if e.is_urgent]

    def recent(self, limit: int = 20) -> list[dict]:
        return [asdict(e) for e in self.fetch_emails()[:limit]]
