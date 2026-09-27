#!/usr/bin/env python3
"""Upload a Minitoon video to YouTube as a Short (free: YouTube Data API).

One-time sign-in:  youtube_upload.py --login
Upload:            youtube_upload.py VIDEO --title T --description D --tags a,b [--privacy public]

Needs ~/.openclaw/secrets/youtube_client_secret.json (Google Cloud OAuth "Desktop app" client).
"""
import argparse
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SECRETS = Path.home() / ".openclaw/secrets"
CLIENT = SECRETS / "youtube_client_secret.json"
TOKEN = SECRETS / "youtube_token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def credentials(interactive: bool = False) -> Credentials:
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif interactive:
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES)
        creds = flow.run_local_server(port=8765, open_browser=False,
                                      authorization_prompt_message="Open this link in your browser:\n{url}\n")
    else:
        raise SystemExit("YouTube not signed in. Run: youtube_upload.py --login")
    TOKEN.write_text(creds.to_json())
    TOKEN.chmod(0o600)
    return creds


def upload(video: str, title: str, description: str, tags: list[str], privacy: str) -> str:
    youtube = build("youtube", "v3", credentials=credentials())
    if "#shorts" not in (title + description).lower():
        description = f"{description}\n\n#Shorts".strip()
    body = {
        "snippet": {"title": title[:100], "description": description[:5000],
                    "tags": tags, "categoryId": "1"},  # Film & Animation
        "status": {
            "privacyStatus": privacy,
            # Minitoon is made for children 3-8; YouTube (COPPA) requires this flag.
            "selfDeclaredMadeForKids": True,
            "containsSyntheticMedia": True,
        },
    }
    media = MediaFileUpload(video, mimetype="video/mp4", chunksize=8 << 20, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    return f"https://youtube.com/shorts/{response['id']} ({privacy})"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("video", nargs="?")
    p.add_argument("--title")
    p.add_argument("--description", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--privacy", default="private", choices=["public", "unlisted", "private"])
    p.add_argument("--login", action="store_true")
    a = p.parse_args()
    if a.login:
        credentials(interactive=True)
        print(f"Signed in. Token saved to {TOKEN}")
    elif a.video and a.title:
        print(upload(a.video, a.title, a.description, [t.strip() for t in a.tags.split(",") if t.strip()], a.privacy))
    else:
        p.error("give VIDEO and --title, or --login")
