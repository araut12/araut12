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

Usage: render.py episode.json [--format 16:9] [--reuse EARLIER_RENDER_DIR]
       (prints the final .mp4 path)
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
ASPECT = "9:16"
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
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": ASPECT}},
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


def dims(path: Path) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    w, h = (int(x) for x in out.stdout.strip().split(",")[:2])
    return w, h


def fit_graph(src: Path, pre: str = "") -> str:
    """filter_complex that fits src into the W x H frame, ending in [v].

    Same shape: fill and crop. Otherwise the picture sits on a blurred copy of itself.
    """
    w, h = dims(src)
    head = f"[0:v]{pre + ',' if pre else ''}"
    if abs(w / h - W / H) < 0.15 * (W / H):
        return f"{head}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[v]"
    bg = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:2,eq=brightness=-0.05"
    if w / h > W / H:
        # Wide picture in a tall frame: zoom in a bit so the character fills more of it.
        fg = f"scale={int(W * 1.45)}:-2,crop={W}:ih"
        pos = "0:(H-h)/2"
    else:
        # Tall picture in a wide frame: full height, centered.
        fg = f"scale=-2:{H}"
        pos = "(W-w)/2:0"
    return f"{head}split[a][b];[a]{bg}[bg];[b]{fg}[fg];[bg][fg]overlay={pos}[v]"


def fit_frame(src: Path, dest: Path) -> None:
    run("ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-filter_complex", fit_graph(src),
        "-map", "[v]", "-frames:v", "1", str(dest))


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




def get_song(spec: dict, dest: Path) -> bool:
    """Whole-video song: the user's MP3 (e.g. from Suno), else ACE-Step sings `song_lyrics`."""
    given = Path(spec["song_file"]).expanduser() if spec.get("song_file") else None
    if given and given.exists():
        run("ffmpeg", "-y", "-loglevel", "error", "-i", str(given), "-ac", "2", "-ar", "44100", str(dest))
        return True
    if spec.get("song_lyrics"):
        log("  singing the lyrics with ACE-Step")
        return ace_music(spec.get("song_style", spec.get("music", DEFAULT_MUSIC)) + ", clear child-friendly vocals",
                         spec["song_lyrics"], float(spec.get("song_seconds", 60)), dest)
    return False


# ---------- assembly ----------

def boomerang(anim: Path, length: float, dest: Path) -> None:
    """Loop a short animation forward-backward to fill a longer song section."""
    run("ffmpeg", "-y", "-loglevel", "error", "-i", str(anim), "-filter_complex",
        f"[0:v]fps={FPS},split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0,"
        "loop=loop=-1:size=32767:start=0[v]",
        "-map", "[v]", "-t", f"{length:.2f}", "-an", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "18", str(dest))


def make_clip(i: int, img: Path, anim: Path | None, clip: Path, length: float,
              audio: Path | None = None) -> None:
    fade = f"fade=t=in:st=0:d=0.25,fade=t=out:st={length - 0.25:.2f}:d=0.25,format=yuv420p"
    if anim:
        # Slow the animation a little if the section is longer, then hold the last frame.
        speed = min(1.6, max(1.0, length / max(0.5, duration(anim))))
        graph = (fit_graph(anim, f"setpts={speed:.3f}*PTS,fps={FPS}")[:-3] +
                 f"[f];[f]tpad=stop_mode=clone:stop_duration={length:.2f},{fade}[v]")
        video_in = ["-i", str(anim)]
    else:
        frames = int(length * FPS)
        step = 0.15 / max(1, frames)  # always zoom 15% over the clip, however long it is
        zoom = f"min(zoom+{step:.6f},1.15)" if i % 2 else f"if(eq(on,0),1.15,max(zoom-{step:.6f},1.0))"
        graph = (f"[0:v]scale={W * 3 // 2}:{H * 3 // 2},zoompan=z='{zoom}':d={frames}"
                 f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},{fade}[v]")
        video_in = ["-loop", "1", "-i", str(img)]
    audio_in = ["-i", str(audio)] if audio else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    run("ffmpeg", "-y", "-loglevel", "error", *video_in, *audio_in,
        "-filter_complex", graph, "-map", "[v]", "-map", "1:a", "-af", "apad", "-t", f"{length:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", str(clip))


def join(clips: list[Path], work: Path) -> Path:
    listing = work / "clips.txt"
    listing.write_text("".join(f"file '{c.name}'\n" for c in clips))
    joined = work / "joined.mp4"
    run("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", str(listing), "-c", "copy", str(joined))
    return joined


