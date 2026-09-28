#!/usr/bin/env python3
"""Verify hey_alfred.onnx with openWakeWord runtime:
- positives: synthetic 'hey alfred' clips (held-out list) -> mean/max score
- negatives: near-miss TTS + 1 h Santa Barbara speech -> FPR at threshold 0.5
"""
import glob
import sys

import numpy as np
import scipy.io.wavfile

sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools")
import openwakeword
from openwakeword.model import Model

MODEL = "/home/leo/homelab/pocket-alfred/tools/train_alfred/hey_alfred.onnx"
WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"

oww = openwakeword.Model(wakeword_model_paths=[MODEL])
label = list(oww.models.keys())[0]
print("model label:", label)


def frame_scores(path):
    scores = [list(s.values())[0] for s in oww.predict_clip(path)]
    oww.reset()
    return scores


# ── Positives ──
pos_files = sorted(glob.glob(f"{WORKDIR}/positive/*.wav"))
pos_scores = []
for p in pos_files:
    sc = [list(s.values())[0] for s in oww.predict_clip(p)]
    if sc:
        pos_scores.append(max(sc))
    oww.reset()
pos_scores = np.array(pos_scores)
print(f"positives: n={len(pos_scores)} mean={pos_scores.mean():.3f} "
      f"median={np.median(pos_scores):.3f} frac>=0.5={(pos_scores >= 0.5).mean():.3f} "
      f"frac>=0.7={(pos_scores >= 0.7).mean():.3f}")

# ── Near-miss negatives ──
neg_files = sorted(glob.glob(f"{WORKDIR}/negative_nearmiss/*.wav"))
nm_scores = []
for p in neg_files:
    sc = [list(s.values())[0] for s in oww.predict_clip(p)]
    if sc:
        nm_scores.append(max(sc))
nm_scores = np.array(nm_scores)
nm_fpr = float((nm_scores >= 0.5).mean())
print(f"near-miss negatives: n={len(nm_scores)} mean={nm_scores.mean():.3f} "
      f"max={nm_scores.max():.3f} FPR@0.5={nm_fpr:.4f}")

# ── Continuous speech FPR (Santa Barbara corpus, ~1 h) ──
sb_path = f"{WORKDIR}/santa_barbara_corpus_test_clip.wav"
sb_scores = [list(s.values())[0] for s in oww.predict_clip(sb_path)]
fps = openwakeword.metrics.get_false_positives(sb_scores, threshold=0.5)
hours = len(sb_scores) * 80 / 1000 / 3600
print(f"santa barbara: {len(sb_scores)} frames ({hours:.2f} h) "
      f"false accepts@0.5={fps} -> {fps / hours:.2f} /hour")
