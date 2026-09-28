#!/usr/bin/env python3
"""Diagnose per-timestep feature stats: pos vs neg on the same near-miss clips.

Key question: is the near-miss clip (as a 3s window) actually DIFFERENT at the
feature level from a positive clip? If yes -> training bug. If no -> data issue.
"""
import glob
import sys

import numpy as np

sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools")
import openwakeword
import openwakeword.data

WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"
F = openwakeword.utils.AudioFeatures()

# Take 3 positive and 3 near-miss clips, compute features on exact 3s windows ending at clip end
import soundfile as sf

def feature_last_ts(path):
    data, sr = sf.read(path, dtype="int16")
    n = len(data)
    buf = np.zeros(16000 * 3, dtype=np.int16)
    j = min(len(buf) - len(data), int(0.1 * 16000))
    buf[-len(data) - j:-j if j else None] = data
    feats = F.embed_clips(buf[None, :], batch_size=1)
    return feats[0]  # (28, 96)

pos_f, neg_f = [], []
for p in sorted(glob.glob(f"{WORKDIR}/positive/*.wav"))[:6]:
    pos_f.append(feature_last_ts(p))
for p in sorted(glob.glob(f"{WORKDIR}/negative_nearmiss/*.wav"))[:6]:
    neg_f.append(feature_last_ts(p))

pos_f = np.stack(pos_f)
neg_f = np.stack(neg_f)
print("pos per-timestep mean (last 10):", np.round(np.abs(pos_f).mean(axis=(0, 2))[-10:], 2))
print("neg per-timestep mean (last 10):", np.round(np.abs(neg_f).mean(axis=(0, 2))[-10:], 2))

# The features fed at training time for pos: end-aligned. At inference, the model
# sees the SAME 28x96 window shape. Compare END-of-window behavior:
print("\npos features, last timestep, first 6 clips, first 8 dims:")
for i in range(6):
    print(" pos:", np.round(pos_f[i, -1, :8], 2))
print("\nneg features, last timestep, first 6 clips, first 8 dims:")
for i in range(6):
    print(" neg:", np.round(neg_f[i, -1, :8], 8) if False else np.round(neg_f[i, -1, :8], 3))
