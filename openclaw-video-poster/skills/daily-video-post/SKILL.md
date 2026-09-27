---
name: daily-video-post
description: Generate a short AI video and post it to YouTube Shorts and TikTok. Use when asked to "post today's video", or when the daily video cron job fires.
metadata: {"openclaw":{"requires":{"bins":["python3"],"env":["REPLICATE_API_TOKEN","TIKTOK_CLIENT_KEY","TIKTOK_CLIENT_SECRET"]}}}
---

# Daily video post

Project folder: `{{PROJECT_DIR}}` (the setup script fills this in).

## Steps

1. Read `{{PROJECT_DIR}}/content.md` for the channel theme, style and banned topics.
   Read the last 14 lines of `{{PROJECT_DIR}}/output/posted.jsonl` if it exists, so today's idea does not repeat a recent one.
2. Come up with ONE fresh idea that fits the theme. Write:
   - `prompt`: a vivid text-to-video prompt, 1-3 sentences, with the subject, motion, camera and lighting. Vertical 9:16. No real people, logos or copyrighted characters.
   - `title`: a catchy title, 60 characters or fewer.
   - `caption`: 1-2 short sentences plus 3-5 relevant hashtags.
   - `tags`: 3-6 comma-separated keywords.
3. Run the pipeline (it can take up to 20 minutes):
   ```bash
   cd {{PROJECT_DIR}} && .venv/bin/python scripts/post_video.py \
     --prompt "<prompt>" --title "<title>" --caption "<caption>" --tags "<tags>"
   ```
4. Reply with a short summary: the title, the YouTube link, the TikTok result, and any error.
   If a platform failed, do NOT retry more than once. Report the error text instead.

## Rules

- Post at most once per day. The script skips on its own if today's post already went out; never pass `--force` unless the user explicitly asks.
- Never print or share the contents of `.env` or `secrets/`.
- If the user says "test" or "dry run", add `--dry-run` (generates the video without posting).
