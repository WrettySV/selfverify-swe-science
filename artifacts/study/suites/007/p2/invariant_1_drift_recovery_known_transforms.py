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
fwrap, pwrap = (lambda x: (x + sw / 2.0) % sw - sw / 2.0), (lambda x: (x + 0.5) % 1.0 - 0.5)
drifts = [(17.3, 0.23), (-23.8, 0.61), (8.9, -0.34), (-31.2, 0.05)]
data = [fc.transform_fid(reference, f, p) for (f, p) in drifts]
result = fc.register_dynamic_series(data, reference=reference, initial_guesses=[(0.0, 0.0)] * len(data),
                                    frequency_range=window, reject_threshold=0.42)
worst = [0.0, 0.0, 0.0]
for i, (f, p) in enumerate(drifts):
    fhat, phat = np.asarray(result["estimates"])[i]
    corrected = np.asarray(result["corrected"][i])
    worst[0] = max(worst[0], abs(fwrap(fhat - f)))
    worst[1] = max(worst[1], abs(pwrap(phat - p)))
    worst[2] = max(worst[2], float(np.linalg.norm(corrected - reference) / np.linalg.norm(reference)))
assert worst[0] < 1.5, f"known frequency drifts not recovered: max |error| = {worst[0]:.3f} Hz (limit 1.5)"
assert worst[1] < 0.05, f"known phase drifts not recovered: max |error| = {worst[1]:.4f} cycles (limit 0.05)"
assert worst[2] < 0.05, f"corrected transients still mismatch the reference: rel error = {worst[2]:.4f} (limit 0.05)"
print("PASS")
