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
rng = np.random.RandomState(11)
dt, n, f0 = 1.0 / 2600.0, 512, 123.0
t = np.arange(n) * dt
base = sum(a * np.exp(2j * np.pi * f * t) * np.exp(-(np.pi * w * t) ** 2 / 2) for f, a, w in [(80.0, 1.0, 30.0), (-150.0, 0.4, 25.0)])
series = [MD(base * np.exp(2j * np.pi * (f * t + p)) + 0.02 * (rng.randn(n) + 1j * rng.randn(n)), dt, f0)
          for f, p in [(34.0, 0.2), (-28.0, -0.15), (12.0, 0.05), (-40.0, 0.3), (22.0, -0.25)]]
reference = np.asarray(fc.dynamic_reference(series), dtype=complex)
expected = np.mean([np.asarray(x, dtype=complex) for x in series], axis=0)
dev = float(np.max(np.abs(reference - expected)))
assert dev < 1e-9, f"common reference must be the average of the series; max deviation from the mean is {dev:.3e} (a single transient is not a common reference)"
print("PASS")
