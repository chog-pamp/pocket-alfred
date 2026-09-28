#!/usr/bin/env python3
"""Sanity: predict scores for the v3 model on the exact TRAINED feature windows.

If train features score high for pos and low for neg but streaming scores high
for everything, the distribution shift is the problem. Use the raw ONNX on the
v3 TRAIN feature npy files directly: pos_v3 rows should be >=0.5 and neg_v3
rows < 0.5 (that's what training optimized).
"""
import numpy as np
import onnxruntime as ort

WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"
sess = ort.InferenceSession(f"{WORKDIR}/hey_alfred.onnx", providers=["CPUExecutionProvider"])
input_name = sess.get_inputs()[0].name

pos = np.load(f"{WORKDIR}/pos_v3.npy")
neg = np.load(f"{WORKDIR}/neg_v3.npy")
print("pos", pos.shape, "neg", neg.shape)

ps = np.array([sess.run(None, {input_name: pos[i:i+1].astype(np.float32)})[0][0][0] for i in range(500)])
ns = np.array([sess.run(None, {input_name: neg[i:i+1].astype(np.float32)})[0][0][0] for i in range(1000)])
print(f"train-pos: mean={ps.mean():.3f} frac>=0.5={(ps >= 0.5).mean():.3f}")
print(f"train-neg: mean={ns.mean():.3f} frac>=0.5={(ns >= 0.5).mean():.3f}")

# Now STREAM the same near-miss clip and check its feature windows
import sys as _s
_s.path.insert(0, "/home/leo/homelab/pocket-alfred/tools")
import openwakeword  # noqa: E402
oww = openwakeword.Model(wakeword_model_paths=[f"{WORKDIR}/hey_alfred.onnx"])
sc = [list(i.values())[0] for i in oww.predict_clip(f"{WORKDIR}/negative_nearmiss/nearmiss_0000.wav")]
print("stream scores nearmiss_0000:", [round(float(x), 3) for x in sc[15:30]])
