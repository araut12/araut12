# Minitoon: OpenClaw daily kids' video pipeline

A daily YouTube Shorts episode for the @MiniToons channel, run by OpenClaw agents and made with free tools.

## Daily flow

1. **8:00 AM (Perth):** the `minitoon-producer` agent pitches the day's story on Telegram
   (@sushan_video_bot), with 7 ready-to-paste Gemini picture prompts.
2. **You:** make the pictures in the Gemini app and send them to the bot.
3. **Bot:** renders the video, uploads it publicly to YouTube (Made for Kids) and replies with the link.

## What's here

| Path | Purpose |
|---|---|
| `skills/minitoon-daily-telegram/` | The Telegram workflow: pitch, collect pictures, render, upload |
| `skills/minitoon-render/` | `render.py` builds the MP4: fits pictures to 9:16, edge-tts voice, Wan 2.2 animation (free Hugging Face Space), ACE-Step music (free HF Space) with MusicGen-small fallback (`make_music.py`), ffmpeg assembly |
| `skills/minitoon-youtube-upload/` | `youtube_upload.py` uploads a Short (YouTube Data API) |
| `characters/CHARACTERS.md` | Character bible used in prompts |

## Restore on a fresh OpenClaw (inside WSL)

```bash
# 1. skills
cp -r skills/* ~/.openclaw/workspace-minitoon/skills/
mkdir -p ~/.openclaw/workspace-minitoon/characters && cp characters/CHARACTERS.md ~/.openclaw/workspace-minitoon/characters/

# 2. Python environments
python3 -m venv ~/.openclaw/venv-media
~/.openclaw/venv-media/bin/pip install gradio_client edge-tts transformers scipy
~/.openclaw/venv-media/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
python3 -m venv ~/.openclaw/venv-youtube
~/.openclaw/venv-youtube/bin/pip install google-api-python-client google-auth-oauthlib
sudo apt install ffmpeg

# 3. secrets (never commit these), in ~/.openclaw/secrets/ with chmod 600:
#    gemini_key                  - aistudio.google.com/apikey (free)
#    hf_token                    - huggingface.co/settings/tokens, type Read (free)
#    youtube_client_secret.json  - Google Cloud OAuth "Desktop app" client
~/.openclaw/venv-youtube/bin/python ~/.openclaw/workspace-minitoon/skills/minitoon-youtube-upload/youtube_upload.py --login

# 4. OpenClaw config
cat ~/.openclaw/secrets/gemini_key | openclaw models auth paste-api-key --provider google
#    In openclaw.json:
#    - models.providers.google = {baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
#      api: "openai-completions", models: [{id: "gemini-3.5-flash", ...}]}
#    - every minitoon agent: model "google/gemini-3.5-flash",
#      tools.deny ["image_generate","video_generate","music_generate"]
#    - minitoon-producer skills add: minitoon-render, minitoon-youtube-upload, minitoon-daily-telegram
openclaw agents bind --agent minitoon-producer --bind telegram
openclaw cron add --name "Minitoon morning pitch" --agent minitoon-producer --cron "0 8 * * *" \
  --tz Australia/Perth --session isolated --timeout-seconds 900 --announce --channel telegram \
  --to <your telegram chat id> \
  --message "Use the minitoon-daily-telegram skill, part A: pitch todays Minitoon episode to the user on Telegram (idea + 7 Gemini picture prompts)."
```

## Free-tier limits

- Hugging Face ZeroGPU (free account): about 5-6 animated scenes plus one ACE-Step song a day.
  Music is made first so it gets the quota. Anything over the limit falls back to zoom motion or MusicGen.
- The Gemini API free tier has no image quota. That's why pictures are made by hand in the Gemini app.
  Set `MINITOON_GEMINI_IMAGES=1` after enabling billing to generate them automatically.
- The Google OAuth app must be **Published** (not Testing), or the YouTube sign-in expires every 7 days.
