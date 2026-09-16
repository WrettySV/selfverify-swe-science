"""Transients that cannot be registered to the reference must be rejected.

The last transient's stable-region peak amplitude is x2.5 (an amplitude
change no frequency/phase rotation can undo), so its windowed residual after
correction must stay above the reject threshold and it must be flagged
unusable. The three genuinely drifted transients must be accepted.
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

MRSData = _load("inv2_mrsdata", "suspect/mrsdata.py").MRSData
fc = _load("inv2_freqcorr", "suspect/processing/frequency_correction.py")

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
rng = np.random.default_rng(5)

def transient(ft, pt, delta, scale=1.0):
    fid = peaks(SPEC) * scale * np.exp(2j * np.pi * (ft * t + pt))
    fid += 2.0 * np.exp(1j * rng.uniform(-3, 3)) * np.exp(2j * np.pi * (1200.0 + delta) * t) * np.exp(-t / 5e-3)
    fid += 1.6 * np.exp(1j * rng.uniform(-3, 3)) * np.exp(2j * np.pi * (-900.0 - delta) * t) * np.exp(-t / 5e-3)
    return MRSData(fid + (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * 0.004, dt, 141.0)

series = [transient(12.0, 0.05, 40.0), transient(-30.0, -0.12, 40.0),
          transient(5.0, 0.3, 40.0), transient(8.0, 0.1, 40.0, scale=2.5)]
res = fc.register_dynamic_series(series, reference=ref, initial_guesses=[(0.0, 0.0)] * 4,
                                 frequency_range=WIN, reject_threshold=0.25)
acc = [bool(v) for v in res["accepted"]]
assert acc[:3] == [True, True, True], f"drifted transients with a good stable-region match must be accepted, got {acc}"
assert acc[3] is False, "transient whose stable region cannot be matched by any freq/phase rotation must be rejected from the average"
print("PASS")
