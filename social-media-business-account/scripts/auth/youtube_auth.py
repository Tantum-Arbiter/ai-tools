"""
YouTube OAuth Setup — run this ONCE on your Windows PC to get a refresh token.
Then add YOUTUBE_REFRESH_TOKEN to your .env file.

Usage:
    python scripts/auth/youtube_auth.py

Prerequisites:
    pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
    Create OAuth 2.0 credentials in Google Cloud Console (Desktop App type)
    Download the credentials JSON and set the path below or use env vars.
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"  # Desktop flow


def main():
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("ERROR: Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env first.")
        return

    from google_auth_oauthlib.flow import InstalledAppFlow

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    credentials = flow.run_local_server(port=0)

    print("\n" + "=" * 60)
    print("SUCCESS! Add this to your .env file:")
    print("=" * 60)
    print(f"YOUTUBE_REFRESH_TOKEN={credentials.refresh_token}")
    print("=" * 60)

    # Optionally save to a local token file (gitignored)
    token_path = Path(__file__).parent.parent.parent / "data" / "youtube_token.json"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_data = {
        "refresh_token": credentials.refresh_token,
        "client_id": client_id,
        # client_secret intentionally omitted from file
    }
    token_path.write_text(json.dumps(token_data, indent=2))
    print(f"\nToken also saved to: {token_path}")
    print("(This file is gitignored — keep it safe)")


if __name__ == "__main__":
    main()
