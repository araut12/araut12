"""Upload a video to YouTube (vertical and under 3 minutes = a Short).

First run opens a browser for Google sign-in and stores a refresh token.
Usage: python scripts/youtube_upload.py VIDEO --title T --description D [--tags a,b]
"""
import argparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from common import env, resolve

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def credentials() -> Credentials:
    token_file = resolve(env("YOUTUBE_TOKEN_FILE", "./secrets/youtube_token.json"))
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        secrets = resolve(env("YOUTUBE_CLIENT_SECRETS", "./secrets/youtube_client_secret.json"))
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
        creds = flow.run_local_server(port=0)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json())
    token_file.chmod(0o600)
    return creds


def upload(video: str, title: str, description: str, tags: list[str]) -> str:
    youtube = build("youtube", "v3", credentials=credentials())
    if "#shorts" not in (title + description).lower():
        description = f"{description}\n\n#Shorts".strip()
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags,
            "categoryId": "22",  # People & Blogs
        },
        "status": {
            "privacyStatus": env("YOUTUBE_PRIVACY", "public"),
            "selfDeclaredMadeForKids": False,
            # YouTube asks creators to disclose realistic AI-generated content.
            "containsSyntheticMedia": True,
        },
    }
    media = MediaFileUpload(video, mimetype="video/mp4", chunksize=8 << 20, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    return f"https://youtube.com/shorts/{response['id']}"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("video")
    p.add_argument("--title", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--tags", default="")
    a = p.parse_args()
    print(upload(a.video, a.title, a.description, [t for t in a.tags.split(",") if t]))
