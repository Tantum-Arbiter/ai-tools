"""
Grow with Freya — Content Automation Orchestrator
Run via Windows Task Scheduler every 30 minutes.
Checks posting schedule, generates content if needed, publishes at optimal times.
"""
import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from scripts.brief_generator import BriefGenerator
from scripts.fact_finder import FactFinder
from scripts.generator.comfyui_client import ComfyUIClient
from scripts.generator.video_assembler import VideoAssembler
from scripts.publisher.instagram_publisher import InstagramPublisher
from scripts.publisher.youtube_publisher import YouTubePublisher
from scripts.scheduler import PostingScheduler
from scripts.state_db import StateDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(ROOT / "logs" / "orchestrator.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def run():
    log.info("=" * 60)
    log.info("Orchestrator starting")

    db_path = os.getenv("DB_PATH", "data/state.db")
    db = StateDB(db_path)
    scheduler = PostingScheduler(ROOT / "config" / "posting_schedule.yaml")

    # FactFinder is passed into BriefGenerator so the trigger drives the fact search.
    # Each post picks its own trigger → fetches a matching fact → builds a unified brief.
    fact_finder = FactFinder(db_path)
    brief_gen = BriefGenerator(ROOT / "config", fact_finder=fact_finder)

    comfy = ComfyUIClient(os.getenv("COMFYUI_BASE_URL", "http://localhost:8188"))
    assembler = VideoAssembler()
    ig = InstagramPublisher()
    yt = YouTubePublisher()

    now = datetime.now()

    # ── Step 1: Check what needs to be posted right now ──────────────
    due_posts = db.get_due_posts(now)
    for post in due_posts:
        _publish_post(post, ig, yt, db, log)

    # ── Step 2: Check queue depth — generate new content if low ──────
    queue_depth = db.get_queue_depth()
    min_queue = int(os.getenv("MIN_QUEUE_SIZE", "2"))

    if queue_depth < min_queue:
        log.info(f"Queue depth {queue_depth} < {min_queue}. Generating new content...")
        slots = scheduler.get_upcoming_slots(now, hours_ahead=24)

        for slot in slots:
            if db.slot_has_content(slot):
                continue

            # Pick content type for this slot
            content_type = scheduler.content_type_for_slot(slot)  # "reel" | "image" | "short"
            platform = slot["platform"]

            log.info(f"Generating {content_type} for {platform} @ {slot['time']}")

            try:
                # Trigger → fact → brief — all coordinated inside BriefGenerator
                brief = brief_gen.generate(content_type=content_type, platform=platform)
                log.info(f"Brief: {brief['theme']} — Hook: {brief['hook'][:60]}...")

                # Generate visual asset
                if content_type in ("reel", "short"):
                    asset_path = _generate_video(comfy, assembler, brief, log)
                else:
                    asset_path = _generate_image(comfy, brief, log)

                if asset_path:
                    db.queue_post(slot=slot, brief=brief, asset_path=str(asset_path))
                    log.info(f"Queued: {asset_path.name}")

            except Exception as e:
                log.error(f"Content generation failed for slot {slot}: {e}", exc_info=True)

    log.info("Orchestrator complete")


def _generate_video(comfy: ComfyUIClient, assembler: VideoAssembler, brief: dict, log) -> Path | None:
    """Generate a short-form video: ComfyUI image → Ken Burns → TTS voiceover → FFmpeg."""
    try:
        # 1. Generate base image via ComfyUI
        image_path = comfy.generate_image(
            prompt=brief["image_prompt"],
            negative_prompt=brief.get("negative_prompt", ""),
            width=1080, height=1920,  # 9:16 vertical
        )
        # 2. Assemble video: Ken Burns effect + voiceover + captions
        video_path = assembler.create_short(
            image_path=image_path,
            script=brief["video_script"],
            caption_text=brief["caption"],
            duration=28,  # Reels sweet spot: 25-30s
        )
        return video_path
    except Exception as e:
        log.error(f"Video generation error: {e}", exc_info=True)
        return None


def _generate_image(comfy: ComfyUIClient, brief: dict, log) -> Path | None:
    """Generate a static image post via ComfyUI."""
    try:
        return comfy.generate_image(
            prompt=brief["image_prompt"],
            negative_prompt=brief.get("negative_prompt", ""),
            width=1080, height=1080,  # Square for feed
        )
    except Exception as e:
        log.error(f"Image generation error: {e}", exc_info=True)
        return None


def _publish_post(post: dict, ig: InstagramPublisher, yt: YouTubePublisher, db: StateDB, log):
    """Publish a queued post to the correct platform."""
    try:
        platform = post["platform"]
        content_type = post["content_type"]
        log.info(f"Publishing {content_type} to {platform}: {post['theme']}")

        if platform == "instagram":
            result = ig.publish(post)
        elif platform == "youtube":
            result = yt.publish(post)
        else:
            log.warning(f"Unknown platform: {platform}")
            return

        db.mark_published(post["id"], result)
        log.info(f"Published successfully: {result.get('url', 'no URL')}")

    except Exception as e:
        log.error(f"Publish failed for post {post['id']}: {e}", exc_info=True)
        db.mark_failed(post["id"], str(e))


if __name__ == "__main__":
    run()
