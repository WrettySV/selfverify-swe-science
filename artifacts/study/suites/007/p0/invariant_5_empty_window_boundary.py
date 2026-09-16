"""Boundary behavior: if the registration window holds no reference signal,
no transient can be registered, so none may be accepted into the average.

The reference spectrum is a narrow Gaussian band far from the requested
window (a true spectral hole), so the windowed comparison has zero reference
power. A correct workflow must refuse to register (finite observations,
everything rejected); a workflow that ignores the window happily "registers"
against the unstable region and accepts the transient.
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

MRSData = _load("inv5_mrsdata", "suspect/mrsdata.py").MRSData
fc = _load("inv5_freqcorr", "suspect/processing/frequency_correction.py")

dt, n = 2e-4, 512
t = np.arange(n) * dt
fa = np.linspace(-1.0 / (2 * dt), 1.0 / (2 * dt), n, endpoint=False)
# reference: single spectral band around -100 Hz (80 Hz sigma) -> exact hole elsewhere
spec = np.exp(-0.5 * ((fa + 100.0) / 80.0) ** 2)
ref_fid = np.fft.ifft(np.fft.ifftshift(spec))
ref = MRSData(ref_fid, dt, 141.0)
hole_window = (1500.0, 2200.0)
winmask = (fa > hole_window[0]) & (fa < hole_window[1])
ref_power_in_window = float(np.sum(np.abs(spec[winmask]) ** 2))
assert ref_power_in_window < 1e-12, "test setup error: window must be a true spectral hole"
x = MRSData(ref_fid * np.exp(2j * np.pi * (30.0 * t + 0.2)), dt, 141.0)
res = fc.register_dynamic_series([x], reference=ref, initial_guesses=[(0.0, 0.0)],
                                 frequency_range=hole_window, reject_threshold=0.5)
assert bool(np.all(np.isfinite(res["estimates"]))), "estimates must stay finite for an empty registration window"
assert bool(np.all(np.isfinite(res["residuals_after"]))), "residuals must stay finite for an empty registration window"
assert not bool(res["accepted"][0]), \
    "no reference signal in the window: nothing can be registered, transient must not be accepted"
print("PASS")
