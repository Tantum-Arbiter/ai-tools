"""
YouTube Publisher
Uploads Shorts and regular videos via YouTube Data API v3.
Auth: OAuth 2.0 with offline refresh token (run scripts/auth/youtube_auth.py once).
Docs: https://developers.google.com/youtube/v3/guides/uploading_a_video
"""
import os
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# YouTube category IDs relevant to parenting content
CATEGORY_EDUCATION = "27"
CATEGORY_PEOPLE_BLOGS = "22"
CATEGORY_HOWTO = "26"

PRIVACY_PUBLIC = "public"
PRIVACY_PRIVATE = "private"   # Use for testing
PRIVACY_UNLISTED = "unlisted"


class YouTubePublisher:
    def __init__(self):
        self.client_id = os.getenv("YOUTUBE_CLIENT_ID")
        self.client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
        self.refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
        if not all([self.client_id, self.client_secret, self.refresh_token]):
            raise EnvironmentError(
                "YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN required. "
                "Run scripts/auth/youtube_auth.py to generate."
            )
        self._credentials = None

    def publish(self, post: dict) -> dict:
        """Upload a video to YouTube."""
        asset_path = Path(post["asset_path"])
        if not asset_path.exists():
            raise FileNotFoundError(f"Asset not found: {asset_path}")

        content_type = post.get("content_type", "short")
        is_short = content_type in ("short", "reel")

        title = self._build_title(post, is_short)
        description = self._build_description(post)
        tags = self._build_tags(post)

        log.info(f"Uploading to YouTube: {title}")
        video_id = self._upload(
            file_path=asset_path,
            title=title,
            description=description,
            tags=tags,
            category_id=CATEGORY_EDUCATION,
            privacy=PRIVACY_PUBLIC,
            made_for_kids=False,
        )

        url = f"https://youtube.com/shorts/{video_id}" if is_short else f"https://youtu.be/{video_id}"
        log.info(f"YouTube upload complete: {url}")
        return {"video_id": video_id, "url": url, "platform": "youtube", "type": content_type}

    def _upload(
        self,
        file_path: Path,
        title: str,
        description: str,
        tags: list[str],
        category_id: str,
        privacy: str,
        made_for_kids: bool,
    ) -> str:
        """Resumable upload via googleapiclient."""
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google.oauth2.credentials import Credentials

        creds = self._get_credentials()
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": category_id,
                "defaultLanguage": "en-GB",
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": made_for_kids,
            },
        }

        media = MediaFileUpload(
            str(file_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024 * 5,  # 5MB chunks
        )

        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                log.debug(f"Upload progress: {int(status.progress() * 100)}%")

        return response["id"]

    def _get_credentials(self):
        """Exchange refresh token for access token."""
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        if self._credentials and self._credentials.valid:
            return self._credentials

        creds = Credentials(
            token=None,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
        )
        creds.refresh(Request())
        self._credentials = creds
        return creds

    # ── Caption builders ──────────────────────────────────────────────
    def _build_title(self, post: dict, is_short: bool) -> str:
        hook = post.get("hook", post.get("theme", "Parenting Tip"))
        brand = os.getenv("BRAND_NAME", "Grow with Freya")
        prefix = "#Shorts | " if is_short else ""
        return f"{prefix}{hook} | {brand}"[:100]  # YouTube title max 100 chars

    def _build_description(self, post: dict) -> str:
        caption = post.get("caption", "")
        hashtags = " ".join(post.get("hashtags", []))
        brand = os.getenv("BRAND_NAME", "Grow with Freya")
        cta = post.get("cta", "Follow for daily parenting support.")
        return (
            f"{caption}\n\n"
            f"{cta}\n\n"
            f"📱 Follow us on Instagram: @growwithfreya\n\n"
            f"{hashtags}\n\n"
            f"© {brand}"
        )[:5000]

    def _build_tags(self, post: dict) -> list[str]:
        hashtags = post.get("hashtags", [])
        clean = [h.lstrip("#") for h in hashtags]
        base = ["parenting", "toddlers", "earlyyears", "growwithfreya", "parentingtips"]
        return list(dict.fromkeys(clean + base))[:500]  # YouTube: max 500 chars total
