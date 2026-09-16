"""NSD of a fixed physical 2-D study must not depend on the voxel grid used to sample it."""
import sys
from pathlib import Path
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from monai.metrics.surface_dice import compute_surface_dice
def nsd(pred, ref, spacing):
    oh = lambda m: torch.nn.functional.one_hot(torch.as_tensor(m, dtype=torch.int64), 2).permute(0, 3, 1, 2)
    r = compute_surface_dice(oh(pred[None]), oh(ref[None]), class_thresholds=[2.5], spacing=tuple(spacing))
    return float(r[0, 0])
def study(sp):
    x, y = np.meshgrid(*(np.arange(66) * s for s in sp), indexing="xy")
    c = (sp[0] * 33.0, sp[1] * 33.0)
    r2 = (x - c[0]) ** 2 + (y - c[1]) ** 2
    rp = 14.0 + 2.0 * np.cos(3.0 * np.arctan2(y - c[1], x - c[0]))
    return (r2 <= 196.0).astype(np.uint8), (r2 <= rp ** 2).astype(np.uint8)
def down3(m):
    return (m.reshape(22, 3, 22, 3).mean(axis=(1, 3)) >= 0.5).astype(np.uint8)
ref, pred = study((1.0, 1.0))
s_fine = nsd(pred, ref, (1.0, 1.0))
s_coarse = nsd(down3(pred), down3(ref), (3.0, 3.0))
assert np.isfinite(s_fine) and np.isfinite(s_coarse), f"non-finite NSD: {s_fine}, {s_coarse}"
assert abs(s_fine - s_coarse) <= 0.10, f"NSD is representation dependent: fine={s_fine:.4f}, coarse={s_coarse:.4f} (max allowed 0.10)"
print("PASS")
