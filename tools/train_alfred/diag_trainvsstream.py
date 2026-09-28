#!/usr/bin/env python3
"""Compare TRAIN-TIME features (embed_clips) vs STREAM-TIME features (Model.predict path)
for the same audio. Must match, or the model trains on a distribution it never sees."""
import glob
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools")
import openwakeword

WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"
F = openwakeword.utils.AudioFeatures()


def trainstyle_features(path):
    data, _ = sf.read(path, dtype="int16")
    buf = np.zeros(16000 * 3, dtype=np.int16)
    j = min(48000 - len(data), 1600)
    start = 48000 - len(data) - j
    buf[start:start + len(data)] = data
    feats = F.embed_clips(buf[None, :], batch_size=1)
    return feats[0]


def stream_feats(path):
    data, _ = sf.read(path, dtype="int16")
    F2 = openwakeword.utils.AudioFeatures()
    for i in range(0, len(data) - 1280 + 1, 1280):
        F2(data[i:i + 1280].astype(np.int16))
    return F2.get_features(28)[0]


p = sorted(glob.glob(f"{WORKDIR}/positive/*.wav"))[0]
tf = trainstyle_features(p)
sf_ = stream_feats(p)
print("trainstyle last frame (8 dims):", np.round(tf[-1][:8], 3))
print("streamstyle last frame (8 dims):", np.round(sf_[-1][:8], 3))
print("corr:", np.corrcoef(tf.flatten(), sf_.flatten())[0, 1])
print("trainstyle mean/std:", tf.mean(), tf.std())
print("streamstyle mean/std:", sf_.mean(), sf_.std())
