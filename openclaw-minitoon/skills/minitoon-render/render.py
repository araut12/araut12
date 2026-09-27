#!/usr/bin/env python3
"""Render a Minitoon episode to a vertical MP4 (YouTube Shorts) with free tools.

Pictures:  Gemini image model (free tier, keeps the character consistent with reference
           images); falls back to Pollinations.ai.
Animation: Wan 2.2 on a free Hugging Face Space; falls back to gentle zoom/pan.
Voice:     edge-tts.
Music:     ACE-Step on a free Hugging Face Space; falls back to MusicGen-small on this PC.
Assembly:  ffmpeg.

Keys (optional but recommended), one per file:
  ~/.openclaw/secrets/gemini_key   ~/.openclaw/secrets/hf_token

Usage: render.py episode.json      (prints the final .mp4 path)
"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

W, H, FPS = 1080, 1920, 30
HERE = Path(__file__).resolve().parent
VENV = Path.home() / ".openclaw/venv-media/bin"
SECRETS = Path.home() / ".openclaw/secrets"
OUT_ROOT = Path.home() / ".openclaw/workspace-minitoon/output/videos"
IMAGE_MODEL = os.getenv("MINITOON_IMAGE_MODEL", "gemini-2.5-flash-image")
WAN_SPACE = "zerogpu-aoti/wan2-2-fp8da-aoti-faster"
ACE_SPACE = "ACE-Step/ACE-Step"
DEFAULT_STYLE = ("3D Pixar-style animation, cute chibi proportions, big expressive eyes, soft fluffy "
                 "textures, bright saturated colors, warm sunny lighting, cozy detailed background, "
                 "child-friendly, no text")
DEFAULT_MUSIC = "children's music, cheerful, catchy, bouncy, ukulele, glockenspiel, claps, whistling, happy, upbeat, 120 bpm"


def secret(name: str, env: str) -> str | None:
    f = SECRETS / name
    return os.getenv(env) or (f.read_text().strip() if f.exists() else None)


GEMINI_KEY = secret("gemini_key", "GEMINI_API_KEY")
HF_TOKEN = secret("hf_token", "HF_TOKEN")
MAX_ANIMATED = int(os.getenv("MINITOON_MAX_ANIMATED", "6" if HF_TOKEN else "2"))


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "episode"


def run(*cmd: str) -> None:
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, cmd[:2], result.stdout,
                                            result.stderr.decode(errors="replace")[-500:])


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


# ---------- pictures ----------

def gemini_image(prompt: str, refs: list[Path], dest: Path) -> bool:
    # The free Gemini API tier has no image quota; turn this on once billing is enabled.
    if not GEMINI_KEY or os.getenv("MINITOON_GEMINI_IMAGES", "0") != "1":
        return False
    parts = [{"inline_data": {"mime_type": "image/png" if r.suffix == ".png" else "image/jpeg",
                              "data": base64.b64encode(r.read_bytes()).decode()}} for r in refs[:3]]
    if refs:
        prompt = ("Keep the main character EXACTLY as in the reference image(s): same face, colors, "
                  "outfit and proportions. New scene: " + prompt)
    parts.append({"text": prompt})
    body = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "9:16"}},
    }).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{IMAGE_MODEL}:generateContent"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json", "x-goog-api-key": GEMINI_KEY})
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.load(r)
            for part in data["candidates"][0]["content"]["parts"]:
                inline = part.get("inline_data") or part.get("inlineData")
                if inline:
                    dest.write_bytes(base64.b64decode(inline["data"]))
                    return True
            log("  gemini returned no image")
        except urllib.error.HTTPError as e:
            log(f"  gemini error {e.code}: {e.read()[:200]!r}")
            if e.code in (400, 403, 404):
                return False
        except Exception as e:
            log(f"  gemini error: {e}")
        time.sleep(10 * (attempt + 1))
    return False


def pollinations_image(prompt: str, seed: int, dest: Path) -> None:
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt) + \
        f"?width=720&height=1280&nologo=true&seed={seed}"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                data = r.read()
            if len(data) > 5000:
                dest.write_bytes(data)
                return
        except Exception as e:
            log(f"  pollinations retry {attempt + 1}: {e}")
        time.sleep(5 * (attempt + 1))
    raise SystemExit(f"Could not generate image for: {prompt}")


def make_vertical(src: Path, dest: Path) -> None:
    """Fit any picture into 1080x1920. Wide pictures sit on a blurred copy of themselves."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", str(src)],
                         capture_output=True, text=True, check=True)
    w, h = (int(x) for x in out.stdout.strip().split(",")[:2])
    if w / h <= 0.7:
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
        run("ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", vf, "-frames:v", "1", str(dest))
    else:
        # Wide picture: zoom it in a bit so the character fills more of the tall frame.
        fg_w = int(W * 1.45)
        run("ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-filter_complex",
            f"[0]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:2,eq=brightness=-0.05[bg];"
            f"[0]scale={fg_w}:-2,crop={W}:ih[fg];[bg][fg]overlay=0:(H-h)/2",
            "-frames:v", "1", str(dest))


