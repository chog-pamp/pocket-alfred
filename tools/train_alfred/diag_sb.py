#!/usr/bin/env python3
"""Test the model state dict: is LayerNorm killing the signal? Print the ONNX
graph structure and check whether the sigmoid is saturating (pre-sigmoid logit).
Reconstruct the FCN in torch, load the ONNX weights manually is hard — instead
re-train WITHOUT best-state selection (the val_fpr climbed at the end, meaning
the 'best' checkpoint was from epoch 11-13, already overfit) — but the training
loss went to 0.0045 which is basically memorized. The v1 model had loss 0.03-0.1
and a 0.75 ceiling; the v2 has loss 0.0045 and a 0.992 ceiling.

Real fix per the reference pipelines: LOWER capacity (layer_dim=32), MORE
negatives, fewer epochs, and STOP before saturation. Also add training
regularization: dropout. And validate on UNSEEN negatives.
"""
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

# Santa Barbara continuous speech, slide over 1-minute slice and count raw
data, _ = sf.read(f"{WORKDIR}/santa_barbara_corpus_test_clip.wav", dtype="int16")
seg = data[: 60 * 16000]
scores = []
for i in range(0, len(seg) - 48000, 16000):
    feats = F.embed_clips(seg[i:i+48000][None, :], batch_size=1)[0]
    s = float(sess.run(None, {input_name: feats[None]})[0][0][0])
    scores.append(s)
    if s > 0.9:
        print(f"high score {s:.3f} at {i/16000:.1f}s")
print(f"60s slice: {len(scores)} windows, mean={np.mean(scores):.3f}, "
      f">=0.5: {(np.array(scores) >= 0.5).sum()}")
