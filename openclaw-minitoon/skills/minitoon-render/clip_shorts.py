#!/usr/bin/env python3
"""Cut a finished wide (16:9) episode into vertical Shorts at scene boundaries.

Usage: clip_shorts.py WIDE.mp4 [--count 4]
Needs timeline.json (written by render.py) next to the video.
Prints the Short paths, one per line.
"""
import argparse
import json
import subprocess
from pathlib import Path

W, H = 1080, 1920


def run(*cmd: str) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"ffmpeg failed: {r.stderr[-400:]}")


def groups(timeline: list[dict], count: int) -> list[tuple[float, float]]:
    """Split into `count` parts of roughly equal length, cutting only between scenes."""
    total = timeline[-1]["end"]
    count = max(1, min(count, len(timeline)))
    bounds = [s["end"] for s in timeline[:-1]]  # possible cut points
    cuts = []
    for k in range(1, count):
        ideal = total * k / count
        options = [b for b in bounds if not cuts or b > cuts[-1]]
        if options:
            cuts.append(min(options, key=lambda b: abs(b - ideal)))
    edges = [0.0] + cuts + [total]
    return [(a, b) for a, b in zip(edges, edges[1:]) if b - a > 3]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("video")
    p.add_argument("--count", type=int, default=4)
    a = p.parse_args()
    video = Path(a.video)
    timeline = json.loads((video.parent / "timeline.json").read_text())

    # Wide picture in a tall frame: zoom in on the centre over a blurred copy of itself.
    graph = (f"[0:v]split[a][b];"
             f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:2,eq=brightness=-0.05[bg];"
             f"[b]scale={int(W * 1.45)}:-2,crop={W}:ih[fg];[bg][fg]overlay=0:(H-h)/2,format=yuv420p[v];"
             "[0:a]afade=t=in:d=0.3[a0]")
    for k, (start, end) in enumerate(groups(timeline, a.count), 1):
        length = end - start
        out = video.parent / f"short-{k}.mp4"
        run("ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{length:.2f}", "-i", str(video),
            "-filter_complex", graph + f";[a0]afade=t=out:st={max(0, length - 1):.2f}:d=1[aout]",
            "-map", "[v]", "-map", "[aout]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out))
        print(out)


if __name__ == "__main__":
    main()
