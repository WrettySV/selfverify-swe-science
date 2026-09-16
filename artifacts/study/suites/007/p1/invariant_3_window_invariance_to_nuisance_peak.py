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
dt, n, f0 = 1.0 / 3000.0, 2048, 123.0
t = np.arange(n) * dt
base = sum(a * np.exp(2j * np.pi * f * t) * np.exp(-(np.pi * w * t) ** 2 / 2) for f, a, w in [(-60.0, 1.8, 14.0), (45.0, 0.6, 16.0)])
nuisance = 1.5 * np.exp(2j * np.pi * 260.0 * t) * np.exp(-(np.pi * 18.0 * t) ** 2 / 2)
drifts = [(18.0, 0.10), (-25.0, -0.20), (9.0, 0.25)]
win = (-110.0, -10.0)
def build(with_nuisance):
    rr = np.random.RandomState(41)
    return [MD(base * np.exp(2j * np.pi * (f * t + p)) + (nuisance if with_nuisance else 0.0)
            + 0.06 * (rr.randn(n) + 1j * rr.randn(n)), dt, f0) for f, p in drifts]
ref = MD(base, dt, f0)
e1 = np.asarray(fc.register_dynamic_series(build(False), reference=ref, frequency_range=win)["estimates"])
e2 = np.asarray(fc.register_dynamic_series(build(True), reference=ref, frequency_range=win)["estimates"])
truth = np.array(drifts)
assert np.all(np.abs(e1 - truth) < [1.0, 0.12]) and np.all(np.abs(e2 - truth) < [1.0, 0.12]), f"stable-window registration must recover the drifts: clean={np.round(e1, 2)} nuisance={np.round(e2, 2)} truth={np.round(truth, 2)}"
assert np.max(np.abs(e1 - e2)) < 0.5, f"estimates must not change when a condition-dependent peak appears outside the window: max |diff|={np.max(np.abs(e1 - e2)):.2f}"
print("PASS")
