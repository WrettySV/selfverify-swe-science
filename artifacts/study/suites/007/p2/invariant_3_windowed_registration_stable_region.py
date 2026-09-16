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
stable = [(-140.0, 6.0, 1.0, 0.0), (-110.0, 8.0, 0.6, 0.12), (-85.0, 5.0, 0.4, -0.2)]
other = [(150.0, 6.0, 0.7, 0.3), (175.0, 5.0, 0.5, -0.4), (260.0, 7.0, 2.0, 0.1)]
reference = MRSData(sum(a * np.exp(-2.0 * np.pi * w * t) * np.exp(2j * np.pi * (f * t + ph)) for (f, w, a, ph) in stable), dt, f0)
transient = fc.transform_fid(MRSData(sum(a * np.exp(-2.0 * np.pi * w * t) * np.exp(2j * np.pi * (f * t + ph)) for (f, w, a, ph) in stable + other), dt, f0), -21.3, 0.42)
window, sw = (-200.0, -75.0), 1.0 / dt
fwrap, pwrap = (lambda x: (x + sw / 2.0) % sw - sw / 2.0), (lambda x: (x + 0.5) % 1.0 - 0.5)
try:
    est = fc.spectral_registration(transient, reference, initial_guess=(21.3, 0.42), frequency_range=window)
except Exception as exc:
    raise AssertionError(f"windowed spectral_registration(frequency_range=tuple) is broken: {type(exc).__name__}: {exc}")
assert abs(fwrap(est[0] + 21.3)) < 2.0 and abs(pwrap(est[1] - 0.42)) < 0.06, f"windowed registration missed the drift: est=({est[0]:.2f}, {est[1]:.3f})"
result = fc.register_dynamic_series([transient], reference=reference, initial_guesses=[(0.0, 0.0)],
                                    frequency_range=window, reject_threshold=0.42)
est_w = np.asarray(result["estimates"])[0]
axis = reference.frequency_axis(); inw = (axis > window[0]) & (axis < window[1])
ref_spec, corr_spec = (np.fft.fftshift(np.fft.fft(reference)), np.fft.fftshift(np.fft.fft(np.asarray(result["corrected"][0]))))
windowed = float(np.linalg.norm((corr_spec - ref_spec)[inw]) / np.linalg.norm(ref_spec[inw]))
assert abs(fwrap(est_w[0] + 21.3)) < 2.0 and abs(pwrap(est_w[1] - 0.42)) < 0.06 and windowed < 0.2, f"workflow failed: est=({est_w[0]:.2f}, {est_w[1]:.3f}), windowed residual = {windowed:.4f}"
print("PASS")
