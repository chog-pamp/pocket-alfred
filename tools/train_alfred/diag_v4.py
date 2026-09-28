#!/usr/bin/env python3
"""v4 diagnosis: pos windows labeled only 0.7-0.9% of the time (~2.5 per clip)
and the label rule may be misaligned. Check what fraction of pos-window features
actually contain phrase audio, by scoring trained model on train-pos rows.
Also check: is phrase_end actually inside the audio? bg start might exceed
window end because the streaming feature lags behind audio by ~0.5 s (mel needs
76 frames = 0.5 s). The get_features(28) window at step i covers mel frames up
to i*1280, which corresponds to audio ending ~ (i+1)*1280 minus the mel window
lag. So my 'win_end = (i+1)*FRAME' is shifted by ~0.5 s vs the actual audio
covered. This mislabels positives!
"""
import sys

import numpy as np

WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"
pos = np.load(f"{WORKDIR}/pos_stream_v4.npy")
print("pos rows:", pos.shape)
# load trained model? it was overwritten with the failed run. Just check stats.
print("feature mean:", pos.mean(), "std:", pos.std())
