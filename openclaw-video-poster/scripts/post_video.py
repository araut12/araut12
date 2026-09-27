"""Generate one AI video and post it to YouTube Shorts and TikTok.

Usage:
  python scripts/post_video.py --prompt "..." --title "..." --caption "... #tags" [--tags a,b]
  python scripts/post_video.py --video existing.mp4 --title "..." --caption "..."
  add --dry-run to generate only, without posting.
"""
import argparse
import sys

from common import already_posted_today, log_post


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--prompt", help="text-to-video prompt")
    src.add_argument("--video", help="post an existing file instead of generating")
    p.add_argument("--title", required=True)
    p.add_argument("--caption", default="", help="description / TikTok caption with hashtags")
    p.add_argument("--tags", default="")
    p.add_argument("--platforms", default="youtube,tiktok")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="post even if a post already went out today")
    a = p.parse_args()

    if already_posted_today() and not a.force and not a.dry_run:
        print("Already posted today; skipping (use --force to override).")
        return 0

    if a.video:
        video = a.video
    else:
        from generate_video import generate
        video = generate(a.prompt)
    print(f"Video: {video}")
    if a.dry_run:
        return 0

    results, ok = {}, True
    for platform in [x.strip() for x in a.platforms.split(",") if x.strip()]:
        try:
            if platform == "youtube":
                from youtube_upload import upload
                tags = [t for t in a.tags.split(",") if t]
                results[platform] = upload(video, a.title, a.caption, tags)
            elif platform == "tiktok":
                from tiktok_upload import upload
                results[platform] = upload(video, f"{a.title} {a.caption}".strip())
            else:
                results[platform] = f"unknown platform {platform}"
                ok = False
        except (Exception, SystemExit) as e:  # keep going so one platform can't block the other
            results[platform] = f"ERROR: {e}"
            ok = False
        print(f"{platform}: {results[platform]}")

    log_post({"ok": ok, "video": video, "title": a.title, "prompt": a.prompt, "results": results})
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
