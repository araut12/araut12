#!/usr/bin/env python3
"""Make and post the day's episode: one wide 16:9 video now, plus Shorts cut from it,
scheduled a few hours apart.

Usage:
  publish_day.py EPISODE.json --title T --description D --tags a,b,c [--shorts 4] [--gap-hours 3] [--dry-run]

--dry-run renders and cuts everything but uploads nothing.
Writes the links into EPISODE.json ("youtube") and prints a summary.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path.home()
SKILLS = HOME / ".openclaw/workspace-minitoon/skills"
MEDIA_PY = str(HOME / ".openclaw/venv-media/bin/python")
YT_PY = str(HOME / ".openclaw/venv-youtube/bin/python")
RENDER = str(SKILLS / "minitoon-render/render.py")
CLIP = str(SKILLS / "minitoon-render/clip_shorts.py")
UPLOAD = str(SKILLS / "minitoon-youtube-upload/youtube_upload.py")


def step(*cmd: str) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"FAILED: {Path(cmd[1]).name}\n{(r.stderr or r.stdout)[-800:]}")
    return r.stdout.strip()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("episode")
    p.add_argument("--title", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--shorts", type=int, default=4, help="how many Shorts to cut (max 5: YouTube allows ~6 uploads/day)")
    p.add_argument("--gap-hours", type=float, default=3)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="post even if this episode is already posted")
    a = p.parse_args()

    ep_path = Path(a.episode).expanduser()
    ep = json.loads(ep_path.read_text())
    if ep.get("status") == "posted" and not a.force and not a.dry_run:
        raise SystemExit(f"Already posted: {ep.get('youtube')}")

    print("rendering the wide video...", file=sys.stderr, flush=True)
    wide = step(MEDIA_PY, RENDER, str(ep_path), "--format", "16:9").splitlines()[-1]
    print("cutting Shorts...", file=sys.stderr, flush=True)
    shorts = step(MEDIA_PY, CLIP, wide, "--count", str(min(5, a.shorts))).splitlines()
    result = {"wide_file": wide, "short_files": shorts}

    if not a.dry_run:
        link = step(YT_PY, UPLOAD, wide, "--wide", "--privacy", "public",
                    "--title", a.title, "--description", a.description, "--tags", a.tags)
        result["wide"] = link
        # Mark posted now, so a Short failing below can never cause the main video to be uploaded twice.
        ep["status"] = "posted"
        ep["youtube"] = {"wide": link}
        ep_path.write_text(json.dumps(ep, indent=2))
        now = datetime.now().astimezone()
        result["shorts"] = []
        for k, short in enumerate(shorts, 1):
            when = (now + timedelta(hours=a.gap_hours * k)).replace(microsecond=0).isoformat()
            desc = f"{a.description}\n\nWatch the full song on our channel! 🎵"
            title = f"{a.title[:80]} (Part {k})"
            try:
                result["shorts"].append(step(YT_PY, UPLOAD, short, "--publish-at", when, "--title", title,
                                             "--description", desc, "--tags", a.tags))
            except SystemExit as e:
                result["shorts"].append(f"Part {k} not uploaded: {str(e)[-300:]}")
        ep["youtube"] = {"wide": result["wide"], "shorts": result["shorts"]}
        ep_path.write_text(json.dumps(ep, indent=2))

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
