#!/usr/bin/env python3
"""Growth Manager: thumbnails, playlists, weekly compilation and analytics for @MiniToons.

  growth.py login                 one-time sign-in with playlist, thumbnail and analytics permissions
  growth.py after-post [--date D] thumbnail + playlists for the day's posted episode (run after publish)
  growth.py compilation [--dry-run] this week's songs joined into one video, uploaded and playlisted
  growth.py insights              analytics review -> lessons into the team's LEARNINGS.md + Telegram report
  growth.py weekly                compilation + insights (Sunday cron)

Uses the Growth Manager specialist (workspace-minitoon-growth-agent/SOUL.md + LEARNINGS.md) via team.py.
"""
import argparse
import glob
import json
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import team  # noqa: E402

team.AGENTS["growth"] = "minitoon-growth-agent"
SECRETS = team.HOME / "secrets"
CLIENT = SECRETS / "youtube_client_secret.json"
TOKEN = SECRETS / "youtube_growth_token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
UPLOAD = team.SKILLS / "minitoon-youtube-upload/youtube_upload.py"
YT_PY = str(team.HOME / "venv-youtube/bin/python")
CHAT = (SECRETS / "telegram_chat_id").read_text().strip()


def tell(text: str) -> None:
    subprocess.run(["openclaw", "message", "send", "--channel", "telegram", "-t", CHAT, "-m", text],
                   capture_output=True, text=True)


def creds(interactive: bool = False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    c = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if c and c.valid:
        return c
    if c and c.expired and c.refresh_token:
        c.refresh(Request())
    elif interactive:
        raise SystemExit("use: growth.py login (prints a link), then growth.py login-finish '<localhost address>'")
    else:
        raise SystemExit("FAILED: growth sign-in missing. Run: growth.py login")
    TOKEN.write_text(c.to_json())
    TOKEN.chmod(0o600)
    return c


PENDING = SECRETS / "youtube_growth_login_pending.json"
REDIRECT = "http://localhost:8766/"


def login_start() -> None:
    """Step 1: print the sign-in link. The browser lands on a localhost address that the user pastes back."""
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(str(CLIENT), SCOPES, redirect_uri=REDIRECT, autogenerate_code_verifier=True)
    url, state = flow.authorization_url(access_type="offline", prompt="consent")
    PENDING.write_text(json.dumps({"state": state, "verifier": flow.code_verifier}))
    PENDING.chmod(0o600)
    print(url)


def login_finish(address: str) -> None:
    """Step 2: exchange the code in the pasted localhost address for a saved token."""
    import os
    from google_auth_oauthlib.flow import Flow
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # the redirect is plain-http localhost by design
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    p = json.loads(PENDING.read_text())
    flow = Flow.from_client_secrets_file(str(CLIENT), SCOPES, redirect_uri=REDIRECT, state=p["state"])
    flow.code_verifier = p["verifier"]
    flow.fetch_token(authorization_response=address.strip())
    TOKEN.write_text(flow.credentials.to_json())
    TOKEN.chmod(0o600)
    PENDING.unlink()
    print("Growth sign-in saved")


def yt():
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=creds())


def video_id(link: str) -> str:
    link = link.split()[0]
    return link.split("v=")[-1] if "v=" in link else link.rstrip("/").split("/")[-1]


def episodes() -> list[tuple[Path, dict]]:
    out = []
    for f in sorted(glob.glob(str(team.DAILY / "*/episode.json"))):
        try:
            out.append((Path(f), json.loads(Path(f).read_text())))
        except Exception:
            pass
    return out


# ---------- thumbnails ----------

