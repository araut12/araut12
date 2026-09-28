#!/usr/bin/env python3
"""Cut a finished wide (16:9) song episode into catchy vertical Shorts.

Each Short is built around a CHORUS (the catchiest part): it starts a scene before the chorus when
there's room, ends when the chorus ends, stays 15-58 seconds, and shows the song title for the first
3 seconds. With no lyrics to go on, it falls back to equal parts cut between scenes.

Usage: clip_shorts.py WIDE.mp4 [--count 4]
Needs timeline.json and episode.json (both written by render.py) next to the video.
Prints the Short paths, one per line.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

W, H = 1080, 1920
MIN_LEN, MAX_LEN = 15.0, 58.0
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def run(*cmd: str) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"ffmpeg failed: {r.stderr[-400:]}")


def words(text: str) -> str:
    return re.sub(r"[^a-z ]+", "", text.lower()).strip()


def chorus_scenes(ep: dict) -> list[int]:
    """Indexes of scenes whose lyrics include a chorus line."""
    lines, in_chorus = [], False
    for line in ep.get("song_lyrics", "").splitlines():
        tag = line.strip().lower()
        if tag.startswith("["):
            in_chorus = "chorus" in tag
        elif in_chorus and words(line):
            lines.append(words(line))
    hits = []
    for i, s in enumerate(ep["scenes"]):
        text = words(s.get("lyrics") or s.get("narration") or "")
        if any(l and l in text for l in lines):
            hits.append(i)
    return hits


def span(timeline: list[dict], first: int, last: int) -> tuple[float, float]:
    return timeline[first]["start"], timeline[last]["end"]


def chorus_windows(timeline: list[dict], hits: list[int], count: int) -> list[tuple[float, float]]:
    # Group neighbouring chorus scenes into one chorus block.
    blocks = []
    for i in hits:
        if blocks and i == blocks[-1][1] + 1:
            blocks[-1][1] = i
        else:
            blocks.append([i, i])
    wins = []
    for first, last in blocks:
        # Lead in with the scene before the chorus (the setup), then widen until long enough.
        if first > 0:
            first -= 1
        while True:
            a, b = span(timeline, first, last)
            if b - a >= MIN_LEN:
                break
            if first > 0:
                first -= 1
            elif last < len(timeline) - 1:
                last += 1
            else:
                break
        # Too long? Trim scenes from the front (the chorus stays).
        while span(timeline, first, last)[1] - span(timeline, first, last)[0] > MAX_LEN and first < last:
            first += 1
        wins.append(span(timeline, first, last))
    # Also a "story teaser": the hook from the start.
    first, last = 0, 0
    while last < len(timeline) - 1 and span(timeline, 0, last)[1] < MIN_LEN + 5:
        last += 1
    teaser = span(timeline, first, last)
    if all(abs(teaser[0] - w[0]) > 3 for w in wins):
        wins.append(teaser)
    seen, out = set(), []
    for w in wins:
        key = (round(w[0]), round(w[1]))
        if key not in seen:
            seen.add(key)
            out.append(w)
    return out[:count]


def even_windows(timeline: list[dict], count: int) -> list[tuple[float, float]]:
    total = timeline[-1]["end"]
    count = max(1, min(count, len(timeline)))
    bounds = [s["end"] for s in timeline[:-1]]
    cuts = []
    for k in range(1, count):
        ideal = total * k / count
        options = [b for b in bounds if not cuts or b > cuts[-1]]
        if options:
            cuts.append(min(options, key=lambda b: abs(b - ideal)))
    edges = [0.0] + cuts + [total]
    return [(a, min(b, a + MAX_LEN)) for a, b in zip(edges, edges[1:]) if b - a > 3]


def title_text(ep: dict) -> str:
    # drawtext can't show emoji; keep letters, numbers and simple punctuation.
    t = re.sub(r"[^A-Za-z0-9 '!?&,.-]+", "", ep.get("title", "")).strip()
    return t.split("|")[0].strip()[:28].replace("'", "’").replace(":", " ")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("video")
    p.add_argument("--count", type=int, default=4)
    a = p.parse_args()
    video = Path(a.video)
    timeline = json.loads((video.parent / "timeline.json").read_text())
    ep_file = video.parent / "episode.json"
    ep = json.loads(ep_file.read_text()) if ep_file.exists() else {"scenes": []}

    hits = chorus_scenes(ep) if ep.get("scenes") else []
    windows = chorus_windows(timeline, hits, a.count) if hits else []
    if len(windows) < min(a.count, 2):
        windows = even_windows(timeline, a.count)

    title = title_text(ep)
    overlay = ""
    if title:
        overlay = (f",drawtext=fontfile={FONT}:text='{title}':fontsize=78:fontcolor=white:borderw=6:"
                   f"bordercolor=0xE0508A:x=(w-text_w)/2:y=h*0.12:enable='lt(t,3)'")
    graph = (f"[0:v]split[a][b];"
             f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:2,eq=brightness=-0.05[bg];"
             f"[b]scale={int(W * 1.45)}:-2,crop={W}:ih[fg];[bg][fg]overlay=0:(H-h)/2{overlay},format=yuv420p[v]")
    for k, (start, end) in enumerate(windows, 1):
        length = end - start
        out = video.parent / f"short-{k}.mp4"
        run("ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{length:.2f}", "-i", str(video),
            "-filter_complex", graph + f";[0:a]afade=t=in:d=0.2,afade=t=out:st={max(0, length - 1):.2f}:d=1[aout]",
            "-map", "[v]", "-map", "[aout]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out))
        print(out)


if __name__ == "__main__":
    main()
