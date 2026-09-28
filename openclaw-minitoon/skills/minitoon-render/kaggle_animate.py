#!/usr/bin/env python3
"""Animate pictures on a free Kaggle GPU (official Kaggle API) and download the clips.

Usage: kaggle_animate.py JOBS.json OUT_DIR [--model ltx|wan] [--budget 100]
JOBS.json: [{"name": "s01", "image": "/path/pic.jpg", "motion": "Bunny waves", "seconds": 4}, ...]
Writes OUT_DIR/<name>.mp4 for each clip it got, and OUT_DIR/log.json. Exit code 0 if at least one clip came back.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home() / ".openclaw"
KAGGLE = str(HOME / "venv-kaggle/bin/kaggle")
KERNEL_SRC = Path(__file__).resolve().parent / "kaggle_kernel.py"
ENV = {**os.environ, "KAGGLE_API_TOKEN": (HOME / "secrets/kaggle_token").read_text().strip()}


def kaggle(*args: str, check: bool = True) -> str:
    r = subprocess.run([KAGGLE, *args], capture_output=True, text=True, env=ENV)
    if check and r.returncode:
        raise SystemExit(f"kaggle {' '.join(args[:2])} failed: {(r.stderr or r.stdout)[-400:]}")
    return (r.stdout + r.stderr).strip()


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("jobs")
    p.add_argument("out")
    p.add_argument("--model", default="ltx", choices=["ltx", "wan"])
    p.add_argument("--budget", type=int, default=100, help="GPU minutes before the notebook stops itself")
    a = p.parse_args()
    user = kaggle("config", "view").split("username:")[1].split()[0]
    ds_id, kernel_id = f"{user}/minitoon-frames", f"{user}/minitoon-animator"

    stage = Path("/tmp/kaggle-stage")
    shutil.rmtree(stage, ignore_errors=True)
    (stage / "data").mkdir(parents=True)
    (stage / "kernel").mkdir()
    jobs = json.loads(Path(a.jobs).read_text())
    out_jobs = []
    for j in jobs:
        dst = stage / "data" / f"{j['name']}.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", j["image"], "-vf", "scale='min(1280,iw)':-2",
                        "-q:v", "3", str(dst)], check=True)
        out_jobs.append({**j, "image": dst.name})
    (stage / "data/jobs.json").write_text(json.dumps(out_jobs, indent=2))
    (stage / "data/settings.json").write_text(json.dumps({"model": a.model, "budget_minutes": a.budget}))
    (stage / "data/dataset-metadata.json").write_text(json.dumps(
        {"title": "minitoon-frames", "id": ds_id, "licenses": [{"name": "CC0-1.0"}]}))

    # (the dataset "status" endpoint is forbidden for access tokens, so check the owner's list instead)
    exists = ds_id in kaggle("datasets", "list", "--mine", check=False)
    log(f"uploading {len(jobs)} pictures (private dataset {ds_id})")
    if exists:
        kaggle("datasets", "version", "-p", str(stage / "data"), "-m", time.strftime("%Y-%m-%d %H:%M"))
    else:
        kaggle("datasets", "create", "-p", str(stage / "data"))
    time.sleep(90)  # let the new version finish processing before the notebook mounts it

    shutil.copy(KERNEL_SRC, stage / "kernel/animator.py")
    (stage / "kernel/kernel-metadata.json").write_text(json.dumps({
        "id": kernel_id, "title": "minitoon-animator", "code_file": "animator.py", "language": "python",
        "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True,
        "machine_shape": "NvidiaTeslaT4",
        "dataset_sources": [ds_id], "competition_sources": [], "kernel_sources": []}))
    log("starting the Kaggle GPU notebook")
    kaggle("kernels", "push", "-p", str(stage / "kernel"), "--accelerator", "NvidiaTeslaT4")

    deadline = time.time() + (a.budget + 40) * 60
    status = ""
    while time.time() < deadline:
        time.sleep(60)
        status = kaggle("kernels", "status", kernel_id, check=False).lower()
        log(f"  {time.strftime('%H:%M')} {status[-60:]}")
        if any(s in status for s in ("complete", "error", "cancel")):
            break

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    kaggle("kernels", "output", kernel_id, "-p", str(out), check=False)
    clips = sorted(out.glob("*.mp4"))
    info = json.loads((out / "log.json").read_text()) if (out / "log.json").exists() else {}
    log(f"status: {status[-60:]} | clips back: {len(clips)} | {json.dumps(info)[:600]}")
    sys.exit(0 if clips else 1)


if __name__ == "__main__":
    main()
