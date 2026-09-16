import importlib.util as ilu, pathlib
import numpy as np

def _load(path):
    spec = ilu.spec_from_file_location("m" + path.name, path)
    mod = ilu.module_from_spec(spec); spec.loader.exec_module(mod); return mod
ROOT = pathlib.Path(__file__).resolve().parents[2]
MRSData = _load(ROOT / "source" / "suspect" / "mrsdata.py").MRSData
fc = _load(ROOT / "source" / "suspect" / "processing" / "frequency_correction.py")
n, dt, f0 = 768, 1.0 / 2400.0, 127.7
t = np.arange(n) * dt
peaks = [(-140.0, 6.0, 1.0, 0.0), (-110.0, 8.0, 0.6, 0.12), (-85.0, 5.0, 0.4, -0.2)]
reference = MRSData(sum(a * np.exp(-2.0 * np.pi * w * t) * np.exp(2j * np.pi * (f * t + ph)) for (f, w, a, ph) in peaks), dt, f0)
window, sw = (-200.0, -75.0), 1.0 / dt
fwrap = lambda x: (x + sw / 2.0) % sw - sw / 2.0
drifts = [(17.3, 0.23), (-23.8, 0.61), (8.9, -0.34), (-31.2, 0.05)]
data = [fc.transform_fid(reference, f, p) for (f, p) in drifts]
guess_sets = [[(0.0, 0.0)] * 4, [(37.4, 0.55)] * 4, [(-41.2, -0.31)] * 4]
def _run(guesses):
    return fc.register_dynamic_series(data, reference=reference, initial_guesses=guesses,
                                      frequency_range=window, reject_threshold=0.42)
results = [_run(g) for g in guess_sets]
corrected = [np.stack([np.asarray(c) for c in r["corrected"]]) for r in results]
max_diff = max(float(np.linalg.norm(corrected[i] - corrected[j]) / np.linalg.norm(corrected[i]))
               for i in range(3) for j in range(i + 1, 3))
est0 = np.asarray(results[0]["estimates"])
drift_err = max(abs(fwrap(est0[i][0] - drifts[i][0])) for i in range(4))
assert max_diff < 0.01, f"registration result depends on the drift hint: max pairwise rel diff = {max_diff:.4f} (limit 0.01)"
assert drift_err < 1.5, f"no-hint registration is incorrect anyway: max |freq error| = {drift_err:.3f} Hz (limit 1.5)"
print("PASS")
