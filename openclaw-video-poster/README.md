# OpenClaw daily AI video poster

Every day at a set time, OpenClaw comes up with a video idea, generates the video with AI (Replicate) and posts it to **YouTube Shorts** and **TikTok**.

```
OpenClaw cron (daily) ──► daily-video-post skill ──► scripts/post_video.py
                                                       ├─ generate_video.py  (Replicate)
                                                       ├─ youtube_upload.py  (YouTube Data API)
                                                       └─ tiktok_upload.py   (TikTok Content Posting API)
```

## 1. Install OpenClaw (skip this if it's already installed)

```bash
npm install -g openclaw@latest
openclaw onboard --install-daemon   # the daemon lets cron jobs run in the background
```

## 2. Get API keys

| Service | What you need |
|---|---|
| Replicate | API token from replicate.com/account/api-tokens |
| YouTube | Google Cloud project → enable **YouTube Data API v3** → OAuth client of type **Desktop app** → download the JSON to `secrets/youtube_client_secret.json` |
| TikTok | App on developers.tiktok.com with **Login Kit** and **Content Posting API** (Direct Post), scopes `user.info.basic` and `video.publish`, redirect URI `http://localhost:8723/callback/` |

> TikTok note: until TikTok audits your app, posts can only be private (`SELF_ONLY`). After the audit, set `TIKTOK_PRIVACY=PUBLIC_TO_EVERYONE` in `.env`.
> YouTube note: an unverified Google Cloud project may lock uploads to private. Apply for an API audit if that happens.

## 3. Set up

```bash
./setup_openclaw.sh 18:00 America/New_York   # time and your timezone
```

This creates the Python venv, copies `.env.example` to `.env`, installs the skill into OpenClaw and creates the daily cron job. Then:

```bash
# fill in .env, then sign in once to each platform:
.venv/bin/python -c 'import sys; sys.path.insert(0,"scripts"); import youtube_upload as y; y.credentials()'
.venv/bin/python scripts/tiktok_upload.py --login

# test without posting
.venv/bin/python scripts/post_video.py --prompt "a paper boat sailing through a neon city at night" --title test --dry-run

# run the real OpenClaw job now
openclaw cron run "Daily video post"
```

## Everyday use

- Edit `content.md` to change the channel theme. OpenClaw reads it before each post.
- `output/posted.jsonl` logs every post. It also prevents a second post on the same day.
- `openclaw cron list` / `openclaw cron remove "Daily video post"` shows or stops the schedule.
- Your computer has to be awake at the scheduled time for the job to run.
