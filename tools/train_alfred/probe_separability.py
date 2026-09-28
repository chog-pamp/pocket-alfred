#!/usr/bin/env python3
"""Retrain with feature-level classification diagnostics first.

Goal: confirm features are separable at all (centroid/linear probe), then train.
Writes diagnostics to stdout.
"""
import numpy as np

pos = np.load("/home/leo/homelab/pocket-alfred/tools/train_alfred/hey_alfred_positive_features.npy")
neg = np.load("/home/leo/homelab/pocket-alfred/tools/train_alfred/negative_features.npy")
print("pos", pos.shape, "neg", neg.shape)

# How much does the LAST clip (containing the phrase) differ between pos/neg?
# Compare the final 8 timesteps vs earlier.
def tail_energy(x, k=8):
    return np.abs(x[:, -k:, :]).mean(axis=(1, 2))

tp, tn = tail_energy(pos), tail_energy(neg)
print(f"tail-8 energy: pos mean={tp.mean():.3f} std={tp.std():.3f}")
print(f"tail-8 energy: neg mean={tn.mean():.3f} std={tn.std():.3f}")

# simple linear separability probe on flattened features
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score

X = np.vstack([pos.reshape(len(pos), -1), neg.reshape(len(neg), -1)])
y = np.array([1] * len(pos) + [0] * len(neg))
clf = LogisticRegression(max_iter=2000, n_jobs=-1)
acc = cross_val_score(clf, X, y, cv=3, scoring="accuracy")
print("logreg 3-fold CV acc:", acc, acc.mean())
