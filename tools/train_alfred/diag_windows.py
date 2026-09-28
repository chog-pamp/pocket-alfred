#!/usr/bin/env python3
"""Diagnose: raw ONNX score on train-style features, for pos / neg / mixed-audio windows.

Question: does the raw 28x96 classifier itself fire on negatives when the near-miss
phrase sits mid-window (as it does in streaming), or only when end-aligned?
"""
import glob
import sys

import numpy as np
import soundfile as sf
import onnxruntime as ort

sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools")
import openwakeword  # noqa: E402

WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"
sess = ort.InferenceSession(f"{WORKDIR}/hey_alfred.onnx", providers=["CPUExecutionProvider"])
input_name = sess.get_inputs()[0].name
F = openwakeword.utils.AudioFeatures()


def score(buf):
    feats = F.embed_clips(buf[None, :], batch_size=1)[0]
    return float(sess.run(None, {input_name: feats[None]})[0][0][0])


pneg = sorted(glob.glob(f"{WORKDIR}/negative_nearmiss/*.wav"))[0]
ppos = sorted(glob.glob(f"{WORKDIR}/positive/*.wav"))[0]
p, pp = pneg, ppos

# positive end-aligned
data, _ = sf.read(pp, dtype="int16")
buf = np.zeros(48000, dtype=np.int16)
buf[-len(data):] = data
print("pos end-aligned:", score(buf))

# near-miss end-aligned (this is how it would appear at inference end-of-phrase)
data, _ = sf.read(p, dtype="int16")
buf = np.zeros(48000, dtype=np.int16)
buf[-len(data):] = data
print("neg end-aligned:", score(buf))

# near-miss START-aligned (phrase in middle of window)
data, _ = sf.read(p, dtype="int16")
buf = np.zeros(48000, dtype=np.int16)
buf[:len(data)] = data
print("neg start-aligned:", score(buf))

# near-miss repeated to fill the whole 3 s
data2 = np.tile(data, 5)[:48000]
print("neg tiled:", score(data2))

# random speech-ish audio (near-miss) mixed with music from fma
fma = sorted(glob.glob(f"{WORKDIR}/fma_sample/*.wav"))[0]
fdat, _ = sf.read(fma, dtype="int16")
buf = np.zeros(48000, dtype=np.int16)
buf[-len(data):] = data
buf[: len(fdat)] = fdat[:48000]
print("neg nearmiss end-aligned over music:", score(buf))
