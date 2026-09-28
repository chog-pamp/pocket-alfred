#!/usr/bin/env python3
"""ROOT CAUSE: compare batch (embed_clips) vs streaming (Model.predict) features."""
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools")
import openwakeword  # noqa: E402

WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"

p = f"{WORKDIR}/negative_nearmiss/nearmiss_0000.wav"
data, _ = sf.read(p, dtype="int16")
buf = np.zeros(48000, dtype=np.int16)
buf[-len(data):] = data

F1 = openwakeword.utils.AudioFeatures()
feats_batch = F1.embed_clips(buf[None, :], batch_size=1)[0]

F2 = openwakeword.utils.AudioFeatures()
for i in range(0, 48000, 1280):
    F2(buf[i:i + 1280].astype(np.int16))
feats_stream = F2.get_features(28)[0]

print("batch  last-frame[:8]:", np.round(feats_batch[-1][:8], 3))
print("stream last-frame[:8]:", np.round(feats_stream[-1][:8], 3))
print("corr:", np.corrcoef(feats_batch.flatten(), feats_stream.flatten())[0, 1])
print("batch mean/std:", feats_batch.mean(), feats_batch.std())
print("stream mean/std:", feats_stream.mean(), feats_stream.std())
