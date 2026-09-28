#!/usr/bin/env python3
"""v4: train on STREAMING-style features so train == inference distribution.

Batch (embed_clips) and streaming (Model.predict) features differ (corr ~0.885)
because streaming carries ~1 s of real audio context while batch zero-pads.
v1-v3 aced batch validation but fired on everything when streamed. v4 trains on
features generated exactly the way openwakeword.Model does at inference.

Positives: mixed over music/noise/near-miss at random SNR, phrase placed with
random lead-in so phrase-end spans many window positions. Every 80 ms streaming
step whose window ends 0-200 ms after the phrase end is labeled 1; all other
steps (including all negative windows) labeled 0.
"""
import collections
import glob
import os
import random
import sys

import numpy as np
import soundfile as sf
from tqdm import tqdm

sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools")
import openwakeword  # noqa: E402
import openwakeword.data  # noqa: E402

WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"
os.chdir(WORKDIR)
SEED = 20260923
np.random.seed(SEED)
random.seed(SEED)
SR = 16000
TOTAL = 48000
FRAME = 1280

positive_clips = sorted(glob.glob("positive/*.wav"))
nearmiss_clips = sorted(glob.glob("negative_nearmiss/*.wav"))
mc, md = openwakeword.data.filter_audio_paths(
    ["fma_sample", "fsd50k_sample"], min_length_secs=1.0,
    max_length_secs=60 * 30, duration_method="header")
music_clips = list(mc)

nm_val = [p for p in nearmiss_clips if hash(p) % 10 == 0]
nm_train = [p for p in nearmiss_clips if hash(p) % 10 != 0]
print(f"positives={len(positive_clips)} nearmiss train={len(nm_train)} val={len(nm_val)} "
      f"music={len(music_clips)}")

_all_bg = None


def get_bg_pool():
    global _all_bg
    if _all_bg is None:
        _all_bg = []
        for p in random.sample(music_clips, 400):
            w = openwakeword.data.read_audio(p)
            w = w.numpy() if hasattr(w, "numpy") else w
            w = (np.asarray(w) * 32767).astype(np.int16)
            if w.ndim > 1:
                w = w[0]
            _all_bg.append(w)
        for p in nm_train:
            w, _ = sf.read(p, dtype="int16")
            _all_bg.append(w)
    return _all_bg


