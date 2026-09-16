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
rng = np.random.RandomState(23)
dt, n, f0 = 1.0 / 2600.0, 512, 123.0
t = np.arange(n) * dt
base = sum(a * np.exp(2j * np.pi * f * t) * np.exp(-(np.pi * w * t) ** 2 / 2) for f, a, w in [(90.0, 1.0, 28.0), (-140.0, 0.5, 24.0), (200.0, 0.3, 20.0)])
ref = MD(base, dt, f0)
drifts = [(34.0, 0.20), (-28.0, -0.15), (12.0, 0.05), (-40.0, 0.30), (22.0, -0.25)]
series = [MD(base * np.exp(2j * np.pi * (f * t + p)) + 0.03 * (rng.randn(n) + 1j * rng.randn(n)), dt, f0) for f, p in drifts]
res = fc.register_dynamic_series(series, reference=ref, initial_guesses=[(500.0, 0.9)] * len(series))
est = np.asarray(res["estimates"], dtype=float)
assert np.all(np.abs(est[:, 0] - [d[0] for d in drifts]) < 1.0), f"frequency drifts not recovered despite a poor initial guess: {np.round(est[:, 0], 2)} vs {np.round([d[0] for d in drifts], 2)}"
assert np.all(np.abs(est[:, 1] - [d[1] for d in drifts]) < 0.12), f"phase drifts not recovered: {np.round(est[:, 1], 3)} vs {np.round([d[1] for d in drifts], 3)}"
ra = np.asarray(res["residuals_after"], dtype=float); rb = np.asarray(res["residuals_before"], dtype=float)
assert np.all(ra < 0.5 * rb), f"correction must reduce the mismatch: before={np.round(rb, 3)} after={np.round(ra, 3)}"
assert np.all(ra < 0.20), f"residual mismatch after correction too large: {np.round(ra, 3)}"
print("PASS")
