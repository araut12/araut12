#!/usr/bin/env python3
"""The Minitoon specialist team, coordinated by code instead of by an AI producer.

Each specialist is one Gemini request whose instructions are that agent's own SOUL.md + LEARNINGS.md
(from its OpenClaw workspace), so feedback written to LEARNINGS.md changes how it works next time.
Every answer is parsed and checked. If something is missing, the step is retried, and if it's still
wrong the run stops with an error. Nothing is ever invented.

  team.py pitch   [--date YYYY-MM-DD] [--dry-run]   story -> song -> pictures -> quality check -> episode.json -> Telegram
  team.py publish [--date YYYY-MM-DD] [--dry-run]   YouTube text -> quality check -> wide video + Shorts -> Telegram
"""
import argparse
import glob
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

HOME = Path.home() / ".openclaw"
DAILY = HOME / "workspace-minitoon/output/daily"
SKILLS = HOME / "workspace-minitoon/skills"
CHARACTERS = HOME / "workspace-minitoon/characters/CHARACTERS.md"
KEY = (HOME / "secrets/gemini_key").read_text().strip()
MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
AGENTS = {"story": "minitoon-story-agent", "song": "minitoon-audio-agent", "pictures": "minitoon-visual-agent",
          "quality": "minitoon-quality-agent", "youtube": "minitoon-youtube-agent"}
PROMPT_PREFIX = ("Use the attached bunny as the character, keep her exactly the same. "
                 "Wide 16:9 landscape image, character in the center, 3D Pixar style: ")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def instructions(role: str) -> str:
    ws = HOME / f"workspace-{AGENTS[role]}"
    parts = [(ws / "SOUL.md").read_text()]
    if (ws / "LEARNINGS.md").exists():
        parts.append("## Your LEARNINGS.md (rules from past feedback; they override your defaults)\n"
                     + (ws / "LEARNINGS.md").read_text())
    parts.append("You have no tools in this conversation: everything you need is in the message. "
                 "Reply ONLY in your delivery format.")
    return "\n\n".join(parts)


def gemini(system: str, user: str, temperature: float) -> str:
    body = json.dumps({"system_instruction": {"parts": [{"text": system}]},
                       "contents": [{"role": "user", "parts": [{"text": user}]}],
                       "generationConfig": {"temperature": temperature}}).encode()
    last = ""
    for attempt in range(8):
        model = MODELS[attempt % len(MODELS)]
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=body, headers={"Content-Type": "application/json", "x-goog-api-key": KEY})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.load(r)
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"]).strip()
        except urllib.error.HTTPError as e:
            last = f"{model}: HTTP {e.code} {e.read()[:160]!r}"
        except Exception as e:  # network hiccup or empty answer
            last = f"{model}: {e}"
        log(f"    retry ({last[:120]})")
        time.sleep(8 * (attempt + 1))
    raise SystemExit(f"FAILED: Gemini unavailable ({last})")


def ask(role: str, task: str, parse, temperature: float = 0.9):
    """Ask a specialist; retry once if the answer isn't in its delivery format."""
    for attempt in range(2):
        log(f"  {role} ...")
        time.sleep(4)  # stay under the free tier's requests-per-minute limit
        text = gemini(instructions(role), task, temperature)
        try:
            return parse(text)
        except ValueError as e:
            log(f"    {role} answer not usable ({e}), asking again")
            task += f"\n\nYour last answer was not usable: {e}. Reply ONLY in the exact delivery format."
    raise SystemExit(f"FAILED: {role} specialist did not deliver a usable answer")


# ---------- parsers ----------

def field(text: str, name: str, until: str | None = None) -> str:
    pat = rf"^{name}:\s*(.*?)" + (rf"(?=^{until}:)" if until else r"\Z")
    m = re.search(pat, text, re.S | re.M | re.I)
    if not m or not m.group(1).strip():
        raise ValueError(f"missing {name}")
    return m.group(1).strip()


def numbered(text: str, n: int = 7) -> list[str]:
    items = re.split(r"^\s*\**(\d+)[.)]\**\s*", text, flags=re.M)
    out = {int(items[i]): items[i + 1].strip() for i in range(1, len(items) - 1, 2)}
    got = [out.get(k, "") for k in range(1, n + 1)]
    if not all(got):
        raise ValueError(f"expected {n} numbered items, got {len([g for g in got if g])}")
    return got


