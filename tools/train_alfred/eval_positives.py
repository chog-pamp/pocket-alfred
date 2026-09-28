#!/usr/bin/env python3
"""POSITIV recall-koll: kör exporterad ONNX på positiva clips (stream_rows-featurizer)."""
import glob
import sys

import numpy as np
import onnxruntime as ort
import soundfile as sf

sys.path.insert(0, ".")
sess = ort.InferenceSession("hey_alfred.onnx", providers=["CPUExecutionProvider"])
inp = sess.get_inputs()[0].name

from featurize_and_train_v5 import stream_rows  # noqa: E402

pos = sorted(glob.glob("positive/*.wav"))
print("pos files:", len(pos))
hits = 0
mx = 0.0
n = min(60, len(pos))
for p in pos[:60]:
    d, _ = sf.read(p, dtype="int16")
    if d.ndim > 1:
        d = d[:, 0]
    rows = stream_rows(np.concatenate([d, np.zeros(8000, dtype=np.int16)]))
    ss = [float(sess.run(None, {inp: r[None]})[0][0][0]) for r in rows]
    m = max(ss)
    mx = max(mx, m)
    hits += m >= 0.5
print(f"POSITIVES: n={n} recall@0.5={hits / max(1, n):.3f} max={mx:.3f}")
