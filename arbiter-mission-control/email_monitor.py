"""
Email Monitor — IMAP-based email intelligence for ARBITER.
Uses Gmail App Password (no OAuth needed).
Reads inbox, categorises urgency, tracks replied/unread counts.
"""
import os
import imaplib
import email
import email.utils
import logging
from datetime import datetime, timedelta
from email.header import decode_header
from dataclasses import dataclass, field, asdict

log = logging.getLogger(__name__)


@dataclass
class EmailItem:
    uid: str = ""
    subject: str = ""
    sender: str = ""
    date: str = ""
    snippet: str = ""
    is_read: bool = False
    is_replied: bool = False
    is_urgent: bool = False
    labels: list = field(default_factory=list)


class EmailMonitor:
    def __init__(self):
        self.host = os.getenv("IMAP_HOST", "imap.gmail.com")
        self.port = int(os.getenv("IMAP_PORT", "993"))
        self.user = os.getenv("EMAIL_ADDRESS", "")
        self.password = os.getenv("EMAIL_APP_PASSWORD", "")
        self._cache: list[EmailItem] = []
        self._last_fetch: datetime | None = None
        self._cache_ttl = 120  # seconds

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

    def fetch_emails(self, max_count: int = 50, force: bool = False) -> list[EmailItem]:
        """Fetch recent emails. Cached for _cache_ttl seconds."""
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
                _, data = conn.fetch(uid, "(FLAGS RFC822.HEADER)")
                if not data or not data[0]:
                    continue
                flags_raw = ""
                raw_header = b""
                for part in data:
                    if isinstance(part, tuple):
                        if b"FLAGS" in part[0]:
                            flags_raw = part[0].decode(errors="replace")
                        raw_header = part[1] if len(part) > 1 else raw_header
                    elif isinstance(part, bytes):
                        flags_raw += part.decode(errors="replace")

                msg = email.message_from_bytes(raw_header)
                subject = self._decode_header(msg.get("Subject", ""))
                sender = self._decode_header(msg.get("From", ""))
                date_str = msg.get("Date", "")
                is_read = "\\Seen" in flags_raw
                is_replied = "\\Answered" in flags_raw

                items.append(EmailItem(
                    uid=uid.decode() if isinstance(uid, bytes) else str(uid),
                    subject=subject[:200],
                    sender=sender[:100],
                    date=date_str[:50],
                    is_read=is_read,
                    is_replied=is_replied,
                    is_urgent=self._is_urgent(subject, flags_raw),
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

    def summary(self) -> dict:
        emails = self.fetch_emails()
        total = len(emails)
        unread = sum(1 for e in emails if not e.is_read)
        replied = sum(1 for e in emails if e.is_replied)
        urgent = sum(1 for e in emails if e.is_urgent)
        return {"total": total, "unread": unread, "replied": replied,
                "urgent": urgent, "configured": self.configured}

    def urgent_items(self) -> list[dict]:
        return [asdict(e) for e in self.fetch_emails() if e.is_urgent]

    def recent(self, limit: int = 20) -> list[dict]:
        return [asdict(e) for e in self.fetch_emails()[:limit]]