def parse_story(text: str) -> dict:
    scenes = []
    for item in numbered(field(text, "SCENES")):
        parts = dict((k.strip().upper(), v.strip()) for k, v in
                     (p.split(":", 1) for p in item.split("|") if ":" in p))
        if "ACTION" not in parts:
            raise ValueError("scene without ACTION")
        scenes.append(parts)
    return {"title": field(text, "TITLE").splitlines()[0], "summary": field(text, "SUMMARY").splitlines()[0],
            "lesson": field(text, "LESSON").splitlines()[0], "scenes": scenes}


def parse_song(text: str) -> dict:
    lyrics = field(text, "LYRICS", "SCENE_LYRICS")
    if "[chorus]" not in lyrics.lower():
        raise ValueError("lyrics have no [chorus]")
    secs = re.search(r"\d+", field(text, "SONG_SECONDS"))
    return {"song_style": field(text, "SONG_STYLE").splitlines()[0], "song_lyrics": lyrics,
            "song_seconds": int(secs.group()) if secs else 75,
            "scene_lyrics": numbered(field(text, "SCENE_LYRICS"))}


def parse_prompts(text: str) -> list[str]:
    prompts = numbered(text)
    return [p if p.startswith("Use the attached bunny") else PROMPT_PREFIX + p for p in prompts]


def parse_quality(text: str) -> list[tuple[str, str]]:
    if re.search(r"VERDICT:\s*PASS", text, re.I):
        return []
    if not re.search(r"VERDICT:\s*FIX", text, re.I):
        raise ValueError("no VERDICT line")
    fixes = re.findall(r"^\s*-\s*(story|song|pictures|youtube)\s*[-:]\s*(.+)$", text, re.M | re.I)
    return [(a.lower(), b.strip()) for a, b in fixes] or [("story", text[-300:])]


def parse_youtube(text: str) -> dict:
    return {"title": field(text, "TITLE").splitlines()[0][:100],
            "description": field(text, "DESCRIPTION", "TAGS"),
            "tags": field(text, "TAGS").splitlines()[0]}


# ---------- steps ----------

def past_titles() -> list[str]:
    out = []
    for f in sorted(glob.glob(str(DAILY / "*/episode.json"))):
        try:
            out.append(json.loads(Path(f).read_text())["title"])
        except Exception:
            pass
    return out


def story_task(extra: str = "") -> str:
    return (f"Write today's episode story.\n\n## Characters\n{CHARACTERS.read_text()}\n\n"
            f"## Past titles (never repeat these ideas)\n" + "\n".join(f"- {t}" for t in past_titles()) + extra)


def story_text(s: dict) -> str:
    lines = [f"TITLE: {s['title']}", f"SUMMARY: {s['summary']}", f"LESSON: {s['lesson']}", "SCENES:"]
    lines += [f"{i}. " + " | ".join(f"{k}: {v}" for k, v in sc.items()) for i, sc in enumerate(s["scenes"], 1)]
    return "\n".join(lines)


def song_task(s: dict, extra: str = "") -> str:
    return f"Write the song for this story.\n\n{story_text(s)}{extra}"


def pictures_task(s: dict, song: dict, extra: str = "") -> str:
    lyr = "\n".join(f"{i}. {l}" for i, l in enumerate(song["scene_lyrics"], 1))
    return (f"Write the 7 Gemini prompts.\n\n## Characters\n{CHARACTERS.read_text()}\n\n## Story\n{story_text(s)}"
            f"\n\n## Scene lyrics\n{lyr}{extra}")


def package_text(s: dict, song: dict, prompts: list[str]) -> str:
    return (f"## Story\n{story_text(s)}\n\n## Song\nSTYLE: {song['song_style']}\n{song['song_lyrics']}\n\n"
            "## Scene lyrics\n" + "\n".join(f"{i}. {l}" for i, l in enumerate(song["scene_lyrics"], 1)) +
            "\n\n## Picture prompts\n" + "\n".join(f"{i}. {p}" for i, p in enumerate(prompts, 1)) +
            "\n\n## Past titles\n" + "\n".join(past_titles()))


