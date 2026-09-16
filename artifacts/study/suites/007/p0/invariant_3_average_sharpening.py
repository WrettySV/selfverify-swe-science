"""A correct registration must sharpen the average: windowed residual must
collapse, estimates must hit each transient's true drift, and the averaged
dominant peak must get sharper and stronger after correction."""
import importlib.util
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]

def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / "source" / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

MRSData = _load("inv3_mrsdata", "suspect/mrsdata.py").MRSData
fc = _load("inv3_freqcorr", "suspect/processing/frequency_correction.py")

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
ref_fid = peaks(SPEC) + peaks([(1200.0, 2.0, 5e-3), (-900.0, 1.6, 5e-3)])
ref = MRSData(ref_fid, dt, 141.0)
rng = np.random.default_rng(23)

def transient(ft, pt, delta):
    fid = peaks(SPEC) * np.exp(2j * np.pi * (ft * t + pt))
    fid += 2.0 * np.exp(1j * rng.uniform(-3, 3)) * np.exp(2j * np.pi * (1200.0 + delta) * t) * np.exp(-t / 5e-3)
    fid += 1.6 * np.exp(1j * rng.uniform(-3, 3)) * np.exp(2j * np.pi * (-900.0 - delta) * t) * np.exp(-t / 5e-3)
    return MRSData(fid + (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * 0.004, dt, 141.0)

ft = [45.0, -40.0, 10.0, -20.0, 30.0, -5.0, 22.0, -33.0]
pt = [0.2, -0.25, 0.05, -0.35, 0.15, -0.1, 0.3, 0.02]
dl = [40.0, -35.0, 30.0, -45.0, 45.0, -30.0, 35.0, -40.0]
series = [transient(a, b, c) for a, b, c in zip(ft, pt, dl)]
res = fc.register_dynamic_series(series, reference=ref, initial_guesses=[(0.0, 0.0)] * 8,
                                 frequency_range=WIN, reject_threshold=0.5)
assert bool(np.all(res["accepted"])), "all 8 mildly drifted transients must be accepted"
sr = np.fft.fftshift(np.fft.fft(ref_fid))
def wres(y):
    sy = np.fft.fftshift(np.fft.fft(np.asarray(y)))
    return float(np.linalg.norm((sy - sr)[mask]) / np.linalg.norm(sr[mask]))
before = np.array([wres(s) for s in series])
after = np.array([wres(c) for c in res["corrected"]])
ratio = float(after.mean() / before.mean())
assert ratio <= 0.2, f"mean windowed residual must collapse after correction (ratio {ratio:.3f})"
err_f = float(np.max(np.abs(res["estimates"][:, 0] - ft)))
err_p = float(np.max(np.abs(((res["estimates"][:, 1] - pt) + 0.5) % 1.0 - 0.5)))
assert err_f <= 4.0, f"drift estimates must match truth within 4 Hz (max error {err_f:.2f} Hz)"
assert err_p <= 0.05, f"drift estimates must match truth within 0.05 turns (max error {err_p:.4f})"

def metrics(series):
    m = np.abs(np.fft.fftshift(np.fft.fft(np.mean(np.asarray(series), axis=0))))
    edge = max(8, len(m) // 12)
    snr = float(m.max() / (np.std(np.concatenate([m[:edge], m[-edge:]])) + 1e-12))
    pk, hh = int(m.argmax()), m.max() / 2.0
    left = pk
    while left > 0 and m[left] >= hh:
        left -= 1
    right = pk
    while right < len(m) - 1 and m[right] >= hh:
        right += 1
    return snr, float((right - left) * (1.0 / dt) / len(m))
snr_b, lw_b = metrics(series)
snr_a, lw_a = metrics(res["corrected"])
assert lw_a < lw_b, f"dominant peak must narrow after correction ({lw_a:.1f} Hz vs {lw_b:.1f} Hz before)"
assert snr_a > snr_b, f"SNR proxy must improve after correction ({snr_a:.1f} vs {snr_b:.1f} before)"
print("PASS")
