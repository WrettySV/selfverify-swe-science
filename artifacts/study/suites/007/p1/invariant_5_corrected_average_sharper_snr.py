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
rng = np.random.RandomState(67)
dt, n, f0 = 1.0 / 2400.0, 1024, 123.0
t = np.arange(n) * dt
base = sum(a * np.exp(2j * np.pi * f * t) * np.exp(-(np.pi * w * t) ** 2 / 2) for f, a, w in [(60.0, 1.0, 14.0), (-110.0, 0.45, 16.0)])
drifts = [(75.0, 0.12), (-65.0, -0.18), (55.0, 0.28), (-40.0, 0.06), (80.0, -0.10), (-55.0, 0.22), (30.0, -0.30), (68.0, 0.15)]
series = [MD(base * np.exp(2j * np.pi * (f * t + p)) + 0.04 * (rng.randn(n) + 1j * rng.randn(n)), dt, f0) for f, p in drifts]
ref = MD(base, dt, f0)
res = fc.register_dynamic_series(series, reference=ref, initial_guesses=[(500.0, 0.9)] * len(series))
est = np.asarray(res["estimates"], dtype=float)
assert np.all(np.abs(est[:, 0] - [d[0] for d in drifts]) < 1.0), f"frequency drifts not recovered from a poor initial guess: {np.round(est[:, 0], 2)}"
acc = np.asarray(res["accepted"], dtype=bool)
assert acc.all(), f"all usable transients should be accepted: {acc.tolist()}"
orig = [np.asarray(s, dtype=complex) for s in series]
corr = [np.asarray(s, dtype=complex) for s in res["corrected"]]
snr_b, snr_a = fc.average_spectrum_snr(orig), fc.average_spectrum_snr(corr)
lw_b, lw_a = fc.linewidth_hz(orig, dt), fc.linewidth_hz(corr, dt)
assert snr_a > 1.15 * snr_b and lw_a < 0.85 * lw_b, f"corrected average must be sharper with higher SNR: snr {snr_b:.1f}->{snr_a:.1f}, fwhm {lw_b:.1f}->{lw_a:.1f} Hz"
print("PASS")
