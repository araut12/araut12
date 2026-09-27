---
name: "minitoon-render"
description: "Actually render a finished Minitoon episode to a vertical MP4 (YouTube Shorts) with free tools: Gemini 3D-cartoon pictures that stay on-model, AI animation, narration and a catchy AI song. Use after the story is approved, or when asked to make/render the video."
---

# Minitoon Render (free)

Turns an approved story into a real video file. Costs nothing.

## Steps

1. Read `~/.openclaw/workspace-minitoon/characters/CHARACTERS.md`. Use the existing characters
   (Bunny is the star) unless the user asks for someone new.
2. Write `episode.json` in your workspace `output/` folder:
   ```json
   {
     "title": "Bunny Learns to Share",
     "character_refs": ["~/.openclaw/workspace-minitoon/characters/samples/sample-04.jpg",
                        "~/.openclaw/workspace-minitoon/characters/samples/sample-07.jpg"],
     "voice": "en-US-AnaNeural",
     "music": "children's music, cheerful, catchy, bouncy, ukulele, glockenspiel, claps, whistling, happy, upbeat, 120 bpm",
     "scenes": [
       {"image": "Bunny waves hello in front of the pink cottage, morning sun, flowers everywhere",
        "narration": "Good morning! It's a sunny day, and Bunny can't wait to play!",
        "motion": "Bunny waves and bounces happily, ears wiggling",
        "animate": true}
     ]
   }
   ```
   - 7-10 scenes, 1-2 short, lively sentences each (total 35-55 seconds). Open with a hook in scene 1
     (a question or a surprise) and end with a happy lesson plus "See you next time!".
   - `image`: describe the action and the place. The character's look comes from `character_refs`.
   - `motion`: one clear action (wave, jump, hug, splash, twirl, laugh). Mark the 4-6 most lively
     scenes `"animate": true`.
   - `music`: comma-separated tags for the mood. Keep it instrumental and catchy (it plays under the voice).
   - Kid-safe only: nothing scary or violent, no real brands, no text in images.
   - Voices: `en-US-AnaNeural` (child, default), `en-US-JennyNeural` (warm woman), `en-GB-SoniaNeural`.
3. Run (takes 5-15 minutes):
   ```bash
   ~/.openclaw/venv-media/bin/python ~/.openclaw/workspace-minitoon/skills/minitoon-render/render.py output/episode.json
   ```
4. The last line printed is the MP4 path. Report it, with the title, scene count, and the
   "done:" line (Gemini images, animated scenes, length). If it fails, retry once, then report the error.
