"""
Posting Scheduler
Reads posting_schedule.yaml and resolves upcoming slots with platform + datetime.
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

CONTENT_TYPE_MAP = {
    # Maps slot type → content_type string
    "reels": "reel",
    "images": "image",
    "shorts": "short",
    "videos": "video",
}


class PostingScheduler:
    def __init__(self, schedule_path: Path):
        with open(schedule_path) as f:
            self.config = yaml.safe_load(f)
        self.mix = self.config.get("content_mix", {})

    def get_upcoming_slots(self, now: datetime, hours_ahead: int = 24) -> list[dict]:
        """Return all posting slots within the next N hours, across all platforms."""
        slots = []
        end = now + timedelta(hours=hours_ahead)
        current = now.replace(second=0, microsecond=0)

        platforms_config = {
            "instagram": self.config.get("instagram", {}),
            "youtube": self.config.get("youtube", {}),
        }

        while current <= end:
            day_name = current.strftime("%A").lower()

            for platform, platform_cfg in platforms_config.items():
                for slot_type, daily_schedule in platform_cfg.items():
                    if slot_type in ("max_posts_per_day", "max_shorts_per_day",
                                     "max_videos_per_day", "min_gap_hours"):
                        continue

                    times_today = daily_schedule.get(day_name, [])
                    for time_str in times_today:
                        hour, minute = map(int, time_str.split(":"))
                        slot_dt = current.replace(hour=hour, minute=minute)
                        if slot_dt > now:
                            content_type = CONTENT_TYPE_MAP.get(slot_type, "reel")
                            # Apply content mix ratio
                            content_type = self._apply_mix(platform, content_type)
                            slots.append({
                                "platform": platform,
                                "slot_type": slot_type,
                                "content_type": content_type,
                                "time": slot_dt,
                            })

            current += timedelta(days=1)
            current = current.replace(hour=0, minute=0)

        # Sort by time and enforce gap constraints
        slots.sort(key=lambda s: s["time"])
        return self._enforce_gaps(slots)

    def content_type_for_slot(self, slot: dict) -> str:
        return slot.get("content_type", "reel")

    def _apply_mix(self, platform: str, base_type: str) -> str:
        """Randomly apply content mix ratio (e.g. 60% reels vs 40% images)."""
        import random
        ratio = self.mix.get("reels_vs_images_ratio", 0.6)
        if platform == "instagram" and base_type in ("reel", "image"):
            return "reel" if random.random() < ratio else "image"
        if platform == "youtube" and base_type in ("short", "video"):
            shorts_ratio = self.mix.get("shorts_vs_videos_ratio", 0.85)
            return "short" if random.random() < shorts_ratio else "video"
        return base_type

    def _enforce_gaps(self, slots: list[dict]) -> list[dict]:
        """Remove slots too close together per platform."""
        filtered = []
        last_by_platform: dict[str, datetime] = {}

        for slot in slots:
            platform = slot["platform"]
            cfg = self.config.get(platform, {})
            min_gap_h = cfg.get("min_gap_hours", 3)
            last = last_by_platform.get(platform)

            if last is None or (slot["time"] - last).total_seconds() >= min_gap_h * 3600:
                filtered.append(slot)
                last_by_platform[platform] = slot["time"]

        return filtered

    def is_blackout(self, dt: datetime) -> bool:
        """Return True if datetime falls within a blackout period."""
        blackouts = self.config.get("engagement_windows", {}).get("blackout_periods", [])
        for period in blackouts:
            start_str, end_str = period.split("-")
            sh, sm = map(int, start_str.split(":"))
            eh, em = map(int, end_str.split(":"))
            slot_minutes = dt.hour * 60 + dt.minute
            start_minutes = sh * 60 + sm
            end_minutes = eh * 60 + em
            if start_minutes <= slot_minutes < end_minutes:
                return True
        return False
