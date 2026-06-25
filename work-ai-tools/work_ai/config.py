"""Day Job configuration — all secrets loaded from .env, never hardcoded."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MondayConfig:
    """Monday.com — READ ONLY. No write token is ever accepted."""

    api_token: str = ""
    board_ids: list[str] = field(default_factory=list)
    api_url: str = "https://api.monday.com/v2"


@dataclass(frozen=True)
class GitHubConfig:
    """GitHub — Playwright-based scraping. Read-only by default.

    Uses a persistent browser profile so the user logs in via SSO once.
    Sprint rollover (only write) requires SafetyGate confirmation.
    """

    org: str = ""
    project_number: int = 0
    repos: list[str] = field(default_factory=list)
    browser_profile_dir: str = ""
    base_url: str = "https://github.com"

    @property
    def has_config(self) -> bool:
        return bool(self.org and self.repos)


@dataclass(frozen=True)
class SlackConfig:
    """Slack — read history + human-gated send."""

    bot_token: str = ""
    channels: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ClarityConfig:
    """Clarity — browser automation, session-based."""

    base_url: str = ""
    profile_dir: str = ""


@dataclass(frozen=True)
class SharePointConfig:
    """SharePoint/PPT — MS Graph delegated auth."""

    client_id: str = ""
    client_secret: str = ""
    tenant_id: str = ""
    drive_id: str = ""
    ppt_path: str = ""


@dataclass(frozen=True)
class DayJobConfig:
    """Top-level config aggregating all integrations."""

    monday: MondayConfig
    github: GitHubConfig
    slack: SlackConfig
    clarity: ClarityConfig
    sharepoint: SharePointConfig


def _split_csv(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


def load_config() -> DayJobConfig:
    """Build config from environment variables. Secrets stay in .env."""
    return DayJobConfig(
        monday=MondayConfig(
            api_token=os.getenv("MONDAY_API_TOKEN", ""),
            board_ids=_split_csv(os.getenv("MONDAY_BOARD_IDS", "")),
        ),
        github=GitHubConfig(
            org=os.getenv("DAYJOB_GITHUB_ORG", ""),
            project_number=int(os.getenv("DAYJOB_GITHUB_PROJECT_NUMBER", "0")),
            repos=_split_csv(os.getenv("DAYJOB_GITHUB_REPOS", "")),
            browser_profile_dir=os.getenv("DAYJOB_BROWSER_PROFILE_PATH", ""),
        ),
        slack=SlackConfig(
            bot_token=os.getenv("SLACK_BOT_TOKEN", ""),
            channels=_split_csv(os.getenv("SLACK_CHANNELS", "")),
        ),
        clarity=ClarityConfig(
            base_url=os.getenv("CLARITY_BASE_URL", ""),
            profile_dir=os.getenv("CLARITY_PROFILE_DIR", ""),
        ),
        sharepoint=SharePointConfig(
            client_id=os.getenv("SHAREPOINT_CLIENT_ID", ""),
            client_secret=os.getenv("SHAREPOINT_CLIENT_SECRET", ""),
            tenant_id=os.getenv("SHAREPOINT_TENANT_ID", ""),
            drive_id=os.getenv("SHAREPOINT_DRIVE_ID", ""),
            ppt_path=os.getenv("SHAREPOINT_PPT_PATH", ""),
        ),
    )
