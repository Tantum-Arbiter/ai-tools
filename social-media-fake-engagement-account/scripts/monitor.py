"""
Comment Monitor — Grow with Freya Engagement Hub
Polls Instagram Graph API and Facebook Graph API for new comments.
Used as fallback when webhooks are not configured, or to catch missed events.
Runs on cron (every 15 minutes recommended).
"""
import os
import logging
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger(__name__)

IG_API = "https://graph.instagram.com/v21.0"
FB_API = "https://graph.facebook.com/v21.0"


class CommentMonitor:
    def __init__(self):
        self.ig_token = os.getenv("META_ACCESS_TOKEN")
        self.ig_account_id = os.getenv("META_INSTAGRAM_ACCOUNT_ID")
        self.fb_page_id = os.getenv("FB_PAGE_ID")
        self.fb_page_token = os.getenv("FB_PAGE_ACCESS_TOKEN")
        self._seen_comment_ids: set[str] = set()  # In-memory dedup (persisted via DB in prod)

    # ── Instagram ────────────────────────────────────────────────────
    def poll_instagram(self, since_minutes: int = 20) -> list[dict]:
        """Fetch recent comments on all Instagram media since N minutes ago."""
        if not self.ig_token or not self.ig_account_id:
            log.warning("Instagram credentials not configured — skipping IG poll.")
            return []

        comments = []
        media_ids = self._get_ig_recent_media()
        since_ts = int((datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).timestamp())

        for media_id in media_ids:
            raw = self._get_ig_comments(media_id, since_ts)
            for c in raw:
                if c["id"] not in self._seen_comment_ids:
                    self._seen_comment_ids.add(c["id"])
                    comments.append({
                        "platform": "instagram",
                        "comment_id": c["id"],
                        "media_id": media_id,
                        "text": c.get("text", ""),
                        "timestamp": c.get("timestamp"),
                        "user": {
                            "platform_id": c.get("from", {}).get("id", ""),
                            "username": c.get("from", {}).get("username", ""),
                        },
                    })

        log.info(f"Instagram: {len(comments)} new comments found.")
        return comments

    def _get_ig_recent_media(self, limit: int = 10) -> list[str]:
        """Get IDs of the most recent Instagram media posts."""
        r = httpx.get(
            f"{IG_API}/{self.ig_account_id}/media",
            params={"fields": "id", "limit": limit, "access_token": self.ig_token},
            timeout=15,
        )
        r.raise_for_status()
        return [item["id"] for item in r.json().get("data", [])]

    def _get_ig_comments(self, media_id: str, since_ts: int) -> list[dict]:
        """Fetch comments on a specific media item."""
        try:
            r = httpx.get(
                f"{IG_API}/{media_id}/comments",
                params={
                    "fields": "id,text,timestamp,from",
                    "since": since_ts,
                    "access_token": self.ig_token,
                },
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get("data", [])
        except Exception as e:
            log.warning(f"Failed to fetch comments for media {media_id}: {e}")
            return []

    # ── Facebook ─────────────────────────────────────────────────────
    def poll_facebook(self, since_minutes: int = 20) -> list[dict]:
        """Fetch recent comments on Facebook Page posts."""
        if not self.fb_page_token or not self.fb_page_id:
            log.warning("Facebook credentials not configured — skipping FB poll.")
            return []

        comments = []
        post_ids = self._get_fb_recent_posts()
        since_ts = int((datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).timestamp())

        for post_id in post_ids:
            raw = self._get_fb_comments(post_id, since_ts)
            for c in raw:
                if c["id"] not in self._seen_comment_ids:
                    self._seen_comment_ids.add(c["id"])
                    comments.append({
                        "platform": "facebook",
                        "comment_id": c["id"],
                        "media_id": post_id,
                        "text": c.get("message", ""),
                        "timestamp": c.get("created_time"),
                        "user": {
                            "platform_id": c.get("from", {}).get("id", ""),
                            "username": c.get("from", {}).get("name", ""),
                        },
                    })

        log.info(f"Facebook: {len(comments)} new comments found.")
        return comments

    def _get_fb_recent_posts(self, limit: int = 10) -> list[str]:
        r = httpx.get(
            f"{FB_API}/{self.fb_page_id}/posts",
            params={"fields": "id", "limit": limit, "access_token": self.fb_page_token},
            timeout=15,
        )
        r.raise_for_status()
        return [item["id"] for item in r.json().get("data", [])]

    def _get_fb_comments(self, post_id: str, since_ts: int) -> list[dict]:
        try:
            r = httpx.get(
                f"{FB_API}/{post_id}/comments",
                params={
                    "fields": "id,message,created_time,from",
                    "since": since_ts,
                    "access_token": self.fb_page_token,
                },
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get("data", [])
        except Exception as e:
            log.warning(f"Failed to fetch FB comments for post {post_id}: {e}")
            return []

    # ── DMs (Instagram) ──────────────────────────────────────────────
    def poll_instagram_dms(self) -> list[dict]:
        """Fetch recent Instagram DMs (requires instagram_manage_messages permission)."""
        if not self.ig_token or not self.ig_account_id:
            return []
        try:
            r = httpx.get(
                f"{IG_API}/{self.ig_account_id}/conversations",
                params={"fields": "messages{message,from,created_time}", "access_token": self.ig_token},
                timeout=15,
            )
            r.raise_for_status()
            dms = []
            for conv in r.json().get("data", []):
                for msg in conv.get("messages", {}).get("data", []):
                    if msg.get("from", {}).get("id") != self.ig_account_id:
                        dms.append({
                            "platform": "instagram",
                            "type": "dm_received",
                            "text": msg.get("message", ""),
                            "timestamp": msg.get("created_time"),
                            "user": {"platform_id": msg["from"]["id"],
                                     "username": msg["from"].get("username", "")},
                        })
            return dms
        except Exception as e:
            log.warning(f"DM poll failed: {e}")
            return []

    def poll_all(self, since_minutes: int = 20) -> list[dict]:
        """Poll all platforms. Returns unified list of comment/DM events."""
        events = []
        events.extend(self.poll_instagram(since_minutes))
        events.extend(self.poll_facebook(since_minutes))
        events.extend(self.poll_instagram_dms())
        return events
