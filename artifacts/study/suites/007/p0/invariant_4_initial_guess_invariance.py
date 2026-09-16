"""The recovered drift must not depend on the (poor) initial guess.

The same transient must yield the same estimate whether started from (0, 0)
or from a far-off guess (250 Hz, 0.45 turns), and that estimate must be the
true drift: a refinement-only optimizer wanders to guess-dependent spurious
local minima when the unstable spectral regions are in play.
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

MRSData = _load("inv4_mrsdata", "suspect/mrsdata.py").MRSData
fc = _load("inv4_freqcorr", "suspect/processing/frequency_correction.py")

dt, n = 2e-4, 512
t = np.arange(n) * dt
fa = np.linspace(-1.0 / (2 * dt), 1.0 / (2 * dt), n, endpoint=False)
WIN = (-350.0, 350.0)

def peaks(lst):
    fid = np.zeros(n, complex)
    for f, a, t2 in lst:
        fid += a * np.exp(2j * np.pi * f * t) * np.exp(-t / t2)
    return fid

SPEC = [(-100.0, 1.0, 12e-3)]
ref_fid = peaks(SPEC) + peaks([(1200.0, 2.0, 5e-3), (-900.0, 1.6, 5e-3)])
ref = MRSData(ref_fid, dt, 141.0)
F_TRUE, P_TRUE, DELTA = 60.0, -0.3, 40.0
fid = peaks(SPEC) * np.exp(2j * np.pi * (F_TRUE * t + P_TRUE))
fid += 2.0 * np.exp(1j * 1.1) * np.exp(2j * np.pi * (1200.0 + DELTA) * t) * np.exp(-t / 5e-3)
fid += 1.6 * np.exp(1j * 2.2) * np.exp(2j * np.pi * (-900.0 - DELTA) * t) * np.exp(-t / 5e-3)
x = MRSData(fid, dt, 141.0)

def run(guess):
    return fc.register_dynamic_series([x], reference=ref, initial_guesses=[guess],
                                      frequency_range=WIN, reject_threshold=0.5)

est_a = np.asarray(run((0.0, 0.0))["estimates"][0], dtype=float)
est_b = np.asarray(run((250.0, 0.45))["estimates"][0], dtype=float)
wrap = lambda d: float(((d + 0.5) % 1.0) - 0.5)
assert abs(est_a[0] - est_b[0]) <= 1.0 and abs(wrap(est_a[1] - est_b[1])) <= 0.02, \
    f"estimate depends on the initial guess: {(est_a[0], est_a[1])} vs {(est_b[0], est_b[1])}"
assert abs(est_a[0] - F_TRUE) <= 3.0, f"true drift not recovered from (0,0) start: got {est_a[0]:.2f} Hz (truth {F_TRUE})"
assert abs(wrap(est_a[1] - P_TRUE)) <= 0.03, f"true phase not recovered from (0,0) start: got {est_a[1]:.4f} turns (truth {P_TRUE})"
assert abs(est_b[0] - F_TRUE) <= 3.0, f"true drift not recovered from far start: got {est_b[0]:.2f} Hz (truth {F_TRUE})"
assert abs(wrap(est_b[1] - P_TRUE)) <= 0.03, f"true phase not recovered from far start: got {est_b[1]:.4f} turns (truth {P_TRUE})"
print("PASS")
