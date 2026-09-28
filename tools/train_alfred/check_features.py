#!/usr/bin/env python3
"""Sanity check: are positive features actually distinguishable from negatives?"""
import numpy as np
import sys
sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools/train_alfred")

pos = np.load("/home/leo/homelab/pocket-alfred/tools/train_alfred/hey_alfred_positive_features.npy")
neg = np.load("/home/leo/homelab/pocket-alfred/tools/train_alfred/negative_features.npy")
print("pos", pos.shape, "neg", neg.shape)
# If alignment worked, the LAST timesteps of positive clips should carry phrase info;
# per-timestep mean magnitude comparison:
pm = np.abs(pos).mean(axis=(0, 2))
nm = np.abs(neg).mean(axis=(0, 2))
print("per-timestep pos mean (first 5):", np.round(pm[:5], 2), "... last 5:", np.round(pm[-5:], 2))
print("per-timestep neg mean (first 5):", np.round(nm[:5], 2))
# nearest-centroid check
cpos = pos.reshape(len(pos), -1).mean(0)
dpos = np.abs(pos.reshape(len(pos), -1) - cpos).mean(1)
dneg = np.abs(neg.reshape(len(neg), -1) - cpos).mean(1)
print("dist to pos-centroid: pos", dpos.mean(), "neg", dneg.mean())
# simple separability: mean activation at last timestep
print("last-timestep feature sum: pos", float(np.abs(pos[:, -1, :]).mean()), "neg", float(np.abs(neg[:, -1, :]).mean()))
