#!/usr/bin/env python3
"""Held-out utvärdering av exporterad hey_alfred.onnx (kör EFTER träning)."""
import glob
import sys

import numpy as np
import onnxruntime as ort
import soundfile as sf

sys.path.insert(0, ".")
sess = ort.InferenceSession("hey_alfred.onnx", providers=["CPUExecutionProvider"])
inp = sess.get_inputs()[0].name
print("input shape:", sess.get_inputs()[0].shape)

nm = [p for p in sorted(glob.glob("negative_nearmiss/*.wav")) if hash(p) % 10 == 0]
print("nm files:", len(nm), nm[:3])

if nm:
    from featurize_and_train_v5 import stream_rows

    hits = 0
    mx = 0.0
    n = min(50, len(nm))
    for p in nm[:50]:
        data, _ = sf.read(p, dtype="int16")
        if data.ndim > 1:
            data = data[:, 0]
        rows = stream_rows(np.concatenate([data, np.zeros(8000, dtype=np.int16)]))
        ss = [float(sess.run(None, {inp: r[None]})[0][0][0]) for r in rows]
        m = max(ss)
        mx = max(mx, m)
        hits += m >= 0.5
    print(f"HELD-OUT nearmiss: n={n} FPR@0.5={hits / max(1, n):.3f} max={mx:.3f}")
else:
    print("INGA near-miss-val-filer hittade — kör featurize_and_train_v5.py först")
