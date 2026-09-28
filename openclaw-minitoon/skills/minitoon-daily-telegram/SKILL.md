---
name: "minitoon-daily-telegram"
description: "Daily Minitoon workflow on Telegram: the specialist team pitches a song episode at 8 AM; you collect the user's pictures and Suno song, run the team to make and post the wide video plus catchy Shorts, and pass the user's feedback to the right specialist. Use whenever the user sends pictures, a song, feedback, 'new idea', 'go', or asks about today's episode."
---

# Minitoon daily workflow (producer)

Every episode is a SONG video (like Cocomelon). The user makes the pictures (Gemini app) and the song
(Suno Pro) by hand. The specialist team does the writing, run by `team.py`:
- Story Writer (`minitoon-story-agent`), Songwriter (`minitoon-audio-agent`),
  Picture Director (`minitoon-visual-agent`), Quality Checker (`minitoon-quality-agent`),
  YouTube Manager (`minitoon-youtube-agent`). Each follows its own SOUL.md + LEARNINGS.md.
NEVER write stories, lyrics, prompts or YouTube text yourself, and never generate pictures or music with your tools.

TEAM = `python3 ~/.openclaw/workspace-minitoon/skills/minitoon-daily-telegram/team.py`
Today's folder: `~/.openclaw/workspace-minitoon/output/daily/<YYYY-MM-DD>/` (its `episode.json` is the source of truth)

## The morning pitch
Runs automatically at 8 AM (`TEAM pitch`), which sends the user the intro, the Suno style, the Suno lyrics
and 7 picture prompts as separate messages. If the user says "new idea", or no pitch arrived, run
`TEAM pitch` yourself (takes about 2 minutes), then reply only "New pitch sent ✅".

## When the user sends things
- Pictures → save them in today's folder as `01.jpg` ... `07.jpg` and set `image_file` on the matching
  scene in `episode.json`. Reply briefly: "Got 3 of 7 ✅". Out of order or extras: match each scene to the
  picture that best shows it (compare with each scene's `lyrics` and `image`), skip near-duplicates, and
  say the mapping in one line.
- An audio file (MP3/M4A/WAV from Suno) → copy it to today's folder as `song.mp3`, set `"song_file"` to
  its full path in `episode.json`. Reply "Got the song 🎵". If they send two, use the last one.
- All 7 pictures in (and the song, or the user says "go" / "no song") →
  reply "🎬 Making the video now, about 15-20 minutes", then run `TEAM publish` (it writes the YouTube text,
  has it checked, renders the wide video to the song's exact length, cuts 4 chorus Shorts, posts the wide
  video and schedules the Shorts 3 hours apart). Then reply with the title, the main video link, and the
  Shorts with their times. If it prints FAILED, reply with that error in plain words.

## Feedback trains the team
When the user comments on the story, song, pictures or YouTube text ("the song was boring", "Bunny's ears
looked wrong", "love this title"), thank them, then append one dated rule to the right specialist's notebook:
- story → `~/.openclaw/workspace-minitoon-story-agent/LEARNINGS.md`
- song → `~/.openclaw/workspace-minitoon-audio-agent/LEARNINGS.md`
- pictures → `~/.openclaw/workspace-minitoon-visual-agent/LEARNINGS.md`
- YouTube text → `~/.openclaw/workspace-minitoon-youtube-agent/LEARNINGS.md`
- something unsafe or wrong that slipped through → `~/.openclaw/workspace-minitoon-quality-agent/LEARNINGS.md`
Format: `- 2026-09-28: <what the user said> → <the rule to follow from now on>`.
Tell the user which specialist learned it.

## Rules
- Keep your messages short. Kid-safe only (ages 3-8). Never post twice in a day unless the user asks.
