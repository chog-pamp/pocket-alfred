#!/usr/bin/env python3
"""Find what the trained model keys on: score vs duration/energy for negatives."""
import glob
import sys

import numpy as np
import soundfile as sf
import onnxruntime as ort

sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools")
import openwakeword  # noqa: E402

WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"
F = openwakeword.utils.AudioFeatures()
sess = ort.InferenceSession(f"{WORKDIR}/hey_alfred.onnx", providers=["CPUExecutionProvider"])
input_name = sess.get_inputs()[0].name

scores_ = []
for p in sorted(glob.glob(f"{WORKDIR}/negative_nearmiss/*.wav"))[:200]:
    data, _ = sf.read(p, dtype="int16")
    buf = np.zeros(48000, dtype=np.int16)
    j = min(48000 - len(data), 1600)
    start = 48000 - len(data) - j
    buf[start:start + len(data)] = data
    sc = float(sess.run(None, {input_name: F.embed_clips(buf[None, :], batch_size=1)[0][None]})[0][0][0])
    scores_.append((sc, len(data) / 16000, p))

scores_.sort(reverse=True)
print("top-5 scoring negatives (score, dur, file):")
for s in scores_[:5]:
    print("  ", round(s[0], 3), round(s[1], 2), s[2].split("/")[-1])
print("bottom-5:")
for s in scores_[-5:]:
    print("  ", round(s[0], 3), round(s[1], 2), s[2].split("/")[-1])
scs = np.array([s[0] for s in scores_])
durs = np.array([s[1] for s in scores_])
print("corr(score, dur):", np.corrcoef(scs, durs)[0, 1])
