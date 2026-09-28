#!/usr/bin/env python3
"""Retrain v2: fix the 'speech-end detector' failure.

Changes vs v1:
- near-miss negatives are ALSO end-aligned as 3s windows (explicit negative rows),
  so 'any speech ending now' is taught as negative.
- positives get two alignments: end-aligned + random position (phrase anywhere
  in the last 2 s), so the model learns the phrase, not its position.
- positives are mixed over music/noise AND near-miss speech (harder augmentation).
- validation includes held-out near-miss clips scored end-aligned; require
  FPR@0.5 < 0.05 there.
"""
import collections
import os
import random
import sys

import numpy as np
from numpy.lib.format import open_memmap
from tqdm import tqdm

import openwakeword
import openwakeword.data

sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools/train_alfred")
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
print("embedding shape:", n_feats)

nearmiss_clips, _ = openwakeword.data.filter_audio_paths(
    ["negative_nearmiss"], min_length_secs=0.3, max_length_secs=3.0,
    duration_method="header")
music_clips, music_durs = openwakeword.data.filter_audio_paths(
    ["fma_sample", "fsd50k_sample"], min_length_secs=1.0,
    max_length_secs=60 * 30, duration_method="header")
positive_clips, durations = openwakeword.data.filter_audio_paths(
    ["positive"], min_length_secs=0.4, max_length_secs=2.0, duration_method="header")
print(f"{len(positive_clips)} positives, {len(nearmiss_clips)} near-miss, {len(music_clips)} music/noise")

# ── Positive features: end-aligned + random-position, mixed over music+speech ─
np.random.seed(SEED)
jitters = (np.random.uniform(0, 0.2, len(positive_clips)) * SR).astype(np.int32)
end_starts = [TOTAL - (int(np.ceil(d * SR)) + j) for d, j in zip(durations, jitters)]
rnd_starts = [max(0, int(np.random.uniform(0.2, 2.0) * SR)) for _ in positive_clips]
all_fg = positive_clips + positive_clips
all_starts = end_starts + rnd_starts

pos_file = "hey_alfred_positive_features_v2.npy"
N_pos_rows = len(all_fg)
fp = open_memmap(pos_file, mode="w+", dtype=np.float32,
                 shape=(N_pos_rows, n_feats[0], n_feats[1]))
mixing_generator = openwakeword.data.mix_clips_batch(
    foreground_clips=all_fg,
    background_clips=music_clips + nearmiss_clips,
    combined_size=TOTAL,
    batch_size=16,
    snr_low=5,
    snr_high=15,
    start_index=all_starts,
    volume_augmentation=True,
    seed=SEED,
)
row = 0
for batch in tqdm(mixing_generator, total=N_pos_rows // 16, desc="pos v2"):
    feats = F.embed_clips(batch[0], batch_size=256)
    take = min(feats.shape[0], N_pos_rows - row)
    fp[row:row + take] = feats[:take]
    row += take
    fp.flush()
    if row >= N_pos_rows:
        break
openwakeword.data.trim_mmap(pos_file)
positive_features = np.load(pos_file)
print("positive v2 features:", positive_features.shape)

# ── Negative features: music/noise windows + END-ALIGNED near-miss windows ────
neg_file = "negative_features_v2.npy"
# rows: 2x per nearmiss (end-aligned + random offset) + music windows to fill
neg_rows_target = 2 * len(nearmiss_clips) + 2 * N_pos_rows
fpn = open_memmap(neg_file, mode="w+", dtype=np.float32,
                  shape=(neg_rows_target, n_feats[0], n_feats[1]))

row = 0
# (a) near-miss clips END-aligned (and a random-position copy)
np.random.seed(SEED + 1)
for p in tqdm(nearmiss_clips, desc="nearmiss v2"):
    if row >= neg_rows_target:
        break
    data, _ = sf.read(p, dtype="int16")
    for start in (max(0, TOTAL - len(data)), max(0, min(int(np.random.uniform(0.1, 2.0) * SR), TOTAL - len(data)))):
        buf = np.zeros(TOTAL, dtype=np.int16)
        if len(data) <= TOTAL:
            buf[start:start + len(data)] = data
        else:
            buf[:] = data[:TOTAL]
        feats = F.embed_clips(buf[None, :], batch_size=1)
        if row < neg_rows_target:
            fp[row] = feats[0]
            row += 1
fp.flush()

# (b) music/noise windows to reach target (random slices)
from speechbrain.dataio.dataio import read_audio  # noqa: E402

batch_size = 64
with tqdm(total=neg_rows_target - row, desc="neg v2") as pbar:
    for i in range(0, len(music_clips), 64):
        if row >= neg_rows_target:
            break
        batch_files = music_clips[i:i + 64]
        try:
            wav_data = []
            for f in music_clips[i:i + 64]:
                w = openwakeword.data.read_audio(f)
                if hasattr(w, "numpy"):
                    w = w.numpy()
                wav_data.append(w)
        except Exception as e:
            print("skip:", e)
            continue
        wav_data = [(w * 32767).astype(np.int16) for w in wav_data]
        wav_data = openwakeword.data.stack_clips(wav_data, clip_size=TOTAL).astype(np.int16)
        feats = F.embed_clips(x=wav_data, batch_size=1024, ncpu=8)
        take = min(feats.shape[0], neg_rows_target - row)
        fpn[row:row + take] = feats[:take]
        row += take
        pbar.update(take)
        fp.flush()
openwakeword.data.trim_mmap(neg_file)
negative_features = np.load(neg_file)
print("negative v2 features:", negative_features.shape)

# ── Train ────────────────────────────────────────────────────────────────────
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

batch_size = 512
training_data = torch.utils.data.DataLoader(
    torch.utils.data.TensorDataset(X_train, y_train),
    batch_size=batch_size, shuffle=True,
)

layer_dim = 64
torch.manual_seed(SEED)
fcn = nn.Sequential(
    nn.Flatten(),
    nn.Linear(X.shape[1] * X.shape[2], layer_dim),
    nn.LayerNorm(layer_dim),
    nn.ReLU(),
    nn.Linear(layer_dim, layer_dim),
    nn.LayerNorm(layer_dim),
    nn.ReLU(),
    nn.Linear(layer_dim, 1),
    nn.Sigmoid(),
)
loss_function = torch.nn.functional.binary_cross_entropy
optimizer = torch.optim.Adam(fcn.parameters(), lr=0.001)

N_EPOCHS = 15
history = collections.defaultdict(list)
best_val_acc, best_state = 0.0, None
for epoch in range(N_EPOCHS):
    fcn.train()
    for batch in training_data:
        xb, yb = batch[0], batch[1]
        optimizer.zero_grad()
        preds = fcn(xb)
        loss = loss_function(preds, yb)
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
    if val_acc > best_val_acc:
        best_val_acc = val_acc
        best_state = {k: v.clone() for k, v in fcn.state_dict().items()}

if best_state:
    fcn.load_state_dict(best_state)

output_path = "hey_alfred.onnx"
torch.onnx.export(fcn, args=torch.zeros((1, n_feats[0], n_feats[1])), f=output_path)
print("exported:", os.path.abspath(output_path), os.path.getsize(output_path), "bytes")
print("BEST val_acc:", best_val_acc)
print("FINAL val_fpr@0.5:", history["val_fpr"][-1])
