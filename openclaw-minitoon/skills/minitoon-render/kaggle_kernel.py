# Minitoon animator: runs on a free Kaggle GPU.
# Input: dataset with jobs.json [{"name": "s01", "image": "s01.jpg", "motion": "...", "seconds": 4}] + images.
# Output: /kaggle/working/<name>.mp4 for every job it managed, plus log.json.
import glob
import json
import os
import subprocess
import sys
import time
import traceback

t0 = time.time()
log = {"clips": {}, "errors": []}


def save_log():
    log["minutes"] = round((time.time() - t0) / 60, 1)
    json.dump(log, open("/kaggle/working/log.json", "w"), indent=2)


import socket  # noqa: E402

import torch  # noqa: E402

# Fail fast: without a GPU and internet (phone-unverified accounts get neither) there's nothing to do.
try:
    socket.create_connection(("pypi.org", 443), timeout=10).close()
    log["internet"] = True
except OSError:
    log["internet"] = False
if not torch.cuda.is_available() or not log["internet"]:
    log["errors"].append(f"no GPU or no internet (gpu={torch.cuda.is_available()}, internet={log['internet']}): "
                         "check Kaggle phone verification")
    save_log()
    raise SystemExit("no GPU / internet")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "diffusers", "transformers", "accelerate",
                "sentencepiece", "imageio", "imageio-ffmpeg", "ftfy"], check=False)
from diffusers.utils import export_to_video, load_image  # noqa: E402

log["gpu"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none"
log["gpus"] = torch.cuda.device_count()
if not torch.cuda.is_available():
    log["errors"].append("no GPU attached to this run")
    save_log()
    raise SystemExit("no GPU")
src = os.path.dirname(glob.glob("/kaggle/input/**/jobs.json", recursive=True)[0])
jobs = json.load(open(f"{src}/jobs.json"))
settings = json.load(open(f"{src}/settings.json")) if os.path.exists(f"{src}/settings.json") else {}
MODEL = settings.get("model", "ltx")
log["model"] = MODEL
save_log()

NEG = "worst quality, blurry, distorted face, extra limbs, deformed, jittery, text, watermark"
try:
    if MODEL == "ltx":
        from diffusers import LTXConditionPipeline
        from diffusers.pipelines.ltx.pipeline_ltx_condition import LTXVideoCondition
        # 2B model: fits Kaggle's RAM (the 13B versions get killed while loading).
        pipe = LTXConditionPipeline.from_pretrained(settings.get("ltx_repo", "Lightricks/LTX-Video-0.9.5"),
                                                    torch_dtype=torch.bfloat16, low_cpu_mem_usage=True)
        pipe.enable_model_cpu_offload()
        pipe.vae.enable_tiling()
        W, H, FPS = settings.get("width", 768), settings.get("height", 448), 24
    else:
        from diffusers import AutoencoderKLWan, WanImageToVideoPipeline
        mid = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
        vae = AutoencoderKLWan.from_pretrained(mid, subfolder="vae", torch_dtype=torch.float32)
        pipe = WanImageToVideoPipeline.from_pretrained(mid, vae=vae, torch_dtype=torch.float16)
        pipe.enable_model_cpu_offload()
        W, H, FPS = settings.get("width", 832), settings.get("height", 480), 24
    log["load_minutes"] = round((time.time() - t0) / 60, 1)
    save_log()
except Exception:
    log["errors"].append("load: " + traceback.format_exc()[-1500:])
    save_log()
    raise

for job in jobs:
    t = time.time()
    try:
        img = load_image(f"{src}/{job['image']}").resize((W, H))
        frames = int(min(5.0, max(2.0, job.get("seconds", 4))) * FPS) // 8 * 8 + 1
        prompt = f"{job['motion']}, smooth Pixar-style 3D cartoon animation, cute, expressive, gentle camera motion"
        if MODEL == "ltx":
            cond = LTXVideoCondition(image=img, frame_index=0)
            video = pipe(conditions=[cond], prompt=prompt, negative_prompt=NEG, width=W, height=H,
                         num_frames=frames, num_inference_steps=settings.get("steps", 30),
                         guidance_scale=3.0, decode_timestep=0.05, decode_noise_scale=0.025,
                         image_cond_noise_scale=0.025,
                         generator=torch.Generator().manual_seed(42)).frames[0]
        else:
            video = pipe(image=img, prompt=prompt, negative_prompt=NEG, width=W, height=H,
                         num_frames=frames, num_inference_steps=settings.get("steps", 30),
                         guidance_scale=5.0, generator=torch.Generator().manual_seed(42)).frames[0]
        export_to_video(video, f"/kaggle/working/{job['name']}.mp4", fps=FPS)
        log["clips"][job["name"]] = round(time.time() - t, 1)
    except Exception:
        log["errors"].append(f"{job['name']}: " + traceback.format_exc()[-1200:])
        torch.cuda.empty_cache()
    save_log()
    if time.time() - t0 > settings.get("budget_minutes", 100) * 60:
        log["errors"].append("time budget reached, stopping")
        break
save_log()
print(json.dumps(log, indent=2))
