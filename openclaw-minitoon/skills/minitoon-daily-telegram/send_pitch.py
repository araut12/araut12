#!/usr/bin/env python3
"""Send today's pitch to Telegram as separate, copy-ready messages.

Order: intro, Suno style, Suno lyrics, then one message per Gemini picture prompt, then a closing note.
Each copyable message contains ONLY the text to paste.

Usage: send_pitch.py EPISODE.json [--dry-run]
"""
import argparse
import json
import subprocess
import time
from pathlib import Path

CHAT_FILE = Path.home() / ".openclaw/secrets/telegram_chat_id"


def send(chat: str, text: str, dry: bool) -> None:
    if dry:
        print(f"--- message ---\n{text}\n")
        return
    r = subprocess.run(["openclaw", "message", "send", "--channel", "telegram", "-t", chat, "-m", text],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"FAILED to send: {(r.stderr or r.stdout)[-300:]}")
    time.sleep(1.2)  # keep the order and stay under Telegram's rate limits


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("episode")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    ep = json.loads(Path(a.episode).expanduser().read_text())
    chat = CHAT_FILE.read_text().strip()
    prompts = [s.get("gemini_prompt") or s["image"] for s in ep["scenes"]]
    n = len(prompts)

    send(chat, f"🐰 Today's song: {ep['title']}\n{ep.get('summary', '')}\n\n"
               f"Next messages, each ready to copy:\n"
               f"🎵 1 Suno style  •  🎵 2 Suno lyrics  •  🎨 {n} Gemini picture prompts (in order)", a.dry_run)
    send(chat, ep["song_style"], a.dry_run)
    send(chat, ep["song_lyrics"], a.dry_run)
    for prompt in prompts:
        send(chat, prompt, a.dry_run)
    send(chat, f"✅ That's all {n} prompts. Send me the {n} pictures in order, plus the Suno MP3.\n"
               f"No MP3? I'll sing it myself. Reply \"new idea\" for a different story.", a.dry_run)
    print(f"sent {n + 4} messages")


if __name__ == "__main__":
    main()