def main() -> None:
    global W, H, ASPECT
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("episode")
    p.add_argument("--format", choices=["9:16", "16:9"], default="9:16",
                   help="9:16 = YouTube Shorts (default), 16:9 = regular wide video")
    p.add_argument("--reuse", help="earlier render folder: reuse its song/voice, animation and music")
    args = p.parse_args()
    if args.format == "16:9":
        W, H, ASPECT = 1920, 1080, "16:9"
    reuse = Path(args.reuse).expanduser() if args.reuse else None

    def reused(name: str, dest: Path) -> bool:
        if reuse and (reuse / name).exists():
            shutil.copy(reuse / name, dest)
            return True
        return False

    spec = json.loads(Path(args.episode).read_text())
    style = spec.get("style", DEFAULT_STYLE)
    voice = spec.get("voice", "en-US-AnaNeural")
    scenes = spec["scenes"]
    suffix = "-wide" if ASPECT == "16:9" else ""
    work = OUT_ROOT / f"{time.strftime('%Y%m%d-%H%M%S')}-{slug(spec['title'])}{suffix}"
    work.mkdir(parents=True, exist_ok=True)
    log(f"gemini images: {'on' if GEMINI_KEY else 'off (no key)'}, hf token: {'yes' if HF_TOKEN else 'no'}, "
        f"animating up to {MAX_ANIMATED} scenes")

    refs = [Path(p).expanduser() for p in spec.get("character_refs", []) if Path(p).expanduser().exists()]
    wanted = [i for i, s in enumerate(scenes) if s.get("animate")] or list(range(len(scenes)))
    to_animate = set(wanted[:MAX_ANIMATED])

    gemini_used = 0
    for i, scene in enumerate(scenes):
        n = i + 1
        log(f"scene {n}/{len(scenes)}: picture")
        raw, img = work / f"s{n:02d}-raw.png", work / f"s{n:02d}.png"
        shape = "Vertical 9:16" if ASPECT == "9:16" else "Wide 16:9"
        prompt = f"{scene['image']}. Style: {style}. {shape} composition, character centered."
        given = Path(scene["image_file"]).expanduser() if scene.get("image_file") else None
        if given and given.exists():
            shutil.copy(given, raw)  # picture supplied by the user (e.g. made in the Gemini app)
        elif gemini_image(prompt, refs, raw):
            gemini_used += 1
            if not refs:
                refs = [raw]  # first scene becomes the character reference for the rest
        else:
            pollinations_image(prompt, seed=1000 + n, dest=raw)
        fit_frame(raw, img)

    # Sound comes first: it gets the free GPU quota before animation uses up the rest.
    song = work / "song.wav"
    log("song")
    song_mode = reused(song.name, song) or get_song(spec, song)

    if song_mode:
        # Whole video is the song: split its length across the scenes by how much each one sings.
        # The video is exactly as long as the song (a vertical Short is capped at YouTube's 3 minutes).
        total = duration(song) if ASPECT == "16:9" else min(duration(song), 175.0)
        weights = [max(1, len((s.get("lyrics") or s.get("narration") or "x").split())) for s in scenes]
        lengths = [total * w / sum(weights) for w in weights]
        music, have_music = None, False
    else:
        log("no song, using narration + background music")
        for i, scene in enumerate(scenes):
            audio = work / f"s{i + 1:02d}.mp3"
            if not reused(audio.name, audio):
                run(str(VENV / "edge-tts"), "--voice", voice, f"--rate={spec.get('voice_rate', '-5%')}",
                    f"--pitch={spec.get('voice_pitch', '+5Hz')}", "--text", scene["narration"],
                    "--write-media", str(audio))
        lengths = [duration(work / f"s{i + 1:02d}.mp3") + 0.6 for i in range(len(scenes))]
        music = work / "music.wav"
        have_music = reused(music.name, music) or make_music(spec, sum(lengths) + 1, music)

    clips, animated = [], 0
    for i, scene in enumerate(scenes):
        n = i + 1
        img, raw = work / f"s{n:02d}.png", work / f"s{n:02d}-raw.png"
        anim, clip = work / f"s{n:02d}-anim.mp4", work / f"s{n:02d}.mp4"
        log(f"scene {n}/{len(scenes)}: motion")
        # Animate the original picture (not the fitted frame), so the clip suits both formats.
        ok = reused(anim.name, anim) or (
            i in to_animate and animate(raw, scene.get("motion", scene["image"]), lengths[i], anim))
        animated += ok
        if ok and song_mode and lengths[i] > duration(anim) * 1.3:
            looped = work / f"s{n:02d}-loop.mp4"
            boomerang(anim, lengths[i], looped)
            anim = looped
        audio = None if song_mode else work / f"s{n:02d}.mp3"
        make_clip(n, img, anim if ok else None, clip, lengths[i], audio)
        clips.append(clip)

    joined = join(clips, work)
    total = duration(joined)
    # Scene start/end times, used to cut the video into Shorts at scene boundaries.
    t, timeline = 0.0, []
    for i, c in enumerate(clips):
        d = duration(c)
        timeline.append({"scene": i + 1, "start": round(t, 2), "end": round(t + d, 2)})
        t += d
    (work / "timeline.json").write_text(json.dumps(timeline, indent=2))
    final = work / f"{slug(spec['title'])}.mp4"
    if song_mode:
        run("ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), "-i", str(song),
            "-filter_complex", f"[1:a]afade=t=out:st={max(0, total - 2):.2f}:d=2,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", f"{total:.2f}", "-movflags", "+faststart", str(final))
    elif have_music:
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
    mode = "song" if song_mode else "narration"
    log(f"done: {len(scenes)} scenes, {mode}, {gemini_used} Gemini images, {animated} animated, {total:.0f}s")
    print(final)


if __name__ == "__main__":
    main()
