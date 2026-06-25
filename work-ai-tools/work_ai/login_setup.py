"""One-time GitHub SSO login setup for the Day Job scraper.

Run from your terminal (not from the server):
    cd arbiter-mission-control
    source venv/bin/activate
    python -m dayjob.login_setup

This opens a visible Chromium window where you complete GitHub SSO.
The session is saved to ~/.arbiter/chromium-profile and reused headlessly
by the server on subsequent queries.
"""
from __future__ import annotations

import os
import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

_DEFAULT_PROFILE_DIR = pathlib.Path.home() / ".arbiter" / "chromium-profile"


def _load_env_file() -> None:
    env_path = pathlib.Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    _load_env_file()

    profile_dir = pathlib.Path(
        os.getenv("DAYJOB_BROWSER_PROFILE_PATH", "") or str(_DEFAULT_PROFILE_DIR)
    )
    profile_dir.mkdir(parents=True, exist_ok=True)

    base_url = os.getenv("DAYJOB_GITHUB_BASE_URL", "https://github.com")
    org = os.getenv("DAYJOB_GITHUB_ORG", "")

    if not org:
        print("ERROR: DAYJOB_GITHUB_ORG not set in .env")
        sys.exit(1)

    target_url = f"{base_url}/{org}"
    marker = profile_dir / ".logged_in"

    print(f"Profile directory: {profile_dir}")
    print(f"Target URL: {target_url}")
    print()

    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        accept_downloads=False,
        args=["--disable-blink-features=AutomationControlled"],
    )

    page = context.new_page()
    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

    current = page.url
    if base_url in current and "/login" not in current and "/sso" not in current:
        print("Already logged in.")
        marker.touch()
        context.close()
        pw.stop()
        print("Done — session saved. Restart the ARBITER server and try a query.")
        return

    print("=" * 60)
    print("  Complete the GitHub SSO login in the Chromium window.")
    print("  This script will wait up to 5 minutes.")
    print("=" * 60)
    print()

    for i in range(300):
        time.sleep(1)
        url = page.url
        on_github = base_url in url
        past_login = "/login" not in url and "/sso" not in url
        if on_github and past_login:
            print(f"Login detected (URL: {url})")
            marker.touch()
            print(f"Session saved to {profile_dir}")
            time.sleep(2)
            context.close()
            pw.stop()
            print("Done — restart the ARBITER server and try a query.")
            return
        if i % 30 == 0 and i > 0:
            print(f"  Still waiting... ({i}s elapsed)")

    print("ERROR: Timed out after 5 minutes. Try again.")
    context.close()
    pw.stop()
    sys.exit(1)


if __name__ == "__main__":
    main()
