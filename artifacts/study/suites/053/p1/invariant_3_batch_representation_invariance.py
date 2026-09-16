"""Per-element representation invariance must hold for a multi-study batch with per-batch spacings."""
import sys
from pathlib import Path
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from monai.metrics.surface_dice import compute_surface_dice
def oh(m):
    return torch.nn.functional.one_hot(torch.as_tensor(m, dtype=torch.int64), 2).permute(3, 0, 1, 2)
def study(sp, amp, mode):
    x, y, z = np.meshgrid(*(np.arange(66) * s for s in sp), indexing="xy")
    c = (sp[0] * 33.0, sp[1] * 33.0, sp[2] * 33.0)
    r2 = (x - c[0]) ** 2 + (y - c[1]) ** 2 + (z - c[2]) ** 2
    ang = np.arctan2(x - c[0], z - c[2]) if mode else np.arctan2(z - c[2], y - c[1])
    rp = 14.0 + amp * np.cos(3.0 * ang)
    return (r2 <= 196.0).astype(np.uint8), (r2 <= rp ** 2).astype(np.uint8)
def d3(m):
    return (m.reshape(22, 3, 22, 3, 22, 3).mean(axis=(1, 3, 5)) >= 0.5).astype(np.uint8)
refA, predA = study((2.0, 1.0, 1.0), 2.5, 1)
refB, predB = study((1.0, 1.0, 1.0), 2.0, 0)
fine = torch.stack([oh(predA), oh(predB)]), torch.stack([oh(refA), oh(refB)])
coarse = torch.stack([oh(d3(predA)), oh(d3(predB))]), torch.stack([oh(d3(refA)), oh(d3(refB))])
sf = compute_surface_dice(fine[0], fine[1], class_thresholds=[2.5], spacing=[(2.0, 1.0, 1.0), (1.0, 1.0, 1.0)])
sc = compute_surface_dice(coarse[0], coarse[1], class_thresholds=[2.5], spacing=[(6.0, 3.0, 3.0), (3.0, 3.0, 3.0)])
f0, f1, c0, c1 = (float(v) for v in (sf[0, 0], sf[1, 0], sc[0, 0], sc[1, 0]))
assert all(np.isfinite(v) for v in (f0, f1, c0, c1)), f"non-finite NSD: {f0}, {f1}, {c0}, {c1}"
assert abs(f0 - c0) <= 0.10 and abs(f1 - c1) <= 0.10, f"batch NSD is representation dependent: study0 {f0:.4f}->{c0:.4f}, study1 {f1:.4f}->{c1:.4f} (max allowed 0.10)"
print("PASS")
