#!/usr/bin/env python3
"""FINAL ROOT CAUSE: v3 near-miss negatives were trained END-ALIGNED with trailing
silence. But streaming continues AFTER the clip ends (zeros!). Wait — no.

Look at the stream scores: 0.008 ... 0.009, 0.048, then 0.947-0.952 for ~15
frames. The near-miss clip is 0.87 s (11 frames). The phrase 'hej hermes'
occupies most of it. After clip ends, silence follows. Model fires DURING the
phrase (frames 20-34). The trained end-aligned window (28 frames ending at
phrase end) should equal stream window at the END of the phrase...

BUT the streaming featurizer carries state — melspectrogram buffer etc. The
stream feature window at phrase-end is NOT identical to batch window (corr 0.885).

Key insight from v1: v1 model scored near-miss at 0.75 ceiling STREAMING
(badly). v3 scores 0.95 streaming on near-miss. Both models are near-perfect on
BATCH features (train-neg mean 0.012!). So the batch features separate
perfectly, but streaming features do NOT — there's a real batch/stream
distribution mismatch, and the models overfit to batch quirks.

FIX: train on STREAMING features. Generate features exactly the way
Model.predict does: AudioFeatures per 1280-sample frame, get_features(28).
That guarantees train == inference distribution.
"""
print("v4: train on streaming-style features")
