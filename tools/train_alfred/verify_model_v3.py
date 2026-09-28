#!/usr/bin/env python3
"""Verify v3: streaming near-miss FPR, positives, and continuous speech."""
import glob
import sys

import numpy as np

sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools")
import openwakeword  # noqa: E402

WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"
oww = openwakeword.Model(wakeword_model_paths=[f"{WORKDIR}/hey_alfred.onnx"])

pos = []
for p in sorted(glob.glob(f"{WORKDIR}/positive/*.wav")):
    sc = [list(s.values())[0] for s in oww.predict_clip(p)]
    pos.append(max(sc) if sc else 0)
    oww.reset()
pos = np.array(pos)
print(f"positives (n={len(pos)}): mean={pos.mean():.3f} frac>=0.5={(pos >= 0.5).mean():.4f}")

neg = []
for p in sorted(glob.glob(f"{WORKDIR}/negative_nearmiss/*.wav")):
    sc = [list(s.values())[0] for s in oww.predict_clip(p)]
    neg.append(max(sc) if sc else 0)
    oww.reset()
neg = np.array(neg)
print(f"near-miss streaming (n={len(neg)}): mean={neg.mean():.3f} max={neg.max():.3f} "
      f"FPR@0.5={(neg >= 0.5).mean():.4f} FPR@0.6={(neg >= 0.6).mean():.4f}")

import openwakeword.metrics  # noqa: E402
sb = [list(i.values())[0] for i in oww.predict_clip(f"{WORKDIR}/santa_barbara_corpus_test_clip.wav")]
fps = openwakeword.metrics.get_false_positives(sb, threshold=0.5)
hours = len(sb) * 80 / 1000 / 3600
print(f"santa barbara: {len(sb)} frames ({hours:.2f} h) FA@0.5={fps} ({fps / hours:.2f}/h) "
      f"max={max(sb):.3f}")
