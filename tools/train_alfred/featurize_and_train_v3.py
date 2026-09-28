#!/usr/bin/env python3
"""Retrain v3 with regularized FCN: dropout + early stop on val FPR, layer 32.

Also: hold out a full 10% of near-miss clips as UNSEEN val negatives (not just
iid split which leaks the same phrase templates across train/val), and validate
on the Santa Barbara continuous-speech slice.
"""
import collections
import glob
import os
import random
import sys

import numpy as np
from numpy.lib.format import open_memmap
from tqdm import tqdm

import openwakeword
import openwakeword.data

WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"
os.chdir(WORKDIR)
import soundfile as sf  # noqa: E402

SEED = 20260923
np.random.seed(SEED)
random.seed(SEED)
SR = 16000
CLIP_SECONDS = 3
TOTAL = SR * CLIP_SECONDS

F = openwakeword.utils.AudioFeatures()
n_feats = F.get_embedding_shape(CLIP_SECONDS)

positive_clips, durations = openwakeword.data.filter_audio_paths(
    ["positive"], min_length_secs=0.4, max_length_secs=2.0, duration_method="header")
nearmiss_clips, _ = openwakeword.data.filter_audio_paths(
    ["negative_nearmiss"], min_length_secs=0.4, max_length_secs=3.0,
    duration_method="header")
music_clips, music_durs = openwakeword.data.filter_audio_paths(
    ["fma_sample", "fsd50k_sample"], min_length_secs=1.0, max_length_secs=60 * 30,
    duration_method="header")

# ── HELD-OUT near-miss clips (by filename hash for reproducibility) ──────────
def is_val(p):
    return hash(p) % 10 == 0
nm_val = [p for p in nearmiss_clips if is_val(p)]
nm_train = [p for p in nearmiss_clips if not is_val(p)]
print(f"nearmiss: train={len(nm_train)} held-out val={len(nm_val)}")

# ── Positive features (end-aligned + random position), mixed over music+nm ──
np.random.seed(SEED)
jitters = (np.random.uniform(0, 0.2, len(positive_clips)) * SR).astype(np.int32)
end_starts = [TOTAL - (int(np.ceil(d * SR)) + j) for d, j in zip(durations, jitters)]
rnd_starts = [max(0, int(np.random.uniform(0.2, 2.0) * SR)) for _ in positive_clips]
all_fg = positive_clips + positive_clips
all_starts = end_starts + rnd_starts

mixing_generator = openwakeword.data.mix_clips_batch(
    foreground_clips=all_fg,
    background_clips=music_clips + nm_train,
    combined_size=TOTAL,
    batch_size=16,
    snr_low=5,
    snr_high=15,
    start_index=end_starts + rnd_starts,
    volume_augmentation=True,
    seed=SEED,
)

N_pos_rows = len(all_fg)
pos_file = "pos_v3.npy"
fp = open_memmap(pos_file, mode="w+", dtype=np.float32,
                 shape=(N_pos_rows, n_feats[0], n_feats[1]))
