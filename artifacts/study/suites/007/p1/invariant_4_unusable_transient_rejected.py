import importlib.util as iu
from pathlib import Path
import numpy as np

r = Path(__file__).resolve().parents[2]
def L(p):
    s = iu.spec_from_file_location(p.stem, p)
    m = iu.module_from_spec(s)
    s.loader.exec_module(m)
    return m
fc = L(r / "source/suspect/processing/frequency_correction.py")
MD = L(r / "source/suspect/mrsdata.py").MRSData
rng = np.random.RandomState(53)
dt, n, f0 = 1.0 / 2600.0, 512, 123.0
t = np.arange(n) * dt
base = sum(a * np.exp(2j * np.pi * f * t) * np.exp(-(np.pi * w * t) ** 2 / 2) for f, a, w in [(70.0, 1.0, 26.0), (-130.0, 0.5, 24.0)])
corrupt = 1.5 * np.exp(2j * np.pi * (-20.0) * t) * np.exp(-(np.pi * 40.0 * t) ** 2 / 2)
drifts = [(14.0, 0.12), (-19.0, -0.10), (0.0, 0.0), (9.0, 0.18), (-6.0, -0.22)]
series = []
for i, (f, p) in enumerate(drifts):
    sig = (corrupt if i == 2 else base * np.exp(2j * np.pi * (f * t + p))) + 0.04 * (rng.randn(n) + 1j * rng.randn(n))
    series.append(MD(sig, dt, f0))
ref = MD(base, dt, f0)
res = fc.register_dynamic_series(series, reference=ref, frequency_range=(-160.0, 140.0), reject_threshold=0.42)
acc = np.asarray(res["accepted"], dtype=bool)
assert acc.tolist() == [True, True, False, True, True], f"the unregisterable transient must be rejected and the others kept, got {acc.tolist()}"
ra = np.asarray(res["residuals_after"], dtype=float)
assert ra[2] > 0.42 and np.all(ra[acc] < 0.42), f"residuals inconsistent with the acceptance decision: {np.round(ra, 3)}"
print("PASS")