# ---------- animation ----------

def animate(img: Path, motion: str, seconds: float, dest: Path) -> bool:
    try:
        from gradio_client import Client, handle_file
        client = Client(WAN_SPACE, token=HF_TOKEN, verbose=False)
        result = client.predict(
            input_image=handle_file(str(img)),
            prompt=f"{motion}, smooth Pixar-style 3D cartoon animation, expressive, gentle camera motion",
            steps=4, negative_prompt="scary, distorted face, extra limbs, blurry, text, watermark, static",
            duration_seconds=max(2.0, min(5.0, seconds)),
            guidance_scale=1, guidance_scale_2=1, seed=42, randomize_seed=False,
            api_name="/generate_video")
        path = result[0] if isinstance(result, (list, tuple)) else result
        path = path["video"] if isinstance(path, dict) else path
        shutil.copy(path, dest)
        return True
    except Exception as e:
        log(f"  animation unavailable, using zoom instead: {str(e)[:160]}")
        return False


# ---------- music ----------

def ace_music(prompt: str, lyrics: str, seconds: float, dest: Path) -> bool:
    try:
        from gradio_client import Client
        client = Client(ACE_SPACE, token=HF_TOKEN, verbose=False)
        result = client.predict(
            audio_duration=round(seconds), prompt=prompt, lyrics=lyrics or "[instrumental]",
            infer_step=60, guidance_scale=15, scheduler_type="euler", cfg_type="apg",
            omega_scale=10, manual_seeds=None, guidance_interval=0.5, guidance_interval_decay=0,
            min_guidance_scale=3, use_erg_tag=True, use_erg_lyric=False, use_erg_diffusion=True,
            oss_steps=None, guidance_scale_text=0, guidance_scale_lyric=0,
            audio2audio_enable=False, ref_audio_strength=0.5, ref_audio_input=None,
            lora_name_or_path="none", api_name="/__call__")
        path = result[0] if isinstance(result, (list, tuple)) else result
        run("ffmpeg", "-y", "-loglevel", "error", "-i", str(path), str(dest))
        return True
    except Exception as e:
        log(f"  ACE-Step unavailable, using local MusicGen: {str(e)[:160]}")
        return False


def make_music(spec: dict, seconds: float, dest: Path) -> bool:
    prompt = spec.get("music", DEFAULT_MUSIC)
    if ace_music(prompt, spec.get("song_lyrics", ""), seconds, dest):
        return True
    try:
        run(str(VENV / "python"), str(HERE / "make_music.py"), prompt, str(dest), str(min(30.0, seconds)))
        return True
    except subprocess.CalledProcessError as e:
        log(f"  music failed: {(e.stderr or b'')[-200:]!r}")
        return False


# ---------- assembly ----------

def make_clip(i: int, img: Path, audio: Path, anim: Path | None, clip: Path) -> None:
    length = duration(audio) + 0.6
    fade = f"fade=t=in:st=0:d=0.25,fade=t=out:st={length - 0.25:.2f}:d=0.25,format=yuv420p"
    if anim:
        # Play the animation, slowed a little if the narration is longer, then hold the last frame.
        speed = min(1.6, max(1.0, length / max(0.5, duration(anim))))
        vf = (f"setpts={speed:.3f}*PTS,fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H},tpad=stop_mode=clone:stop_duration={length:.2f},{fade}")
        video_in = ["-i", str(anim)]
    else:
        frames = int(length * FPS)
        zoom = "min(zoom+0.0009,1.15)" if i % 2 else "if(eq(on,0),1.15,max(zoom-0.0009,1.0))"
        vf = (f"scale={W * 3 // 2}:{H * 3 // 2},zoompan=z='{zoom}':d={frames}"
              f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},{fade}")
        video_in = ["-loop", "1", "-i", str(img)]
    run("ffmpeg", "-y", "-loglevel", "error", *video_in, "-i", str(audio),
        "-map", "0:v", "-map", "1:a", "-vf", vf, "-af", "apad", "-t", f"{length:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", str(clip))


