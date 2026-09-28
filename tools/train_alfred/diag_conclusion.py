#!/usr/bin/env python3
"""Key experiment: train a model with the SAME pipeline but validated at positions
OTHER than end-aligned. Also generate more diverse positives by splitting 'hey'
and 'alfred' pronunciation variants.

But FIRST, quickly verify the hypothesis: the model may be triggering on
'SPEECH END-ALIGNED' (any speech) because the near-miss negatives in TRAINING
were ALSO end-aligned in the negative_features (well, no — negatives were
stack_clips'd from the fma/fsd50k corpus + nearmiss, at RANDOM offsets — the
nearmiss negatives' phrase positions within the 3s window are random).

Hmm. The real issue: model fires 0.75-0.76 on ANY speech (pos or neg) end-aligned.
The 0.75 ceiling for negatives vs 0.76 positives means the classifier found only
weak signal. Training data problem: our near-miss negatives are all < 2 s, so as
3 s windows they contain SILENCE (padding) — 2000 neg windows are mostly silence
from the nearmiss (320 clips in 4.02 h total; negs were dominated by fma+fsd50k).

Wait — actually 2000 neg features came mostly from fma/fsd50k (~4 hours).
Only 320 nearmiss clips = ~4 min. The model learned 'speech end-aligned' vs
'music/noise', because our nearmiss set was tiny relative to music/noise!

FIX: retrain with (a) nearmiss negatives END-ALIGNED as features too,
(b) heavy negative weight, (c) more nearmiss data (generate 1000+), and
(d) random-position positive windows too (jittered alignment so the model
fires across positions).
"""
print("see retrain plan")
