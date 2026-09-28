#!/usr/bin/env python3
"""Score the BUNDLED hey_hermes.onnx on our positive/negative sets as a baseline."""
import glob
import sys

import numpy as np

sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools")
import openwakeword

MODEL = "/home/leo/.hermes/hermes-agent/tools/wakewords/hey_hermes.onnx"
WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"
oww = openwakeword.Model(wakeword_model_paths=[MODEL])

pos_files = sorted(glob.glob(f"{WORKDIR}/positive/*.wav"))
neg_files = sorted(glob.glob(f"{WORKDIR}/negative_nearmiss/*.wav"))

ps, ns = [], []
for p in pos_files:
    sc = [list(s.values())[0] for s in oww.predict_clip(p)]
    ps.append(max(sc) if sc else 0)
    oww.reset()
for p in neg_files:
    sc = [list(s.values())[0] for s in oww.predict_clip(p)]
    ns.append(max(sc) if sc else 0)
    oww.reset()
ps, ns = np.array(ps), np.array(ns)
print(f"hey_hermes model on 'hey alfred' clips: mean={ps.mean():.3f} frac>=0.5={(ps>=0.5).mean():.3f}")
print(f"hey_hermes model on near-miss clips: mean={ns.mean():.3f} max={ns.max():.3f} FPR@0.5={(ns>=0.5).mean():.3f}")