def main() -> None:
    spec = json.loads(Path(sys.argv[1]).read_text())
    style = spec.get("style", DEFAULT_STYLE)
    voice = spec.get("voice", "en-US-AnaNeural")
    scenes = spec["scenes"]
    work = OUT_ROOT / f"{time.strftime('%Y%m%d-%H%M%S')}-{slug(spec['title'])}"
    work.mkdir(parents=True, exist_ok=True)
    log(f"gemini images: {'on' if GEMINI_KEY else 'off (no key)'}, hf token: {'yes' if HF_TOKEN else 'no'}, "
        f"animating up to {MAX_ANIMATED} scenes")

    refs = [Path(p).expanduser() for p in spec.get("character_refs", []) if Path(p).expanduser().exists()]
    wanted = [i for i, s in enumerate(scenes) if s.get("animate")] or list(range(len(scenes)))
    to_animate = set(wanted[:MAX_ANIMATED])

    gemini_used = 0
    for i, scene in enumerate(scenes):
        n = i + 1
        img, audio = work / f"s{n:02d}.png", work / f"s{n:02d}.mp3"
        log(f"scene {n}/{len(scenes)}: picture + voice")
        raw = work / f"s{n:02d}-raw.png"
        prompt = f"{scene['image']}. Style: {style}. Vertical 9:16 composition, character centered."
        given = Path(scene["image_file"]).expanduser() if scene.get("image_file") else None
        if given and given.exists():
            shutil.copy(given, raw)  # picture supplied by the user (e.g. made in the Gemini app)
        elif gemini_image(prompt, refs, raw):
            gemini_used += 1
            if not refs:
                refs = [raw]  # first scene becomes the character reference for the rest
        else:
            pollinations_image(prompt, seed=1000 + n, dest=raw)
        make_vertical(raw, img)
        run(str(VENV / "edge-tts"), "--voice", voice, f"--rate={spec.get('voice_rate', '-5%')}",
            f"--pitch={spec.get('voice_pitch', '+5Hz')}", "--text", scene["narration"], "--write-media", str(audio))

    # Music first: it gets the free GPU quota before animation uses up the rest.
    estimate = sum(duration(work / f"s{i + 1:02d}.mp3") + 0.6 for i in range(len(scenes)))
    music = work / "music.wav"
    log("music")
    have_music = make_music(spec, estimate + 1, music)

    clips, animated = [], 0
    for i, scene in enumerate(scenes):
        n = i + 1
        img, audio = work / f"s{n:02d}.png", work / f"s{n:02d}.mp3"
        anim, clip = work / f"s{n:02d}-anim.mp4", work / f"s{n:02d}.mp4"
        log(f"scene {n}/{len(scenes)}: motion")
        ok = i in to_animate and animate(img, scene.get("motion", scene["image"]), duration(audio), anim)
        animated += ok
        make_clip(n, img, audio, anim if ok else None, clip)
        clips.append(clip)

    listing = work / "clips.txt"
    listing.write_text("".join(f"file '{c.name}'\n" for c in clips))
    joined = work / "joined.mp4"
    run("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", str(listing), "-c", "copy", str(joined))
    total = duration(joined)

    final = work / f"{slug(spec['title'])}.mp4"
    if have_music:
        # Music ducks under the narration and comes up between lines; fades out at the end.
        run("ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), "-stream_loop", "-1", "-i", str(music),
            "-filter_complex",
            "[0:a]asplit=2[voice][key];"
            f"[1:a]volume=0.55,afade=t=out:st={max(0, total - 2):.2f}:d=2[m];"
            "[m][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[ducked];"
            "[voice][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
            "loudnorm=I=-14:TP=-1.5:LRA=11[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", f"{total:.2f}", "-movflags", "+faststart", str(final))
    else:
        shutil.copy(joined, final)

    (work / "episode.json").write_text(json.dumps(spec, indent=2))
    log(f"done: {len(scenes)} scenes, {gemini_used} Gemini images, {animated} animated, {total:.0f}s")
    print(final)


if __name__ == "__main__":
    main()
