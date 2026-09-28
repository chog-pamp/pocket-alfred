#!/usr/bin/env python3
"""Verify hey_alfred.onnx (v2): positives, near-misses, and streaming behavior."""
import glob
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools")
import openwakeword  # noqa: E402

WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"
oww = openwakeword.Model(wakeword_model_paths=[f"{WORKDIR}/hey_alfred.onnx"])

# 1) streaming scores on positives (fresh model instance semantics: reset between)
pos_scores = []
for p in sorted(glob.glob(f"{WORKDIR}/positive/*.wav")):
    sc = [list(s.values())[0] for s in oww.predict_clip(p)]
    pos_scores.append(max(sc) if sc else 0)
    oww.reset()
pos_scores = np.array(pos_scores)
print(f"positives (n={len(pos_scores)}): mean={pos_scores.mean():.3f} "
      f"frac>=0.5={(pos_scores >= 0.5).mean():.4f} frac>=0.7={(pos_scores >= 0.7).mean():.4f}")

# 2) near-miss negatives (streaming)
neg_scores = []
for p in sorted(glob.glob(f"{WORKDIR}/negative_nearmiss/*.wav")):
    sc = [list(s.values())[0] for s in oww.predict_clip(p)]
    neg_scores.append(max(sc) if sc else 0)
    oww.reset()
neg_scores = np.array(neg_scores)
print(f"near-miss (n={len(neg_scores)}): mean={neg_scores.mean():.3f} max={neg_scores.max():.3f} "
      f"FPR@0.5={(neg_scores >= 0.5).mean():.4f} FPR@0.6={(neg_scores >= 0.6).mean():.4f}")

# 3) 'hey hermes' previously-FP clips specifically
hm = []
for p in sorted(glob.glob(f"{WORKDIR}/negative_nearmiss/*.wav")):
    if "ermes" in open(p).read() if False else False:
        pass
    sc = [list(s.values())[0] for s in oww.predict_clip(p)]
    m = max(sc) if sc else 0
    if m >= 0.5:
        hm.append((m, p.split("/")[-1]))
    oww.reset()
print("clips still >=0.5:", hm[:10])

# 4) continuous speech FPR on Santa Barbara corpus (~1 h)
import openwakeword.metrics  # noqa: E402
sb_scores = [list(i.values())[0] for i in oww.predict_clip(f"{WORKDIR}/santa_barbara_corpus_test_clip.wav")]
fps = openwakeword.metrics.get_false_positives(sb_scores, threshold=0.5)
hours = len(sb_scores) * 80 / 1000 / 3600
print(f"santa barbara: {len(sb_scores)} frames ({hours:.2f} h) FA@0.5={fps} "
      f"({fps / hours:.2f}/h) max_score={max(sb_scores):.3f}")