def pitch(day: str, dry: bool) -> None:
    folder = DAILY / day
    ep_path = folder / "episode.json"
    if ep_path.exists() and json.loads(ep_path.read_text()).get("status") in ("rendering", "posted"):
        raise SystemExit(f"FAILED: {day} is already {json.loads(ep_path.read_text())['status']}")
    log(f"pitch for {day}")
    s = ask("story", story_task(), parse_story)
    song = ask("song", song_task(s), parse_song)
    prompts = ask("pictures", pictures_task(s, song), parse_prompts)

    fixes = ask("quality", "Check this package.\n\n" + package_text(s, song, prompts), parse_quality, 0.2)
    if fixes:
        log(f"  quality asked for {len(fixes)} fix(es): {fixes}")
        notes = {}
        for who, what in fixes:
            notes.setdefault(who, []).append(what)
        fix = lambda who: "\n\n## Fix requested by the Quality Checker\n" + "\n".join(f"- {n}" for n in notes[who])
        if "story" in notes:
            s = ask("story", story_task(fix("story")), parse_story)
        if "story" in notes or "song" in notes:
            song = ask("song", song_task(s, fix("song") if "song" in notes else ""), parse_song)
        if notes.keys() & {"story", "song", "pictures"}:
            prompts = ask("pictures", pictures_task(s, song, fix("pictures") if "pictures" in notes else ""),
                          parse_prompts)

    ep = {"title": s["title"], "summary": s["summary"], "lesson": s["lesson"], "status": "waiting_for_pictures",
          "song_style": song["song_style"], "song_lyrics": song["song_lyrics"], "song_seconds": song["song_seconds"],
          "quality_fixes": [f"{a}: {b}" for a, b in fixes],
          "scenes": [{"image": f"{sc.get('ACTION', '')} at {sc.get('PLACE', '')}", "gemini_prompt": prompts[i],
                      "lyrics": song["scene_lyrics"][i], "narration": song["scene_lyrics"][i],
                      # every scene wants motion; the renderer animates as many as the free quota allows
                      "motion": sc.get("MOTION", sc.get("ACTION", "")), "animate": True}
                     for i, sc in enumerate(s["scenes"])]}
    folder.mkdir(parents=True, exist_ok=True)
    ep_path.write_text(json.dumps(ep, indent=2))
    log(f"saved {ep_path}")
    cmd = ["python3", str(SKILLS / "minitoon-daily-telegram/send_pitch.py"), str(ep_path)] + (["--dry-run"] if dry else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout[-4000:] if dry else r.stdout.strip())
    if r.returncode:
        raise SystemExit(f"FAILED: sending the pitch: {r.stderr[-300:]}")
    print(f"Pitch {'prepared' if dry else 'sent'} ✅ {ep['title']}")


def publish(day: str, dry: bool) -> None:
    ep_path = DAILY / day / "episode.json"
    ep = json.loads(ep_path.read_text())
    missing = [i + 1 for i, s in enumerate(ep["scenes"]) if not Path(s.get("image_file") or "/none").exists()]
    if missing:
        raise SystemExit(f"FAILED: pictures missing for scenes {missing}")
    task = (f"Write the YouTube text for today's episode.\n\nTITLE IDEA: {ep['title']}\nSUMMARY: {ep['summary']}\n"
            f"LESSON: {ep.get('lesson', '')}\n\nLYRICS:\n{ep.get('song_lyrics', '')}")
    yt = ask("youtube", task, parse_youtube)
    fixes = ask("quality", "Check this YouTube text for a Made for Kids channel.\n\n"
                f"TITLE: {yt['title']}\nDESCRIPTION: {yt['description']}\nTAGS: {yt['tags']}", parse_quality, 0.2)
    if fixes:
        yt = ask("youtube", task + "\n\n## Fix requested by the Quality Checker\n" +
                 "\n".join(f"- {b}" for _, b in fixes), parse_youtube)
    cmd = [str(HOME / "venv-media/bin/python"), str(SKILLS / "minitoon-daily-telegram/publish_day.py"), str(ep_path),
           "--title", yt["title"], "--description", yt["description"], "--tags", yt["tags"], "--shorts", "4"]
    if dry:
        cmd.append("--dry-run")
    log("rendering and posting (10-20 minutes)")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"FAILED: {r.stdout[-300:]} {r.stderr[-500:]}")
    result = json.loads(r.stdout[r.stdout.index("{"):])
    log_file = HOME / f"workspace-{AGENTS['youtube']}/memory/channel-log.md"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if not dry:
        with log_file.open("a") as f:
            f.write(f"{day} | {yt['title']} | {result.get('wide')} | {'; '.join(result.get('shorts', []))}\n")
    print(json.dumps({"title": yt["title"], **result}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=["pitch", "publish"])
    p.add_argument("--date", default=date.today().isoformat())
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    (pitch if a.step == "pitch" else publish)(a.date, a.dry_run)