def thumbnail(ep_path: Path, ep: dict, vid: str) -> str:
    words = team.ask("growth", f"Task: THUMBNAIL_TEXT\nTITLE: {ep['title']}\nLYRICS:\n{ep.get('song_lyrics', '')[:800]}",
                     lambda t: team.field(t, "TEXT").splitlines()[0].strip().strip('"')[:18])
    words = "".join(ch for ch in words if ch.isalnum() or ch in " !?'&").strip().upper() or "SING ALONG!"
    pic = next((s["image_file"] for s in ep["scenes"] if s.get("image_file")), None)
    if not pic:
        return "no picture"
    out = ep_path.parent / "thumbnail.jpg"
    text = words.replace("'", "’")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", pic, "-vf",
                    "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,eq=saturation=1.25:contrast=1.05,"
                    f"drawtext=fontfile={FONT}:text='{text}':fontsize=118:fontcolor=white:borderw=10:"
                    "bordercolor=0xE0508A:x=(w-text_w)/2:y=h-text_h-60",
                    "-q:v", "3", str(out)], check=True)
    from googleapiclient.http import MediaFileUpload
    try:
        yt().thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(out), mimetype="image/jpeg")).execute()
        return f"thumbnail set ({words})"
    except Exception as e:
        msg = str(e)
        if "403" in msg or "forbidden" in msg.lower():
            return "thumbnail NOT set: verify the channel at youtube.com/verify to allow custom thumbnails"
        return f"thumbnail failed: {msg[:160]}"


# ---------- playlists ----------

def playlists(service) -> dict[str, str]:
    out, token = {}, None
    while True:
        r = service.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=token).execute()
        out.update({p["snippet"]["title"]: p["id"] for p in r.get("items", [])})
        token = r.get("nextPageToken")
        if not token:
            return out


def parse_playlists(text: str) -> list[str]:
    import re
    names = [n.strip().strip('"')[:60] for n in re.findall(r"PLAYLIST:\s*(.+)", text)][:2]
    if not names:
        raise ValueError("no PLAYLIST lines")
    return names


