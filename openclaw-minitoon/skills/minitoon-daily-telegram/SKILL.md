---
name: "minitoon-daily-telegram"
description: "Daily Minitoon workflow over Telegram: pitch today's episode with Gemini picture prompts, collect the pictures the user sends back, then render and upload. Use for the morning pitch, and whenever the user sends pictures, approves, or asks to change the idea in Telegram."
---

# Minitoon daily workflow (Telegram)

The user makes the pictures for free in the Gemini app. You do everything else.
NEVER generate, edit or "improve" pictures yourself, and never analyze them at length. Just save
the user's pictures and use them exactly as sent.
Today's working folder: `~/.openclaw/workspace-minitoon/output/daily/<YYYY-MM-DD>/`

## A. Morning pitch (the cron job asks for this)

1. Read `~/.openclaw/workspace-minitoon/characters/CHARACTERS.md` and the titles in
   `~/.openclaw/workspace-minitoon/output/daily/*/episode.json` so you don't repeat an idea.
2. Write a new 35-50 second Bunny story in 7 scenes (hook first, happy lesson at the end, then
   "See you next time!"). Save `episode.json` in today's folder with the format from the
   `minitoon-render` skill, plus `"status": "waiting_for_pictures"`. Do not set `image_file` yet.
3. Send ONE Telegram message, short and friendly, in this format:

   🐰 Today's idea: <title>
   <one-sentence story summary>

   Make these 7 pictures in Gemini (attach your Bunny picture each time), then send them to me in order:
   1️⃣ <full Gemini prompt for scene 1>
   2️⃣ ...
   Reply "new idea" for a different story, or tell me what to change.

   Each Gemini prompt must be self-contained and start with:
   "Use the attached bunny as the character, keep her exactly the same. Vertical 9:16 image, 3D Pixar style: "
   followed by the scene's action and place.

## B. The user replies in Telegram

- "new idea" / change requests → rewrite `episode.json` and send a new pitch (step A.3).
- Pictures → save each one into today's folder as `01.jpg`, `02.jpg`, ... in the order received
  (copy it from the attachment path you are given). Set `image_file` on the matching scene.
  Reply briefly: "Got 3 of 7 ✅".
  If the user sends several at once, number them in the order they appear.
  If the pictures arrive out of order or there are extras, match each scene to the picture that
  best shows it (look at each picture briefly), skip near-duplicates, and tell the user the mapping
  in one line.
- When all scenes have pictures (or the user says "go" / "make it"), set `"status": "rendering"`,
  reply "🎬 Making the video now, about 10 minutes", then:
  1. Render with the `minitoon-render` skill, using today's `episode.json`.
  2. Write the YouTube title, description and tags with `minitoon-youtube-optimizer`.
  3. Upload with `minitoon-youtube-upload` (public).
  4. Set `"status": "posted"` and `"youtube"` in `episode.json`, then reply with the title and the
     YouTube link. Also attach the MP4 if possible.
  If a step fails, reply with the exact error and what the user can do. Never upload twice in a day.

## Rules
- Keep Telegram messages short. No walls of text apart from the prompt list.
- Kid-safe content only (ages 3-8).
