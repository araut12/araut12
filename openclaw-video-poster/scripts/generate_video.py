"""Generate a short vertical video from a text prompt using a Replicate model.

Usage: python scripts/generate_video.py "a neon koi fish swimming through a rainy city"
Prints the path of the saved .mp4 on success.
"""
import argparse
import time
from datetime import datetime

import requests

from common import OUTPUT_DIR, env

API = "https://api.replicate.com/v1"


def generate(prompt: str) -> str:
    token = env("REPLICATE_API_TOKEN")
    model = env("REPLICATE_VIDEO_MODEL", "minimax/video-01")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    r = requests.post(
        f"{API}/models/{model}/predictions",
        headers=headers,
        json={"input": {"prompt": prompt, "aspect_ratio": "9:16"}},
        timeout=60,
    )
    r.raise_for_status()
    prediction = r.json()

    # Video models usually take 1-10 minutes.
    deadline = time.time() + 20 * 60
    while prediction["status"] not in ("succeeded", "failed", "canceled"):
        if time.time() > deadline:
            raise SystemExit("Video generation timed out after 20 minutes")
        time.sleep(10)
        prediction = requests.get(prediction["urls"]["get"], headers=headers, timeout=60).json()

    if prediction["status"] != "succeeded":
        raise SystemExit(f"Generation {prediction['status']}: {prediction.get('error')}")

    output = prediction["output"]
    video_url = output[0] if isinstance(output, list) else output

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"video-{datetime.now():%Y%m%d-%H%M%S}.mp4"
    with requests.get(video_url, stream=True, timeout=300) as dl:
        dl.raise_for_status()
        with path.open("wb") as f:
            for chunk in dl.iter_content(1 << 20):
                f.write(chunk)
    return str(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt")
    print(generate(parser.parse_args().prompt))