def add_to_playlists(ep: dict, vid: str, names: list[str] | None = None) -> list[str]:
    service = yt()
    existing = playlists(service)
    if names is None:
        names = team.ask("growth", f"Task: PLAYLISTS\nEPISODE: {ep['title']}\nSUMMARY: {ep.get('summary', '')}\n"
                                   f"EXISTING PLAYLISTS: {', '.join(existing) or 'none yet'}", parse_playlists)
    done = []
    for name in names:
        pid = existing.get(name)
        if not pid:
            pid = service.playlists().insert(part="snippet,status", body={
                "snippet": {"title": name, "description": f"{name} from MiniToons 🐰 New Bunny songs every day!"},
                "status": {"privacyStatus": "public"}}).execute()["id"]
        service.playlistItems().insert(part="snippet", body={
            "snippet": {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
        done.append(name)
    return done


def after_post(day: str) -> None:
    ep_path = team.DAILY / day / "episode.json"
    ep = json.loads(ep_path.read_text())
    wide = (ep.get("youtube") or {}).get("wide")
    if not wide or ep.get("growth_done"):
        print("nothing to do")
        return
    vid = video_id(wide)
    report = [thumbnail(ep_path, ep, vid)]
    try:
        report.append("playlists: " + ", ".join(add_to_playlists(ep, vid)))
    except Exception as e:
        report.append(f"playlists failed: {str(e)[:160]}")
    ep["growth_done"] = report
    ep_path.write_text(json.dumps(ep, indent=2))
    print("\n".join(report))


# ---------- weekly compilation ----------

def compilation(dry: bool) -> None:
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    picks = [(p, e) for p, e in episodes()
             if p.parent.name >= week_ago and e.get("status") == "posted" and e.get("wide_file")
             and Path(e["wide_file"]).exists()]
    if len(picks) < 3:
        print(f"only {len(picks)} songs this week, skipping the compilation")
        return
    work = team.HOME / f"workspace-minitoon/output/compilations/{date.today().isoformat()}"
    work.mkdir(parents=True, exist_ok=True)
    listing = work / "list.txt"
    listing.write_text("".join(f"file '{e['wide_file']}'\n" for _, e in picks))
    video = work / "compilation.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", str(video)], check=True)
    titles = "\n".join(f"{i}. {e['title']}" for i, (_, e) in enumerate(picks, 1))
    meta = team.ask("growth", f"Task: COMPILATION\nSONGS THIS WEEK:\n{titles}", team.parse_youtube)
    if dry:
        print(json.dumps({"file": str(video), **meta}, indent=2))
        return
    r = subprocess.run([YT_PY, str(UPLOAD), str(video), "--wide", "--privacy", "public", "--title", meta["title"],
                        "--description", meta["description"], "--tags", meta["tags"]], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"FAILED: compilation upload: {r.stderr[-300:]}")
    link = r.stdout.strip().splitlines()[-1]
    try:
        add_to_playlists({"title": meta["title"]}, video_id(link), ["Bunny Song Compilations"])
    except Exception as e:
        team.log(f"playlist failed: {e}")
    tell(f"📼 Weekly compilation posted ({len(picks)} songs): {link}")
    print(link)


# ---------- insights ----------

def insights() -> None:
    from googleapiclient.discovery import build
    posted = {video_id(e["youtube"]["wide"]): e["title"] for _, e in episodes()
              if isinstance(e.get("youtube"), dict) and e["youtube"].get("wide")}
    if not posted:
        print("no posted videos yet")
        return
    ya = build("youtubeAnalytics", "v2", credentials=creds())
    end, start = date.today().isoformat(), (date.today() - timedelta(days=28)).isoformat()
    rows = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end,
                              metrics="views,estimatedMinutesWatched,averageViewPercentage,subscribersGained",
                              dimensions="video", sort="-views", maxResults=50).execute().get("rows", [])
    sources = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end, metrics="views",
                                 dimensions="insightTrafficSourceType", sort="-views").execute().get("rows", [])
    table = "\n".join(f"- {posted.get(r[0], r[0])}: views {r[1]}, minutes {r[2]}, avg watched {r[3]}%, subs +{r[4]}"
                      for r in rows) or "no views yet"
    src = ", ".join(f"{s[0]} {s[1]}" for s in sources) or "none"
    text = team.gemini(team.instructions("growth"), f"Task: INSIGHTS\n\nLAST 28 DAYS PER VIDEO:\n{table}\n\n"
                                                    f"TRAFFIC SOURCES: {src}", 0.3)
    today = date.today().isoformat()
    targets = {"STORY": "minitoon-story-agent", "SONG": "minitoon-audio-agent",
               "YOUTUBE": "minitoon-youtube-agent", "GROWTH": "minitoon-growth-agent"}
    learned = []
    for key, agent in targets.items():
        try:
            rule = team.field(text, key).splitlines()[0].strip()
        except ValueError:
            continue
        if rule and rule.lower() != "none":
            with (team.HOME / f"workspace-{agent}/LEARNINGS.md").open("a") as f:
                f.write(f"- {today} (analytics): {rule}\n")
            learned.append(f"{key.title()}: {rule}")
    try:
        summary = team.field(text, "SUMMARY", "STORY")
    except ValueError:
        summary = text[:600]
    tell("📈 Weekly channel report\n" + summary + ("\n\nThe team learned:\n" + "\n".join(learned) if learned else ""))
    print(summary)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=["login", "login-finish", "after-post", "compilation", "insights", "weekly"])
    p.add_argument("address", nargs="?", help="for login-finish: the localhost address from the browser")
    p.add_argument("--date", default=date.today().isoformat())
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    if a.step == "login":
        login_start()
    elif a.step == "login-finish":
        login_finish(a.address)
    elif a.step == "after-post":
        after_post(a.date)
    elif a.step == "compilation":
        compilation(a.dry_run)
    elif a.step == "insights":
        insights()
    else:
        for step in (lambda: compilation(False), insights):
            try:
                step()
            except SystemExit as e:
                tell(f"⚠️ Growth weekly step failed: {e}")
