"""Drift must be estimated from the stable window alone, not the full spectrum.

A transient is the stable in-window peak shifted by (40 Hz, 0.15 turns), plus
unstable out-of-window features that sit at *different* frequencies than in
the reference. Windowed registration must recover the true drift; a
full-spectrum registration is biased by the unstable features.
"""
import importlib.util
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]

def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / "source" / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

MRSData = _load("inv1_mrsdata", "suspect/mrsdata.py").MRSData
fc = _load("inv1_freqcorr", "suspect/processing/frequency_correction.py")

dt, n = 2e-4, 512
t = np.arange(n) * dt
fa = np.linspace(-1.0 / (2 * dt), 1.0 / (2 * dt), n, endpoint=False)
WIN = (-350.0, 350.0)
mask = (fa > WIN[0]) & (fa < WIN[1])

def peaks(lst):
    fid = np.zeros(n, complex)
    for f, a, t2 in lst:
        fid += a * np.exp(2j * np.pi * f * t) * np.exp(-t / t2)
    return fid

SPEC = [(-100.0, 1.0, 12e-3)]
OUT = [(1200.0, 2.0, 5e-3), (-900.0, 1.6, 5e-3)]
ref_fid = peaks(SPEC) + peaks(OUT)
ref = MRSData(ref_fid, dt, 141.0)
F_TRUE, P_TRUE, DELTA = 40.0, 0.15, 40.0
fid = peaks(SPEC) * np.exp(2j * np.pi * (F_TRUE * t + P_TRUE))
fid += 2.0 * np.exp(1j * 0.3) * np.exp(2j * np.pi * (1200.0 + DELTA) * t) * np.exp(-t / 5e-3)
fid += 1.6 * np.exp(1j * -0.7) * np.exp(2j * np.pi * (-900.0 - DELTA) * t) * np.exp(-t / 5e-3)
x = MRSData(fid, dt, 141.0)

def wres(y):
    sy = np.fft.fftshift(np.fft.fft(np.asarray(y)))
    sr = np.fft.fftshift(np.fft.fft(ref_fid))
    return float(np.linalg.norm((sy - sr)[mask]) / np.linalg.norm(sr[mask]))

res = fc.register_dynamic_series([x], reference=ref, initial_guesses=[(0.0, 0.0)],
                                 frequency_range=WIN, reject_threshold=0.5)
f_est, p_est = (float(v) for v in res["estimates"][0])
dph = ((p_est - P_TRUE + 0.5) % 1.0) - 0.5
ratio = wres(res["corrected"][0]) / wres(x)
assert bool(res["accepted"][0]), "drifted transient with a usable stable window must be accepted"
assert abs(f_est - F_TRUE) <= 3.0, f"freq drift off by {f_est - F_TRUE:+.2f} Hz: unstable region leaked into registration"
assert abs(dph) <= 0.02, f"phase drift off by {dph:+.4f} turns: unstable region leaked into registration"
assert ratio <= 0.15, f"windowed residual not reduced after correction (ratio {ratio:.3f})"
print("PASS")
