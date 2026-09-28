#!/usr/bin/env python3
"""v5 — train on STREAMING features (exact openwakeword.Model.predict path).

v1-v3 trained on batch features (embed_clips), which separate pos/neg almost
perfectly (train-neg mean 0.012) but a streaming inference-time mismatch (corr
~0.885, different context padding) made the exported models fire on ANY speech
when run through openwakeword.Model. v4's streaming labels were misaligned by
the mel-context lag. v5 fixes labeling with a tolerant positive band and, most
importantly, generates ALL training windows through the exact streaming path.
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
random.seed(SEED)
np.random.seed(SEED)
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
print(f"positives={len(positive_clips)} nearmiss train={len(nm_train)} val={len(nm_val)}")

# background pool
random.seed(SEED)
bg_pool = []
for p in random.sample(music_clips, 300):
    w = openwakeword.data.read_audio(p)
    w = w.numpy() if hasattr(w, "numpy") else np.asarray(w)
    w = (np.asarray(w) * 32767).astype(np.int16)
    if w.ndim > 1:
        w = w[0]
    bg_pool.append(w)
for p in nm_train:
    w, _ = sf.read(p, dtype="int16")
    if w.ndim > 1:
        w = w[:, 0]
    bg_pool.append(w)


def mixed_clip(fg, snr_low=5, snr_high=15):
    bg = random.choice(bg_pool).copy()
    if len(bg) < TOTAL:
        bg = np.tile(bg, TOTAL // len(bg) + 1)[:TOTAL]
    else:
        off = random.randint(0, len(bg) - TOTAL)
        bg = bg[off:off + TOTAL]
    fg = np.asarray(fg, dtype=np.float32)[:TOTAL]
    fg_rms = np.sqrt((fg ** 2).mean()) + 1e-9
    bg_rms = np.sqrt((bg.astype(np.float32) ** 2).mean()) + 1e-9
    snr = 10 ** (np.random.uniform(snr_low, snr_high) / 20)
    scale = snr * bg_rms / fg_rms
    start = random.randint(0, TOTAL - len(fg))
    bg[start:start + len(fg)] = (bg[start:start + len(fg)] + scale * fg).astype(np.int16)
    peak = np.abs(bg).max() + 1e-9
    bg = (bg / peak * random.uniform(0.05, 1.0)).astype(np.int16)
    return bg, start, len(fg)


_FEAT_CACHE = []


def stream_rows(audio):
    F = openwakeword.utils.AudioFeatures()
    rows = []
    for i in range(0, len(audio) - FRAME + 1, FRAME):
        F(audio[i:i + FRAME].astype(np.int16))
        rows.append(F.get_features(28)[0])
    return np.stack(rows)


def process_clips(clips, with_phrase):
    """Return (X, y) streaming windows for the given clips, mixed over bg."""
    label_desc = "pos v5" if with_phrase else "nm v5"
    X, y = [], []
    for p in tqdm(clips, desc=label_desc):
        data, _ = sf.read(p, dtype="int16")
        if data.ndim > 1:
            data = data[:, 0]
        bg, start, flen = mixed_clip(data)
        # append trailing silence so the stream runs past the phrase end
        audio = np.concatenate([bg, np.zeros(FRAME * 8, dtype=np.int16)])
        feats = stream_rows(audio)
        phrase_end = start + flen
        for i in range(len(feats)):
            win_end = (i + 1) * FRAME
            if with_phrase:
                # positive band: window ends 0..700ms after phrase end (tolerates
                # the ~0.5 s mel-context lag of the streaming featurizer)
                d = phrase_end - win_end
                lab = 1.0 if (0 <= d <= int(0.7 * SR)) else 0.0
            else:
                lab = 0.0
            X.append(feats[i])
            y.append(lab)
    return np.asarray(X, dtype=np.float32), np.asarray(y, dtype=np.float32)


pos_X, pos_y = process_clips(positive_clips, True)
nm_X, nm_y = process_clips(nm_train, False)

# ── Assemble training set ─────────────────────────────────────────────────────
import torch  # noqa: E402  (needed for training below)

rng = np.random.default_rng(SEED)
X_pos = pos_X[pos_y == 1]
X_neg_posmix = pos_X[pos_y == 0]
keep = rng.random(len(X_neg_posmix)) < 0.12
X_neg_posmix = X_neg_posmix[keep]

# music windows (all label 0)
music_X = []
for p in tqdm(random.sample(list(music_clips), 200), desc="music v5"):
    w = openwakeword.data.read_audio(p)
    w = w.numpy() if hasattr(w, "numpy") else np.asarray(w)
    w = (np.asarray(w) * 32767).astype(np.int16)
    if w.ndim > 1:
        w = w[0]
    if len(w) < TOTAL:
        w = np.tile(w, TOTAL // len(w) + 1)[:TOTAL]
    else:
        w = w[:TOTAL]
    feats = stream_rows(w)
    music_X.extend(list(feats))
music_X = np.asarray(music_X, dtype=np.float32)

X = np.vstack([X_pos, X_neg_posmix, nm_X, np.asarray(music_X, dtype=np.float32)])
y = np.array([1.0] * len(X_pos) + [0.0] * len(X_neg_posmix) + [0.0] * len(nm_X)
             + [0.0] * len(music_X), dtype=np.float32)[..., None]
print(f"X_pos={len(X_pos)} neg_posmix={len(X_neg_posmix)} nm={len(nm_X)} music={len(music_X)}")

idx = rng.permutation(len(X))
X, y = X[idx], y[idx]
n_val = max(256, int(0.1 * len(X)))
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
        # UPPVikta positiva (v5-buggen: 0.2 → kollaps till predict-all-negative,
        # val_recall=0.0000 i alla epochs). pos_frac≈0.26 → vikten 3 ger ~50/50 effektivt.
        weights[yb.flatten() == 1] = 3.0
        optimizer.zero_grad()
        preds = fcn(xb)
        loss = torch.nn.functional.binary_cross_entropy(preds, yb, weights[..., None])
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
    print(f"epoch {epoch}: loss={history['loss'][-1]:.4f} val_acc={val_acc:.4f} "
          f"val_fpr@0.5={val_fpr:.4f} val_recall={val_recall:.4f}")
    score = val_recall - 5.0 * val_fpr
    if score > best_score:
        best_score = score
        best_state = {k: v.clone() for k, v in fcn.state_dict().items()}
        best_epoch = epoch
        best_metrics = (val_acc, val_fpr, val_recall)

if best_state:
    fcn.load_state_dict(best_state)
print(f"BEST epoch={best_epoch} acc={best_metrics[0]:.4f} fpr={best_metrics[1]:.4f} "
      f"recall={best_metrics[2]:.4f}")

torch.onnx.export(fcn, args=torch.zeros((1, 28, 96)), f="hey_alfred.onnx")
print("exported:", os.path.abspath("hey_alfred.onnx"), os.path.getsize("hey_alfred.onnx"))

# ── Held-out near-miss STREAMING evaluation ──────────────────────────────────
import onnxruntime as ort  # noqa: E402
sess = ort.InferenceSession("hey_alfred.onnx", providers=["CPUExecutionProvider"])
input_name = sess.get_inputs()[0].name
hits = 0
max_score = 0.0
for p in nm_val:
    data, _ = sf.read(p, dtype="int16")
    if data.ndim > 1:
        data = data[:, 0]
    audio = np.concatenate([data, np.zeros(FRAME * 8, dtype=np.int16)])
    feats = stream_rows(audio)
    ss = [float(sess.run(None, {input_name: f[None]})[0][0][0]) for f in feats]
    m = max(ss)
    max_score = max(max_score, m)
    hits += 1 if m >= 0.5 else 0
print(f"HELD-OUT near-miss: n={len(nm_val)} FPR@0.5={hits / max(len(nm_val), 1):.4f} "
      f"max={max_score:.3f}")


