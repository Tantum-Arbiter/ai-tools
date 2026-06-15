"""
Instagram Publisher
Uses Instagram Graph API to post Reels (video) and Images.
Docs: https://developers.facebook.com/docs/instagram-api/guides/content-publishing
Requires: Instagram Professional/Business account linked to a Facebook Page.
"""
import os
import time
import logging
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

IG_API = "https://graph.instagram.com/v21.0"


class InstagramPublisher:
    def __init__(self):
        self.token = os.getenv("META_ACCESS_TOKEN")
        self.account_id = os.getenv("META_INSTAGRAM_ACCOUNT_ID")
        if not self.token or not self.account_id:
            raise EnvironmentError("META_ACCESS_TOKEN and META_INSTAGRAM_ACCOUNT_ID required.")

    def publish(self, post: dict) -> dict:
        """Route to correct publisher based on content type."""
        content_type = post.get("content_type", "image")
        asset_path = Path(post["asset_path"])

        if not asset_path.exists():
            raise FileNotFoundError(f"Asset not found: {asset_path}")

        # Instagram requires a public URL — use a temporary upload service or your own CDN.
        # For local setup: use ngrok or upload to S3/Cloudflare R2 (free tier).
        media_url = self._upload_to_accessible_url(asset_path)

        if content_type in ("reel", "short"):
            return self._publish_reel(post, media_url)
        else:
            return self._publish_image(post, media_url)

    # ── Reel (Video) ─────────────────────────────────────────────────
    def _publish_reel(self, post: dict, video_url: str) -> dict:
        log.info("Creating Instagram Reel media container...")

        # Step 1: Create container
        container_id = self._create_video_container(post, video_url)

        # Step 2: Wait for processing
        self._wait_for_processing(container_id)

        # Step 3: Publish
        media_id = self._publish_container(container_id)
        permalink = self._get_permalink(media_id)

        log.info(f"Reel published: {permalink}")
        return {"media_id": media_id, "url": permalink, "platform": "instagram", "type": "reel"}

    def _create_video_container(self, post: dict, video_url: str) -> str:
        caption = self._build_caption(post)
        params = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": self.token,
        }
        r = httpx.post(f"{IG_API}/{self.account_id}/media", params=params, timeout=30)
        r.raise_for_status()
        return r.json()["id"]

    # ── Image ─────────────────────────────────────────────────────────
    def _publish_image(self, post: dict, image_url: str) -> dict:
        log.info("Creating Instagram image media container...")
        caption = self._build_caption(post)
        params = {
            "image_url": image_url,
            "caption": caption,
            "access_token": self.token,
        }
        r = httpx.post(f"{IG_API}/{self.account_id}/media", params=params, timeout=30)
        r.raise_for_status()
        container_id = r.json()["id"]

        self._wait_for_processing(container_id)
        media_id = self._publish_container(container_id)
        permalink = self._get_permalink(media_id)

        log.info(f"Image published: {permalink}")
        return {"media_id": media_id, "url": permalink, "platform": "instagram", "type": "image"}

    # ── Helpers ───────────────────────────────────────────────────────
    def _wait_for_processing(self, container_id: str, timeout: int = 300):
        """Poll until media container status is FINISHED."""
        start = time.time()
        while time.time() - start < timeout:
            r = httpx.get(
                f"{IG_API}/{container_id}",
                params={"fields": "status_code,status", "access_token": self.token},
                timeout=15,
            )
            data = r.json()
            status = data.get("status_code", "")
            log.debug(f"Container {container_id} status: {status}")
            if status == "FINISHED":
                return
            if status == "ERROR":
                raise RuntimeError(f"Instagram container processing failed: {data}")
            time.sleep(10)
        raise TimeoutError(f"Container {container_id} did not finish within {timeout}s")

    def _publish_container(self, container_id: str) -> str:
        r = httpx.post(
            f"{IG_API}/{self.account_id}/media_publish",
            params={"creation_id": container_id, "access_token": self.token},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["id"]

    def _get_permalink(self, media_id: str) -> str:
        r = httpx.get(
            f"{IG_API}/{media_id}",
            params={"fields": "permalink", "access_token": self.token},
            timeout=15,
        )
        return r.json().get("permalink", "")

    def _build_caption(self, post: dict) -> str:
        """Assemble caption + hashtags from brief."""
        caption = post.get("caption", "")
        hashtags = " ".join(post.get("hashtags", []))
        return f"{caption}\n\n{hashtags}"

    def _upload_to_accessible_url(self, asset_path: Path) -> str:
        """
        Instagram requires a publicly accessible URL for media.
        Options:
          1. Cloudflare R2 (free tier: 10GB storage, 1M requests/month)  ← RECOMMENDED
          2. AWS S3 (free tier: 5GB)
          3. ngrok local tunnel (free, for testing)
        
        Implement one of these based on your preference.
        For now, raises NotImplementedError with setup instructions.
        """
        # If MEDIA_CDN_BASE_URL is set, assume files are served from there
        cdn_base = os.getenv("MEDIA_CDN_BASE_URL")
        if cdn_base:
            return f"{cdn_base.rstrip('/')}/{asset_path.name}"

        raise NotImplementedError(
            "Instagram requires a public URL. "
            "Set MEDIA_CDN_BASE_URL in .env after setting up Cloudflare R2 or S3. "
            "See docs/cdn_setup.md for instructions."
        )
