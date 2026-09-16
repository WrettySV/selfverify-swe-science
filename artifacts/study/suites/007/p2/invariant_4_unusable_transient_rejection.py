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
rng = np.random.default_rng(7)
good = fc.transform_fid(reference, 12.3, 0.18) + MRSData(0.005 * rng.standard_normal(n), dt, f0)
bad = MRSData(0.35 * (rng.standard_normal(n) + 1j * rng.standard_normal(n)), dt, f0)
result = fc.register_dynamic_series([good, bad], reference=reference, initial_guesses=[(0.0, 0.0)] * 2,
                                    frequency_range=(-200.0, -75.0), reject_threshold=0.5)
accepted = np.asarray(result["accepted"], dtype=bool)
after = np.asarray(result["residuals_after"], dtype=float)
assert bool(accepted[0]), "drifted-but-valid transient was rejected by the quality control"
assert not bool(accepted[1]), "noise-only transient was accepted and would pollute the reported average"
assert after[0] < 0.5, f"valid transient residual too large: {after[0]:.4f} (limit 0.5)"
assert after[1] > 0.5, f"noise transient residual not large enough to trigger rejection: {after[1]:.4f} (limit 0.5)"
print("PASS")
