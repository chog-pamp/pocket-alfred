#!/usr/bin/env python3
"""CRITICAL: streaming-score a near-miss clip and print score trajectory.
If the model fires ONLY on the 'background music/noise' segments (never on the
phrase), then the classifier learned 'silence->speech onset' as POSITIVE signal
because the randomized-position positives taught it wrong. The trajectory tells
us: which parts of near-miss clips score high?
"""
import glob
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools")
import openwakeword  # noqa: E402

WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"
oww = openwakeword.Model(wakeword_model_paths=[f"{WORKDIR}/hey_alfred.onnx"])

for name in ["negative_nearmiss/nearmiss_0000.wav", "negative_nearmiss/nearmiss_0004.wav"]:
    p = f"{WORKDIR}/{name}"
    sc = [round(list(s.values())[0], 3) for s in oww.predict_clip(p)]
    oww.reset()
    data, _ = sf.read(p, dtype="int16")
    # energy envelope in 300ms bins
    e = [int(np.abs(data[k:k+4800].astype(np.float32)).mean()) for k in range(0, len(data), 4800)]
    print(f"{name}: dur={len(data)/16000:.2f}s")
    print("  scores:", sc)
    print("  energy:", e)

# and a positive:
p = sorted(glob.glob(f"{WORKDIR}/positive/*.wav"))[0]
sc = [round(list(s.values())[0], 3) for s in oww.predict_clip(p)]
oww.reset()
data, _ = sf.read(p, dtype="int16")
e = [int(np.abs(data[k:k+4800].astype(np.float32)).mean()) for k in range(0, len(data), 4800)]
print(f"POS {p.split('/')[-1]}: dur={len(data)/16000:.2f}s")
print("  scores:", sc)
print("  energy:", e)
