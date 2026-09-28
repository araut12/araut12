---
name: "minitoon-daily-telegram"
description: "Daily Minitoon workflow over Telegram: pitch today's song episode (Gemini picture prompts + song lyrics for Suno), collect the pictures and song the user sends back, then make one wide video plus Shorts and post them. Use for the morning pitch, and whenever the user sends pictures, a song, approves, or asks to change the idea in Telegram."
---

# Minitoon daily workflow (Telegram)

Every episode is a SONG (like Cocomelon): the whole video is one catchy kids' song, no narrator.
The user makes the pictures (Gemini app) and optionally the song (Suno) by hand. You do everything else.
NEVER generate, edit or "improve" pictures or music yourself with your own tools.
Today's working folder: `~/.openclaw/workspace-minitoon/output/daily/<YYYY-MM-DD>/`

## A. Morning pitch (the cron job asks for this)

1. Read `~/.openclaw/workspace-minitoon/characters/CHARACTERS.md` and the titles in
   `~/.openclaw/workspace-minitoon/output/daily/*/episode.json` so you don't repeat an idea.
2. Write a new Bunny song story in 7 scenes, and the song itself:
   - Song: 60-90 seconds, simple words for ages 3-8, lots of repetition, a very catchy chorus that
     appears at least twice, sound words (whoosh! pop! yum!). Structure:
     [verse] ... [chorus] ... [verse] ... [chorus]
   - Each scene gets the lyric lines sung while it is on screen (`lyrics`). Together the scenes cover
     the whole song in order.
3. Save `episode.json` in today's folder:
   ```json
   {"title": "...", "status": "waiting_for_pictures",
    "song_style": "children's song, cheerful, catchy, bouncy, ukulele, glockenspiel, claps, female child vocals, 120 bpm",
    "song_lyrics": "[verse]\n...\n\n[chorus]\n...",
    "song_seconds": 75,
    "scenes": [{"image": "...", "lyrics": "...", "narration": "<same as lyrics>",
                "motion": "one simple action", "animate": true}]}
   ```
   Mark the 5-6 liveliest scenes `"animate": true`.
4. Send ONE Telegram message:

   🐰 Today's song: <title>
   <one-sentence summary>

   🎨 Make these 7 pictures in Gemini (attach your Bunny picture each time):
   1️⃣ <prompt> ... 7️⃣ <prompt>

   🎵 Optional, for the best song: paste this into Suno (Custom mode), then send me the MP3:
   Style: <song_style>
   Lyrics:
   <song_lyrics>

   Send the pictures in order. If you don't send a song, I'll sing it myself.
   Reply "new idea" for a different story.

   Each Gemini prompt is self-contained and starts with:
   "Use the attached bunny as the character, keep her exactly the same. Wide 16:9 landscape image, character in the center, 3D Pixar style: "

## B. The user replies in Telegram

- "new idea" / change requests → rewrite `episode.json` and send a new pitch (A.4).
- Pictures → save them into today's folder as `01.jpg`, `02.jpg`, ... and set `image_file` on the
  matching scene. Reply briefly: "Got 3 of 7 ✅". If they arrive out of order or there are extras, match
  each scene to the picture that best shows it, skip near-duplicates, and say the mapping in one line.
- An audio file (MP3/M4A/WAV, e.g. from Suno) → copy it to today's folder as `song.mp3` and set
  `"song_file"` to that path. Reply "Got the song 🎵".
- When all scenes have pictures (or the user says "go" / "make it"): set `"status": "rendering"`, reply
  "🎬 Making the video now, about 15 minutes", then:
  1. Write the YouTube title (max 70 chars, fun, include an emoji), a short kid-friendly description
     and 8-12 tags (use `minitoon-youtube-optimizer`).
  2. Run ONE command. It renders the wide video, cuts it into Shorts, posts the wide video now and
     schedules the Shorts 3 hours apart:
     ```bash
     ~/.openclaw/venv-media/bin/python ~/.openclaw/workspace-minitoon/skills/minitoon-daily-telegram/publish_day.py \
       ~/.openclaw/workspace-minitoon/output/daily/<YYYY-MM-DD>/episode.json \
       --title "<title>" --description "<description>" --tags "<tag1,tag2,...>" --shorts 4
     ```
  3. Reply with the title, the main video link, and the Shorts with their scheduled times.
  If it prints FAILED, reply with the error. Never run it twice for the same day unless the user
  asks (it refuses anyway once the episode is posted).

## Rules
- Keep Telegram messages short apart from the prompts and lyrics.
- Kid-safe content only (ages 3-8).
