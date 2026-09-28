#!/usr/bin/env python3
"""Pick up the pictures and song the user sent on Telegram, without relying on the chat AI.

Runs every 5 minutes (OpenClaw cron). For today's episode that is waiting for pictures:
- collects new images and audio that arrived after the pitch;
- matches pictures to scenes with Gemini vision (any order, duplicates skipped);
- tells the user the progress ("Got 5 of 7 ✅");
- when all scenes have pictures AND a song has arrived (or 45 minutes have passed since the last
  picture, then ACE-Step sings the lyrics), it runs `team.py publish` and sends the links.
"""
import base64
import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import team  # noqa: E402

INBOUND = team.HOME / "media/inbound"
CHAT = (team.HOME / "secrets/telegram_chat_id").read_text().strip()
IMAGES, AUDIO = {".jpg", ".jpeg", ".png", ".webp"}, {".mp3", ".m4a", ".wav", ".ogg", ".aac"}
WAIT_FOR_SONG = 45 * 60


def tell(text: str) -> None:
    subprocess.run(["openclaw", "message", "send", "--channel", "telegram", "-t", CHAT, "-m", text],
                   capture_output=True, text=True)


def thumb(path: Path) -> str:
    out = Path("/tmp") / f"intake-{path.stem}.jpg"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-vf", "scale=512:-2", str(out)],
                   check=True)
    return base64.b64encode(out.read_bytes()).decode()


def match(ep: dict, pics: list[Path]) -> dict[int, int]:
    """Ask Gemini which picture shows which scene. Returns {scene_index: picture_index}."""
    parts = []
    for k, p in enumerate(pics):
        parts += [{"text": f"PICTURE {k + 1}:"}, {"inline_data": {"mime_type": "image/jpeg", "data": thumb(p)}}]
    scenes = "\n".join(f"SCENE {i + 1}: {s.get('image', '')[-260:]}" for i, s in enumerate(ep["scenes"]))
    parts.append({"text": f"These pictures were made for a kids' song video. Scenes:\n{scenes}\n\n"
                          "Match each scene to the ONE picture that best shows it. Use each picture at most once; "
                          "near-duplicate pictures count as one. If no picture fits a scene, use null.\n"
                          'Reply with JSON only, like {"1": 3, "2": 1, "3": null}.'})
    body = json.dumps({"contents": [{"role": "user", "parts": parts}],
                       "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}).encode()
    import urllib.request
    for model in team.MODELS * 2:
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=body, headers={"Content-Type": "application/json", "x-goog-api-key": team.KEY})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                text = json.load(r)["candidates"][0]["content"]["parts"][0]["text"]
            raw = json.loads(text[text.index("{"): text.rindex("}") + 1])
            out, used = {}, set()
            for s, p in raw.items():
                if p and int(p) - 1 not in used and 1 <= int(p) <= len(pics):
                    out[int(s) - 1] = int(p) - 1
                    used.add(int(p) - 1)
            return out
        except Exception as e:
            team.log(f"  vision retry ({model}: {str(e)[:100]})")
            time.sleep(10)
    # Vision unavailable: fall back to arrival order.
    return {i: i for i in range(min(len(pics), len(ep["scenes"])))}


def main() -> None:
    day = date.today().isoformat()
    path = team.DAILY / day / "episode.json"
    if not path.exists():
        return
    ep = json.loads(path.read_text())
    if ep.get("status") != "waiting_for_pictures":
        return
    since = ep.get("pitched_at") or path.parent.stat().st_mtime
    used = set(ep.get("used_media", []))
    new = sorted((f for f in INBOUND.iterdir() if f.stat().st_mtime > since and f.name not in used),
                 key=lambda f: f.stat().st_mtime)
    new_pics = [f for f in new if f.suffix.lower() in IMAGES]
    new_songs = [f for f in new if f.suffix.lower() in AUDIO]
    changed = False

    if new_songs:
        song = new_songs[-1]  # the last one sent wins
        dest = path.parent / f"song{song.suffix.lower()}"
        dest.write_bytes(song.read_bytes())
        ep["song_file"] = str(dest)
        used.update(f.name for f in new_songs)
        tell("Got the song 🎵")
        changed = True

    if new_pics:
        # Re-match with every picture received so far, so late or out-of-order pictures still land right.
        pool = [Path(p) for p in ep.get("picture_pool", [])] + new_pics
        ep["picture_pool"] = [str(p) for p in pool]
        mapping = match(ep, pool)
        for i, s in enumerate(ep["scenes"]):
            if i in mapping:
                dest = path.parent / f"{i + 1:02d}.jpg"
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(pool[mapping[i]]), str(dest)],
                               check=True)
                s["image_file"] = str(dest)
        used.update(f.name for f in new_pics)
        ep["last_picture_at"] = time.time()
        have = sum(1 for s in ep["scenes"] if s.get("image_file"))
        missing = [i + 1 for i, s in enumerate(ep["scenes"]) if not s.get("image_file")]
        msg = f"Got {have} of {len(ep['scenes'])} ✅"
        if missing:
            msg += f" (still need scene {', '.join(map(str, missing))})"
        tell(msg)
        changed = True

    ep["used_media"] = sorted(used)
    have_all = all(s.get("image_file") for s in ep["scenes"])
    waited = time.time() - ep.get("last_picture_at", time.time())
    ready = have_all and (ep.get("song_file") or waited > WAIT_FOR_SONG)
    if have_all and not ep.get("song_file") and changed:
        tell("All pictures in! 🎨 Send the Suno MP3 now, or I'll sing it myself in 45 minutes.")
    if not ready:
        if changed:
            path.write_text(json.dumps(ep, indent=2))
        return

    ep["status"] = "rendering"
    path.write_text(json.dumps(ep, indent=2))
    tell("🎬 Making the 16:9 video and the Shorts now, about 15-20 minutes…")
    r = subprocess.run(["python3", str(Path(__file__).resolve().parent / "team.py"), "publish", "--date", day],
                       capture_output=True, text=True)
    if r.returncode:
        ep = json.loads(path.read_text())
        if ep.get("status") != "posted":
            ep["status"] = "waiting_for_pictures"  # allow a retry on the next run
            path.write_text(json.dumps(ep, indent=2))
        tell(f"⚠️ Video failed: {(r.stdout + r.stderr)[-400:]}")
        return
    res = json.loads(r.stdout[r.stdout.index("{"):])
    lines = [f"🎉 Posted: {res['title']}", f"▶️ {res.get('wide')}"]
    lines += [f"📱 Short {k}: {s}" for k, s in enumerate(res.get("shorts", []), 1)]
    tell("\n".join(lines))


if __name__ == "__main__":
    main()
