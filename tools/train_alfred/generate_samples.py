#!/usr/bin/env python3
"""Generate synthetic 'hey alfred' positive samples + near-miss negative samples via edge-tts.

Outputs 16 kHz 16-bit mono WAV files:
  positive/  hey_alfred_XXX.wav   (~1.0-1.5 s)
  negative_nearmiss/ nearmiss_XXX.wav (~1.0-1.5 s)
"""
import asyncio
import os
import sys
import random

import edge_tts
import numpy as np
import soundfile as sf

SR = 16000
OUT_POS = "/home/leo/homelab/pocket-alfred/tools/train_alfred/positive"
OUT_NEG = "/home/leo/homelab/pocket-alfred/tools/train_alfred/negative_nearmiss"
os.makedirs(OUT_POS, exist_ok=True)
os.makedirs(OUT_NEG, exist_ok=True)

random.seed(20260923)

VOICES = [
    "sv-SE-MattiasNeural", "sv-SE-SofieNeural",
    "en-US-GuyNeural", "en-US-JennyNeural", "en-US-AriaNeural",
    "en-GB-RyanNeural", "en-GB-SoniaNeural",
    "en-AU-NatashaNeural", "en-IN-NeerjaNeural", "en-US-ChristopherNeural",
]

POS_TEXTS = ["hey alfred"]
NEG_TEXTS = ["hej hermes", "hey hermes", "hey alva", "hi arnold", "hey alvin",
             "hey alfredo", "hey alba", "hi alfred", "hey olaf", "hey alvar"]


def jitter(rate_base=0, pitch_base=0):
    rate = f"{rate_base + random.randint(-12, 25):+d}%"
    pitch = f"{pitch_base + random.randint(-15, 15):+d}Hz"
    return rate, pitch


async def gen_one(text, voice, out_path, idx):
    rate, pitch = jitter()
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    tmp = out_path + ".tmp.mp3"
    await communicate.save(tmp)
    # decode via ffmpeg to 16k mono wav, trim silence lightly
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-loglevel", "error", "-i", tmp,
        "-af", "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse",
        "-ar", str(SR), "-ac", "1", "-sample_fmt", "s16", out_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, err = await proc.communicate()
    os.remove(tmp)
    return proc.returncode == 0, err.decode()[:200]


async def main():
    n_pos = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    n_neg = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    sem = asyncio.Semaphore(12)

    async def bounded(text, voice, path):
        async with sem:
            ok, err = await gen_one(text, voice, path, 0)
            return ok, path, err

    tasks = []
    for i in range(n_pos):
        voice = random.choice(VOICES)
        text = random.choice(POS_TEXTS)
        tasks.append(bounded(text, voice, os.path.join(OUT_POS, f"hey_alfred_{i:04d}.wav")))
    for i in range(n_neg):
        voice = random.choice(VOICES)
        text = random.choice(NEG_TEXTS)
        tasks.append(bounded(text, voice, os.path.join(OUT_NEG, f"nearmiss_{i:04d}.wav")))

    fails = 0
    for fut in asyncio.as_completed(tasks):
        ok, path, err = await fut
        if not ok:
            fails += 1
            print("FAIL", path, err, file=sys.stderr)
    print(f"done. positives={len(os.listdir(OUT_POS))} negatives={len(os.listdir(OUT_NEG))} fails={fails}")


asyncio.run(main())
