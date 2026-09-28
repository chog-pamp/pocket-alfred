#!/usr/bin/env python3
"""Diagnose near-miss clip scores: are the raw preds ever below 0.5 mid-clip?"""
import glob
import sys

import numpy as np

sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools")
import openwakeword

MODEL = "/home/leo/homelab/pocket-alfred/tools/train_alfred/hey_alfred.onnx"
WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"
import onnxruntime as ort
import onnx
m = onnx.load(MODEL)
print("ONNX inputs:", [(i.name, i.type) for i in m.graph.input])
print("ONNX outputs:", [(o.name, o.type) for o in m.graph.output])
oww = openwakeword.Model(wakeword_model_paths=[MODEL])
print("model_inputs (frames):", oww.model_inputs)
print("model_outputs:", oww.model_outputs)

neg_files = sorted(glob.glob(f"{WORKDIR}/negative_nearmiss/*.wav"))[:20]
for p in neg_files[:8]:
    sc = [list(s.values())[0] for s in oww.predict_clip(p)]
    oww.reset()
    print(f"{p.split('/')[-1]}: len={len(sc)} scores={[round(s,3) for s in sc]}")
