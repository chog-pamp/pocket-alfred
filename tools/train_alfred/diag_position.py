#!/usr/bin/env python3
"""CRITICAL TEST: score positive-audio placed at DIFFERENT positions in the 3s window.

If 'hey alfred' at start-aligned position scores ~0.03, the model has memorized
'end-aligned phrase + quiet before' and will never fire in streaming (where the
phrase is mid-window when frames slide past). This tells us what to fix.
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

pp = sorted(glob.glob(f"{WORKDIR}/positive/*.wav"))[3]
data, _ = sf.read(pp, dtype="int16")
print("clip dur:", len(data) / 16000)

for name, start in [("end-aligned", 48000 - len(data)),
                    ("middle", 24000 - len(data) // 2),
                    ("start-aligned", 1600)]:
    buf = np.zeros(48000, dtype=np.int16)
    buf[start:start + len(data)] = data
    feats = F.embed_clips(buf[None, :], batch_size=1)[0]
    sc = float(sess.run(None, {input_name: feats[None]})[0][0][0])
    print(f"pos {name}: score={sc:.4f}")

# Also check the raw + scaled variants for the near-miss
pneg = sorted(glob.glob(f"{WORKDIR}/negative_nearmiss/*.wav"))[0]
data, _ = sf.read(pneg, dtype="int16")
for name, start in [("end-aligned", 48000 - len(data)),
                    ("start-aligned", 0),
                    ("middle", 24000 - len(data) // 2)]:
    buf = np.zeros(48000, dtype=np.int16)
    buf[start:start + len(data)] = data
    sc = float(sess.run(None, {input_name: F.embed_clips(buf[None, :], batch_size=1)[0][None]})[0][0][0])
    print(f"neg {name}: score={sc:.4f}")
