#!/usr/bin/env python3
"""Raw ONNX probe: end-aligned near-miss vs positive vs shifted window."""
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


def raw(feats):
    return float(sess.run(None, {input_name: feats[None]})[0][0][0])


p = f"{WORKDIR}/negative_nearmiss/nearmiss_0000.wav"
data, _ = sf.read(p, dtype="int16")
buf = np.zeros(48000, dtype=np.int16)
buf[-len(data):] = data
feats = F.embed_clips(buf[None, :], batch_size=1)[0]
print("nearmiss end-aligned raw:", float(sess.run(None, {input_name: feats[None]})[0][0][0]))

pp = sorted(glob.glob(f"{WORKDIR}/positive/*.wav"))[0]
data, _ = sf.read(pp, dtype="int16")
buf = np.zeros(48000, dtype=np.int16)
buf[-len(data):] = data
featsp = F.embed_clips(buf[None, :], batch_size=1)[0]
print("positive end-aligned raw:", float(sess.run(None, {input_name: featsp[None]})[0][0][0]))

f_shift = np.vstack([feats[1:], feats[-1:]])[None]
print("nearmiss shifted-1:", float(sess.run(None, {input_name: f_shift})[0][0][0]))
