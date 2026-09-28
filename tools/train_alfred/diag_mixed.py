#!/usr/bin/env python3
"""Check: do the TRAINING-time positive features (mixin output) actually have
speech aligned at the END? Compare the mixed output's energy envelope vs the
raw positive clip. Also dump a few mixed clips as wav to listen/verify.
"""
import glob
import sys

import numpy as np

sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools")
import openwakeword  # noqa: E402
import openwakeword.data  # noqa: E402

WORKDIR = "/home/leo/homelab/pocket-alfred/tools/train_alfred"
import os  # noqa: E402
os.chdir(WORKDIR)

SR = 16000
TOTAL = 48000

positive_clips, durations = openwakeword.data.filter_audio_paths(
    ["positive"], min_length_secs=0.4, max_length_secs=2.0, duration_method="header")
negative_clips, _ = openwakeword.data.filter_audio_paths(
    ["fma_sample", "fsd50k_sample", "negative_nearmiss"],
    min_length_secs=1.0, max_length_secs=60*30, duration_method="header")

np.random.seed(1)
jitters = (np.random.uniform(0, 0.2, len(positive_clips)) * SR).astype(np.int32)
starts = [TOTAL - (int(np.ceil(d * SR)) + j) for d, j in zip(durations, jitters)]

gen = openwakeword.data.mix_clips_batch(
    foreground_clips=positive_clips[:8],
    background_clips=negative_clips,
    combined_size=TOTAL,
    batch_size=8,
    snr_low=5,
    snr_high=15,
    start_index=starts[:8],
    volume_augmentation=True,
    seed=1,
    shuffle=False,
)
batch, lbls, _ = next(gen)
print("mixed batch shape:", batch.shape)
import soundfile as sf
for i in range(4):
    sf.write(f"diag_mixed_{i}.wav", batch[i], 16000, subtype="PCM_16")
    # energy profile: 10 windows of 4800 samples
    e = [int(np.abs(batch[i][k:k+4800].astype(np.float32)).mean()) for k in range(0, 48000, 4800)]
    print(f"clip {i}: start_index={starts[i]} energy-profile={e}")
