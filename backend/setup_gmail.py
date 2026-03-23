#!/usr/bin/env python3
"""
NeonTrade AI - Gmail OAuth2 Setup Script
Run this ONCE on a machine with a browser to obtain a refresh token.

Usage:
    python setup_gmail.py

The script will:
1. Open your browser for Google login
2. Ask you to authorize NeonTrade AI to send emails
3. Save the refresh token to your .env file

After running this, copy the GMAIL_REFRESH_TOKEN value to your
EasyPanel environment variables for VPS deployment.
"""

import json
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
TOKEN_PATH = Path(__file__).parent / "data" / "gmail_token.json"


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("ERROR: google-auth-oauthlib not installed.")
        print("Run: pip install google-auth-oauthlib google-api-python-client")
        sys.exit(1)

    client_id = os.getenv("GMAIL_CLIENT_ID", "")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print("ERROR: GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET must be set in .env")
        sys.exit(1)

    # Build OAuth2 client config from environment variables
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    print("=" * 50)
    print("  NeonTrade AI - Gmail OAuth2 Setup")
    print("=" * 50)
    print()
    print("A browser window will open for Google login.")
    print(f"Log in with: {os.getenv('GMAIL_SENDER', 'your Gmail account')}")
    print("Grant permission to send emails on your behalf.")
    print()

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=8090, prompt="consent")

    # Save full token for local use
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    refresh_token = creds.refresh_token

    print()
    print("=" * 50)
    print("  SUCCESS! Gmail OAuth2 configured.")
    print("=" * 50)
    print()
    print(f"Token saved to: {TOKEN_PATH}")
    print()
    print("Your GMAIL_REFRESH_TOKEN:")
    print(f"  {refresh_token}")
    print()

    # Update .env file with the refresh token
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        env_content = env_path.read_text(encoding="utf-8")
        if "GMAIL_REFRESH_TOKEN=" in env_content:
            lines = env_content.split("\n")
            for i, line in enumerate(lines):
                if line.startswith("GMAIL_REFRESH_TOKEN="):
                    lines[i] = f"GMAIL_REFRESH_TOKEN={refresh_token}"
                    break
            env_path.write_text("\n".join(lines), encoding="utf-8")
            print(".env file updated with refresh token.")
        else:
            with open(env_path, "a") as f:
                f.write(f"\nGMAIL_REFRESH_TOKEN={refresh_token}\n")
            print(".env file updated with refresh token.")
    else:
        print("WARNING: .env file not found. Add this to your .env:")
        print(f"  GMAIL_REFRESH_TOKEN={refresh_token}")

    print()
    print("IMPORTANT: Copy the GMAIL_REFRESH_TOKEN to your EasyPanel")
    print("environment variables for VPS deployment.")


if __name__ == "__main__":
    main()
