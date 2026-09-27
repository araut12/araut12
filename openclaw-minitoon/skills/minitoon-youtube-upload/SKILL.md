---
name: "minitoon-youtube-upload"
description: "Upload a finished Minitoon MP4 to YouTube as a Short (marked Made for Kids). Use after minitoon-render has produced the video and the YouTube title/description/tags are ready."
---

# Minitoon YouTube Upload (free)

## Steps

1. You need: the MP4 path from `minitoon-render`, plus a title (max 100 chars, no clickbait), a short kid-friendly description and 5-10 tags (from `minitoon-youtube-optimizer`).
2. Run:
   ```bash
   ~/.openclaw/venv-youtube/bin/python ~/.openclaw/workspace-minitoon/skills/minitoon-youtube-upload/youtube_upload.py \
     "<mp4 path>" --title "<title>" --description "<description>" --tags "<tag1,tag2,...>" --privacy public
   ```
3. Reply with the YouTube link it prints.

## Rules

- Upload at most ONE video per day. Never upload the same MP4 twice.
- If it says "not signed in", stop and tell the user to run the `--login` command. Never try to sign in yourself.
- If the upload fails, report the error. Do not retry more than once.
