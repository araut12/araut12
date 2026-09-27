#!/usr/bin/env python3
"""Generate free background music locally with MusicGen-small (CPU).

Usage: make_music.py "cheerful ukulele kids cartoon music" OUT.wav [seconds]
"""
import sys

import numpy as np
import scipy.io.wavfile
import torch
from transformers import AutoProcessor, MusicgenForConditionalGeneration

prompt, out = sys.argv[1], sys.argv[2]
seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 20

torch.set_num_threads(max(1, torch.get_num_threads()))
processor = AutoProcessor.from_pretrained("facebook/musicgen-small")
model = MusicgenForConditionalGeneration.from_pretrained("facebook/musicgen-small")
inputs = processor(text=[prompt], padding=True, return_tensors="pt")
tokens = int(seconds * model.config.audio_encoder.frame_rate)
with torch.no_grad():
    audio = model.generate(**inputs, do_sample=True, guidance_scale=3, max_new_tokens=tokens)
rate = model.config.audio_encoder.sampling_rate
data = audio[0, 0].numpy()
data = (data / max(1e-6, np.abs(data).max()) * 0.9 * 32767).astype(np.int16)
scipy.io.wavfile.write(out, rate, data)
print(out)