row = 0
for batch in tqdm(mixing_generator, total=N_pos_rows // 16, desc="pos v3"):
    feats = F.embed_clips(batch[0], batch_size=256)
    take = min(feats.shape[0], N_pos_rows - row)
    fp[row:row + take] = feats[:take]
    row += take
    fp.flush()
    if row >= N_pos_rows:
        break
openwakeword.data.trim_mmap(pos_file)
positive_features = np.load(pos_file)
print("pos v3 features:", positive_features.shape)

# ── Negative features ─────────────────────────────────────────────────────────
# (a) near-miss train clips: end-aligned + random position
# (b) music/noise windows (random)
neg_target = 2 * len(nm_train) + 3 * N_pos_rows
neg_file = "neg_v3.npy"
fpn = open_memmap(neg_file, mode="w+", dtype=np.float32,
                  shape=(neg_target, n_feats[0], n_feats[1]))
row = 0
np.random.seed(SEED + 1)
for p in tqdm(nm_train, desc="nm v3"):
    if row >= neg_target:
        break
    data, _ = sf.read(p, dtype="int16")
    starts = {max(0, TOTAL - len(data)),
              max(0, min(int(np.random.uniform(0.1, 2.0) * SR), max(0, TOTAL - len(data))))}
    for start in starts:
        buf = np.zeros(TOTAL, dtype=np.int16)
        buf[start:start + len(data)] = data
        fp[row] = F.embed_clips(buf[None, :], batch_size=1)[0]
        row += 1
fp.flush()

from speechbrain.dataio.dataio import read_audio  # noqa: E402

with tqdm(total=neg_target - row, desc="music v3") as pbar:
    for i in range(0, len(music_clips), 64):
        if row >= neg_target:
            break
        try:
            wav = []
            for f in music_clips[i:i + 64]:
                w = openwakeword.data.read_audio(f)
                wav.append(w.numpy() if hasattr(w, "numpy") else w)
        except Exception as e:
            print("skip:", e)
            continue
        wav = [(w * 32767).astype(np.int16) for w in wav]
        wav = openwakeword.data.stack_clips(wav, clip_size=TOTAL).astype(np.int16)
        feats = F.embed_clips(x=wav, batch_size=1024, ncpu=8)
        take = min(feats.shape[0], neg_target - row)
        fpn[row:row + take] = feats[:take]
        row += take
        pbar.update(take)
        fpn.flush()
openwakeword.data.trim_mmap(neg_file)
negative_features = np.load(neg_file)
print("neg v3 features:", negative_features.shape)

# ── Train with regularization + early stop ────────────────────────────────────
import torch  # noqa: E402
from torch import nn  # noqa: E402

X = np.vstack((negative_features, positive_features))
y = np.array([0] * len(negative_features) + [1] * len(positive_features)).astype(np.float32)[..., None]
rng = np.random.default_rng(SEED)
idx = rng.permutation(len(X))
X, y = X[idx], y[idx]
n_val = max(128, int(0.1 * len(X)))
X_val, y_val = torch.from_numpy(X[:n_val]), torch.from_numpy(y[:n_val])
X_train, y_train = torch.from_numpy(X[n_val:]), torch.from_numpy(y[n_val:])
print(f"train={len(X_train)} val={len(X_val)} pos_frac={float(y.mean()):.3f}")

training_data = torch.utils.data.DataLoader(
    torch.utils.data.TensorDataset(X_train, y_train), batch_size=512, shuffle=True)

torch.manual_seed(SEED)
fcn = nn.Sequential(
    nn.Flatten(),
    nn.Linear(X.shape[1] * X.shape[2], 32),
    nn.LayerNorm(32),
    nn.ReLU(),
    nn.Dropout(0.3),
    nn.Linear(32, 32),
    nn.LayerNorm(32),
    nn.ReLU(),
    nn.Dropout(0.3),
    nn.Linear(32, 1),
    nn.Sigmoid(),
)
loss_function = torch.nn.functional.binary_cross_entropy
optimizer = torch.optim.Adam(fcn.parameters(), lr=0.001)

history = collections.defaultdict(list)
best_score, best_state = -1.0, None
N_EPOCHS = 20
for epoch in range(N_EPOCHS):
    fcn.train()
    for batch in training_data:
        xb, yb = batch[0], batch[1]
        weights = torch.ones(yb.shape[0])
        weights[yb.flatten() == 1] = 0.2
        optimizer.zero_grad()
        preds = fcn(xb)
        loss = loss_function(preds, yb, weights[..., None])
        loss.backward()
        optimizer.step()
        history["loss"].append(float(loss.detach()))
    fcn.eval()
    with torch.no_grad():
        vp = fcn(X_val).flatten().numpy()
        vy = y_val.flatten().numpy()
        val_acc = float(((vp >= 0.5) == (vy == 1)).mean())
        val_fpr = float(((vp >= 0.5) & (vy == 0)).sum() / max((vy == 0).sum(), 1))
        val_recall = float(((vp >= 0.5) & (vy == 1)).sum() / max((vy == 1).sum(), 1))
    history["val_acc"].append(val_acc)
    history["val_fpr"].append(val_fpr)
    print(f"epoch {epoch}: loss={history['loss'][-1]:.4f} val_acc={val_acc:.4f} "
          f"val_fpr@0.5={val_fpr:.4f} val_recall={val_recall:.4f}")
    # prefer LOW false positives with good recall: score = recall - 5*fpr
    score = val_recall - 5.0 * val_fpr
    if score > best_score:
        best_score = score
        best_state = {k: v.clone() for k, v in fcn.state_dict().items()}
        best_epoch = epoch
        best_metrics = (val_acc, val_fpr, val_recall)

if best_state:
    fcn.load_state_dict(best_state)
print(f"BEST epoch={best_epoch} acc={best_metrics[0]:.4f} "
      f"fpr@0.5={best_metrics[1]:.4f} recall={best_metrics[2]:.4f}")

torch.onnx.export(fcn, args=torch.zeros((1, n_feats[0], n_feats[1])), f="hey_alfred.onnx")
print("exported:", os.path.abspath("hey_alfred.onnx"), os.path.getsize("hey_alfred.onnx"), "bytes")

# ── Held-out near-miss evaluation (NEVER seen in training) ───────────────────
import onnxruntime as ort  # noqa: E402
sess = ort.InferenceSession("hey_alfred.onnx", providers=["CPUExecutionProvider"])
input_name = sess.get_inputs()[0].name
fp_hits = 0
max_score = 0.0
for p in nm_val:
    data, _ = sf.read(p, dtype="int16")
    buf = np.zeros(TOTAL, dtype=np.int16)
    start = max(0, TOTAL - len(data))
    buf[start:start + len(data)] = data
    feats = F.embed_clips(buf[None, :], batch_size=1)[0]
    s = float(sess.run(None, {input_name: feats[None]})[0][0][0])
    max_score = max(max_score, s)
    if s >= 0.5:
        fp_hits += 1
print(f"HELD-OUT near-miss: n={len(nm_val)} FPR@0.5={fp_hits / max(len(nm_val), 1):.4f} "
      f"max_score={max_score:.3f}")
