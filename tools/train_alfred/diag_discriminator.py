#!/usr/bin/env python3
"""Find the REAL discriminating feature: compare many pos vs neg end-aligned 3s windows.

For each clip: compute the 28x96 features end-aligned, then look at stats of the
LAST-8-timestep energy vs FIRST-20. The model must be using something; find what
separates pos/neg so we can verify a retrain generalizes rather than exploiting
an artifact. Also test a stronger baseline: per-timestep feature differences.
"""
import glob
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools")
import openwakeword  # noqa: E402

WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"
F = openwakeword.utils.AudioFeatures()

N = 120


def endaligned_feats(path):
    data, _ = sf.read(path, dtype="int16")
    buf = np.zeros(48000, dtype=np.int16)
    j = min(48000 - len(data), 1600)
    start = 48000 - len(data) - j
    buf[start:start + len(data)] = data
    return F.embed_clips(buf[None, :], batch_size=1)[0]


pos_feats, neg_feats = [], []
for p in sorted(glob.glob(f"{WORKDIR}/positive/*.wav"))[:N]:
    pos_feats.append(endaligned_feats(p))
for p in sorted(glob.glob(f"{WORKDIR}/negative_nearmiss/*.wav"))[:N]:
    neg_feats.append(endaligned_feats(p))
pos_feats = np.stack(pos_feats)
neg_feats = np.stack(neg_feats)
print("pos", pos_feats.shape, "neg", neg_feats.shape)

# per-timestep mean activation
pm = np.abs(pos_feats).mean(axis=(0, 2))
nm = np.abs(neg_feats).mean(axis=(0, 2))
for i in range(0, 28, 4):
    print(f"ts[{i:2d}]: pos={pm[i]:.2f} neg={nm[i]:.2f}")

# last-timestep activation comparison
print("last-ts pos mean:", float(np.abs(pos_feats[:, -1, :]).mean()),
      "neg:", float(np.abs(neg_feats[:, -1, :]).mean()))

# Look at feature MEAN over last 8 timesteps as a 96-dim vector
pos_tail = np.abs(pos_feats[:, -8:, :]).mean(axis=(1, 2))
neg_tail = np.abs(neg_feats[:, -8:, :]).mean(axis=(1, 2))
print("tail8 pos mean/std:", pos_tail.mean(), pos_tail.std())
print("tail8 neg mean/std:", neg_tail.mean(), neg_tail.std())

# How about DURATION? pos clips are 'hey alfred' (2 words, ~0.7 s),
# near-miss are many phrases, some much longer. Check durations:
import soundfile as sf2
pos_dur = [sf2.info(p).duration for p in sorted(glob.glob(f"{WORKDIR}/positive/*.wav"))[:N]]
neg_dur = [sf2.info(p).duration for p in sorted(glob.glob(f"{WORKDIR}/negative_nearmiss/*.wav"))[:N]]
print("pos dur mean:", np.mean(pos_dur), "neg dur mean:", np.mean(neg_dur))
print("pos dur p10/p90:", np.percentile(pos_dur, [10, 90]), "neg:", np.percentile(neg_dur, [10, 90]))
