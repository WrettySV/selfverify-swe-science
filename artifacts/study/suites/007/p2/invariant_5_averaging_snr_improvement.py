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
peaks = [(-140.0, 6.0, 1.0, 0.0), (-110.0, 8.0, 0.6, 0.12), (-85.0, 5.0, 0.4, -0.2), (150.0, 6.0, 0.7, 0.3), (175.0, 5.0, 0.5, -0.4)]
reference = MRSData(sum(a * np.exp(-2.0 * np.pi * w * t) * np.exp(2j * np.pi * (f * t + ph)) for (f, w, a, ph) in peaks), dt, f0)
rng = np.random.default_rng(42)
drifts = [(26.4, 0.31), (-31.8, 0.08), (18.9, -0.26), (-24.6, 0.44), (29.7, 0.52), (-17.3, -0.14), (33.2, 0.19), (-28.1, 0.37)]
scale = 0.03 * float(np.linalg.norm(reference))
series = [fc.transform_fid(reference, f, p) + MRSData(scale * rng.standard_normal(n), dt, f0) for (f, p) in drifts]
result = fc.register_dynamic_series(series, reference=reference, initial_guesses=[(0.0, 0.0)] * 8,
                                    frequency_range=(-200.0, -75.0), reject_threshold=0.42)
accepted = np.asarray(result["accepted"], dtype=bool)
corrected = [np.asarray(c) for c, k in zip(result["corrected"], accepted) if k]
assert len(corrected) >= 6, f"too few transients accepted for averaging: {len(corrected)}/8"
snr_before, snr_after = fc.average_spectrum_snr(series), fc.average_spectrum_snr(corrected)
axis = reference.frequency_axis(); inw = (axis > -200.0) & (axis < -75.0)
ref_spec = np.fft.fftshift(np.fft.fft(reference))
windowed_ratio = lambda s: float(np.linalg.norm((np.fft.fftshift(np.fft.fft(s)) - ref_spec)[inw]) / np.linalg.norm(ref_spec[inw]))
ratio_before, ratio_after = float(np.mean([windowed_ratio(np.asarray(x)) for x in series])), float(np.mean([windowed_ratio(c) for c in corrected]))
assert snr_after >= 3.5 * snr_before, f"averaged SNR did not improve enough after registration: {snr_before:.1f} -> {snr_after:.1f} (need >= 3.5x)"
assert ratio_after <= 0.2 * ratio_before, f"windowed residual did not drop enough after registration: {ratio_before:.3f} -> {ratio_after:.3f} (need <= 0.2x)"
print("PASS")
