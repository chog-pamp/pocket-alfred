#!/usr/bin/env python3
"""Featurize + train + export a custom openWakeWord model for 'hey alfred'.

Follows the openWakeWord training_models.ipynb flow:
  melspectrogram->embedding features (frozen) -> small FCN classifier -> ONNX export.
Negative data: openwakeword-sampled fma (music) + fsd50k (noise) + generated near-miss
TTS phrases, mixed at random SNR with positives for augmentation.
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
print("embedding shape per 3s clip:", n_feats)

# ── Gather negative clip paths ────────────────────────────────────────────────
negative_clips, negative_durations = openwakeword.data.filter_audio_paths(
    ["fma_sample", "fsd50k_sample", "negative_nearmiss"],
    min_length_secs=1.0,
    max_length_secs=60 * 30,
    duration_method="header",
)
print(f"{len(negative_clips)} negative clips after filtering "
      f"(~{sum(negative_durations)/3600:.2f} hours)")

# ── Positive clips ───────────────────────────────────────────────────────────
positive_clips, durations = openwakeword.data.filter_audio_paths(
    ["positive"],
    min_length_secs=0.4,
    max_length_secs=2.0,
    duration_method="header",
)
print(f"{len(positive_clips)} positive clips after filtering")

# Align each positive clip's END with the end of the window (0-200 ms jitter),
# so the model peaks right after the phrase is spoken.
jitters = (np.random.uniform(0, 0.2, len(positive_clips)) * SR).astype(np.int32)
starts = [TOTAL - (int(np.ceil(d * SR)) + j) for d, j in zip(durations, jitters)]

# ── Positive features: mix with background at random SNR ─────────────────────
batch_size = 16
mixing_generator = openwakeword.data.mix_clips_batch(
    foreground_clips=positive_clips,
    background_clips=negative_clips,
    combined_size=TOTAL,
    batch_size=batch_size,
    snr_low=5,
    snr_high=15,
    start_index=starts,
    volume_augmentation=True,
    seed=SEED,
)

N_total = len(positive_clips)
pos_file = "hey_alfred_positive_features.npy"
fp = open_memmap(pos_file, mode="w+", dtype=np.float32,
                 shape=(N_total, n_feats[0], n_feats[1]))
row = 0
for batch in tqdm(mixing_generator, total=N_total // batch_size, desc="pos features"):
    mixed = batch[0]
    feats = F.embed_clips(mixed, batch_size=256)
    fp[row:row + feats.shape[0], :, :] = feats
    row += feats.shape[0]
    fp.flush()
    if row >= N_total:
        break
openwakeword.data.trim_mmap(pos_file)
print("positive features:", np.load(pos_file, mmap_mode="r").shape)

# ── Negative features: window the background corpus into 3 s clips ───────────
batch_size = 64
# Cap negative feature rows: keep the set roughly balanced (negs ~ 2x pos here;
# positives were mixed over this same corpus too).
N_max_neg = min(int(sum(negative_durations) // CLIP_SECONDS), 4 * N_total)
neg_file = "negative_features.npy"
fpn = open_memmap(neg_file, mode="w+", dtype=np.float32,
                  shape=(N_max_neg, n_feats[0], n_feats[1]))

import torchaudio  # noqa: E402  (speechbrain read_audio fallback)
from speechbrain.dataio.dataio import read_audio  # noqa: E402

row = 0
with tqdm(total=N_max_neg, desc="neg features") as pbar:
    for i in range(0, len(negative_clips), batch_size):
        if row >= N_max_neg:
            break
        batch_files = negative_clips[i:i + batch_size]
        try:
            wav_data = [read_audio(f).numpy() for f in batch_files]
        except Exception as e:
            print("skip batch:", e)
            continue
        wav_data = [ (w * 32767).astype(np.int16) for w in wav_data ]
        wav_data = openwakeword.data.stack_clips(wav_data, clip_size=TOTAL).astype(np.int16)
        feats = F.embed_clips(x=wav_data, batch_size=1024, ncpu=8)
        take = min(feats.shape[0], N_max_neg - row)
        fpn[row:row + take, :, :] = feats[:take]
        row += take
        pbar.update(take)
        fpn.flush()
openwakeword.data.trim_mmap(neg_file)
negative_features = np.load(neg_file)
print("negative features:", negative_features.shape)

# ── Train the small FCN ──────────────────────────────────────────────────────
import torch  # noqa: E402
from torch import nn  # noqa: E402

positive_features = np.load(pos_file)
X = np.vstack((negative_features, positive_features))
y = np.array([0] * len(negative_features) + [1] * len(positive_features)).astype(np.float32)[..., None]

# shuffle before splitting so the val split is iid
rng = np.random.default_rng(SEED)
idx = rng.permutation(len(X))
X, y = X[idx], y[idx]
n_val = max(64, int(0.1 * len(X)))
X_val, y_val = torch.from_numpy(X[:n_val]), torch.from_numpy(y[:n_val])
X_train, y_train = torch.from_numpy(X[n_val:]), torch.from_numpy(y[n_val:])
print(f"train={len(X_train)} val={len(X_val)} pos_frac={float(y.mean()):.3f}")

batch_size = 512

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

# Balanced sampling: WeightedRandomSampler draws positives 4x more often than
# negatives each epoch, so the 80/20 class imbalance doesn't drown the signal.
all_labels = torch.from_numpy(y[n_val:].flatten())
sample_weights = torch.where(all_labels == 1, torch.tensor(4.0), torch.tensor(1.0))
sampler = torch.utils.data.WeightedRandomSampler(
    weights=sample_weights, num_samples=len(all_labels), replacement=True,
)
training_data = torch.utils.data.DataLoader(
    torch.utils.data.TensorDataset(X_train, y_train),
    batch_size=batch_size, sampler=sampler,
)

N_EPOCHS = 12
history = collections.defaultdict(list)
best_val_acc, best_state = 0.0, None
for epoch in range(N_EPOCHS):
    fcn.train()
    for batch in training_data:
        xb, yb = batch[0], batch[1]
        weights = torch.ones(yb.shape[0])
        weights[yb.flatten() == 1] = 0.1  # upweight negatives (FPR control)
        optimizer.zero_grad()
        preds = fcn(xb)
        loss = loss_function(preds, yb, weights[..., None])
        loss.backward()
        optimizer.step()
        history["loss"].append(float(loss.detach()))
    # validation
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
          f"val_fpr@0.5={val_acc and val_fpr:.4f} val_recall={val_recall:.4f}")
    if val_acc > best_val_acc:
        best_val_acc = val_acc
        best_state = {k: v.clone() for k, v in fcn.state_dict().items()}

if best_state:
    fcn.load_state_dict(best_state)

# ── Export to ONNX ───────────────────────────────────────────────────────────
output_path = os.path.join(WORKDIR, "hey_alfred.onnx")
torch.onnx.export(fcn, args=torch.zeros((1, n_feats[0], n_feats[1])), f=output_path)
print("exported:", output_path, os.path.getsize(output_path), "bytes")
print("BEST val_acc:", best_val_acc)
print("FINAL val_fpr@0.5:", history["val_fpr"][-1])