def mixed_clip(fg_data, bg_pool, snr_low=5, snr_high=15):
    bg = random.choice(bg_pool).copy()
    if len(bg) < TOTAL:
        bg = np.tile(bg, TOTAL // len(bg) + 1)[:TOTAL]
    else:
        off = random.randint(0, len(bg) - TOTAL)
        bg = bg[off:off + TOTAL]
    fg = fg_data.astype(np.float32)
    if len(fg) > TOTAL:
        fg = fg[:TOTAL]
    fg_rms = np.sqrt((fg ** 2).mean()) + 1e-9
    bg_rms = np.sqrt((bg.astype(np.float32) ** 2).mean()) + 1e-9
    snr = 10 ** (np.random.uniform(snr_low, snr_high) / 20)
    scale = snr * bg_rms / fg_rms
    start = random.randint(0, TOTAL - len(fg))
    bg[start:start + len(fg)] = (bg[start:start + len(fg)] + scale * fg).astype(np.int16)
    # volume augmentation
    peak = np.abs(bg).max() + 1e-9
    vol = np.random.uniform(0.05, 1.0)
    bg = (bg / peak * min(vol, 1.0)).astype(np.int16)
    return bg, start, len(fg)


def stream_feature_rows(audio):
    """Exactly openwakeword.Model.predict's feature path. Returns (N, 28, 96)."""
    F = openwakeword.utils.AudioFeatures()
    rows = []
    for i in range(0, len(audio) - FRAME + 1, FRAME):
        F(audio[i:i + FRAME].astype(np.int16))
        rows.append(F.get_features(28)[0])
    return np.stack(rows) if rows else np.empty((0, 28, 96), dtype=np.float32)


def windows_label(background_pool, clips, phrase_is_present=True):
    """Yield (features_row, label) for every 80ms window of mixed clips."""
    for p in tqdm(clips, desc="featurize"):
        data, _ = sf.read(p, dtype="int16")
        if data.ndim > 1:
            data = data[:, 0]
        bg, start, flen = mixed_clip(data, background_pool)
        feats = stream_feature_rows(bg)
        # window i of stream covers audio up to (i+1)*1280+ (mel lag ~ 6 frames);
        # phrase end in samples = start+flen. Label 1 for windows ending within
        # 0-200ms after phrase end.
        phrase_end = start + flen
        for i in range(len(feats)):
            win_end = (i + 1) * FRAME
            hit = phrase_is_present and (0 <= phrase_end - win_end <= int(0.2 * SR))
            yield feats[i], 1.0 if hit else 0.0


bg_pool = get_bg_pool()
pos_feats, neg_feats = [], []
for f, lab in windows_label(bg_pool, positive_clips):
    if lab == 1.0:
        pos_feats.append(f)
    else:
        neg_feats.append(f)
# subsample the negative windows from positives (most of a clip is background)
rng = np.random.default_rng(SEED)
keep = rng.random(len(neg_feats)) < 0.15
neg_from_pos = [neg_feats[i] for i in range(len(neg_feats)) if keep[i]]
print(f"pos windows={len(pos_feats)} neg-windows-from-pos={len(neg_from_pos)}")
del neg_feats

# near-miss: ALL windows are negative
nm_neg = []
for f, lab in windows_label(bg_pool, nm_train, phrase_is_present=False):
    nm_neg.append(f)
# subsample
keep = rng.random(len(nm_neg)) < 0.25
nm_neg = [nm_neg[i] for i in range(len(nm_neg)) if keep[i]]
print(f"nm windows={len(nm_neg)}")

# music windows (label 0)
music_neg = []
for p in tqdm(random.sample(music_clips, 200), desc="music"):
    w = openwakeword.data.read_audio(p)
    w = w.numpy() if hasattr(w, "numpy") else w
    w = (w * 32767).astype(np.int16)
    if w.ndim > 1:
        w = w[0]
    if len(w) < TOTAL:
        w = np.tile(w, TOTAL // len(w) + 1)[:TOTAL]
    else:
        w = w[:TOTAL]
    feats = stream_feature_rows(w)
    for f in feats:
        music_neg.append(f)
keep = rng.random(len(music_neg)) < 0.3
music_neg = [music_neg[i] for i in range(len(music_neg)) if keep[i]]
print(f"music windows={len(music_neg)}")

X_pos = np.stack(pos_feats).astype(np.float32)
X_neg = np.vstack([np.stack(neg_from_pos), np.stack(nm_neg), np.stack(music_neg)]).astype(np.float32)
np.save("pos_stream_v4.npy", X_pos)
np.save("neg_stream_v4.npy", X_neg)
print("X_pos", X_pos.shape, "X_neg", X_neg.shape)

# ── Train ─────────────────────────────────────────────────────────────────────
import torch  # noqa: E402
from torch import nn  # noqa: E402

X = np.vstack([X_neg, X_pos])
y = np.array([0] * len(X_neg) + [1] * len(X_pos)).astype(np.float32)[..., None]
rng2 = np.random.default_rng(SEED)
idx = rng2.permutation(len(X))
X, y = X[idx], y[idx]
n_val = max(256, int(0.08 * len(X)))
X_val, y_val = torch.from_numpy(X[:n_val]), torch.from_numpy(y[:n_val])
X_train, y_train = torch.from_numpy(X[n_val:]), torch.from_numpy(y[n_val:])
print(f"train={len(X_train)} val={len(X_val)} pos_frac={float(y.mean()):.3f}")

training_data = torch.utils.data.DataLoader(
    torch.utils.data.TensorDataset(X_train, y_train), batch_size=512, shuffle=True)

torch.manual_seed(SEED)
fcn = torch.nn.Sequential(
    torch.nn.Flatten(),
    torch.nn.Linear(X.shape[1] * X.shape[2], 32),
    torch.nn.LayerNorm(32),
    torch.nn.ReLU(),
    torch.nn.Dropout(0.3),
    torch.nn.Linear(32, 32),
    torch.nn.LayerNorm(32),
    torch.nn.ReLU(),
    torch.nn.Dropout(0.3),
    torch.nn.Linear(32, 1),
    torch.nn.Sigmoid(),
)
loss_function = torch.nn.functional.binary_cross_entropy
optimizer = torch.optim.Adam(fcn.parameters(), lr=0.001)

history = collections.defaultdict(list)
best_score, best_state, best_epoch, best_metrics = -1e9, None, 0, None
for epoch in range(20):
    fcn.train()
    for xb, yb in training_data:
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
    score = val_recall - 5.0 * val_fpr
    if score > best_score:
        best_score, best_state, best_epoch = score, {k: v.clone() for k, v in fcn.state_dict().items()}, epoch
        best_metrics = (val_acc, val_fpr, val_recall)

if best_state:
    fcn.load_state_dict(best_state)
print(f"BEST epoch={best_epoch} acc={best_metrics[0]:.4f} fpr={best_metrics[1]:.4f} recall={best_metrics[2]:.4f}")

torch.onnx.export(fcn, args=torch.zeros((1, 28, 96)), f="hey_alfred.onnx")
print("exported:", os.path.abspath("hey_alfred.onnx"), os.path.getsize("hey_alfred.onnx"))
