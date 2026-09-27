"""Post a video to TikTok with the Content Posting API (Direct Post).

One-time sign-in:  python scripts/tiktok_upload.py --login
Upload:            python scripts/tiktok_upload.py VIDEO --caption "text #tags"

Until TikTok audits your app, posts can only be SELF_ONLY (visible to you).
"""
import argparse
import base64
import hashlib
import http.server
import os
import secrets
import time
import urllib.parse
import webbrowser

import requests

from common import env, read_json, resolve, write_json

API = "https://open.tiktokapis.com/v2"
REDIRECT_PORT = 8723
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback/"
MIN_CHUNK = 5 * 1024 * 1024
CHUNK = 10 * 1024 * 1024


def token_file():
    return resolve(env("TIKTOK_TOKEN_FILE", "./secrets/tiktok_token.json"))


def save_token(data: dict) -> dict:
    data["expires_at"] = time.time() + data.get("expires_in", 0) - 60
    write_json(token_file(), data)
    return data


def login() -> None:
    """OAuth with PKCE. Register REDIRECT_URI in your TikTok app settings first."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
        "client_key": env("TIKTOK_CLIENT_KEY"),
        "scope": "user.info.basic,video.publish",
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            result.update(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"TikTok sign-in complete. You can close this tab.")

        def log_message(self, *args):
            pass

    print(f"Opening browser for TikTok sign-in:\n{url}")
    webbrowser.open(url)
    with http.server.HTTPServer(("localhost", REDIRECT_PORT), Handler) as server:
        server.handle_request()

    if result.get("state", [None])[0] != state or "code" not in result:
        raise SystemExit(f"TikTok sign-in failed: {result}")
    r = requests.post(f"{API}/oauth/token/", data={
        "client_key": env("TIKTOK_CLIENT_KEY"),
        "client_secret": env("TIKTOK_CLIENT_SECRET"),
        "code": result["code"][0],
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }, timeout=30)
    r.raise_for_status()
    save_token(r.json())
    print(f"Saved TikTok token to {token_file()}")


def access_token() -> str:
    token = read_json(token_file())
    if not token:
        raise SystemExit("No TikTok token yet. Run: python scripts/tiktok_upload.py --login")
    if time.time() >= token.get("expires_at", 0):
        r = requests.post(f"{API}/oauth/token/", data={
            "client_key": env("TIKTOK_CLIENT_KEY"),
            "client_secret": env("TIKTOK_CLIENT_SECRET"),
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
        }, timeout=30)
        r.raise_for_status()
        token = save_token(r.json())
    return token["access_token"]


def api(path: str, token: str, body: dict) -> dict:
    r = requests.post(f"{API}{path}", json=body, timeout=60, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
    })
    data = r.json()
    if data.get("error", {}).get("code") not in ("ok", None):
        raise SystemExit(f"TikTok {path} failed: {data['error']}")
    return data["data"]


def upload(video: str, caption: str) -> str:
    token = access_token()

    # TikTok requires checking the creator's allowed privacy levels before posting.
    creator = api("/post/publish/creator_info/query/", token, {})
    privacy = env("TIKTOK_PRIVACY", "SELF_ONLY")
    if privacy not in creator["privacy_level_options"]:
        raise SystemExit(f"Privacy {privacy} not allowed; options: {creator['privacy_level_options']}")

    size = os.path.getsize(video)
    chunk = size if size < MIN_CHUNK else CHUNK
    count = max(1, size // chunk)  # the last chunk absorbs the remainder

    init = api("/post/publish/video/init/", token, {
        "post_info": {"title": caption[:2200], "privacy_level": privacy, "is_aigc": True},
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": chunk,
            "total_chunk_count": count,
        },
    })

    with open(video, "rb") as f:
        for i in range(count):
            start = i * chunk
            end = size - 1 if i == count - 1 else start + chunk - 1
            f.seek(start)
            r = requests.put(init["upload_url"], data=f.read(end - start + 1), timeout=300, headers={
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes {start}-{end}/{size}",
            })
            r.raise_for_status()

    publish_id = init["publish_id"]
    for _ in range(60):
        status = api("/post/publish/status/fetch/", token, {"publish_id": publish_id})
        if status["status"] == "PUBLISH_COMPLETE":
            return f"TikTok publish_id {publish_id} ({privacy})"
        if status["status"] == "FAILED":
            raise SystemExit(f"TikTok publish failed: {status.get('fail_reason')}")
        time.sleep(10)
    return f"TikTok publish_id {publish_id} still processing"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("video", nargs="?")
    p.add_argument("--caption", default="")
    p.add_argument("--login", action="store_true")
    a = p.parse_args()
    if a.login:
        login()
    elif a.video:
        print(upload(a.video, a.caption))
    else:
        p.error("give a VIDEO path or --login")
