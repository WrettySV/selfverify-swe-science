"""3D representation invariance: multi-lobe object with a rigid physical shift (1,1,2) mm; score must survive 2x re-gridding."""
import sys
from pathlib import Path
from functools import reduce
import numpy as np
import torch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source"))
from monai.metrics import SurfaceDiceMetric

def ell3(shape, sp, c, s):
    g = [np.arange(n) for n in shape]
    X, Y, Z = np.meshgrid(*g, indexing="ij")
    return (((X - c[0]) * sp[0] / s[0]) ** 2 + ((Y - c[1]) * sp[1] / s[1]) ** 2 + ((Z - c[2]) * sp[2] / s[2]) ** 2) <= 1.0


def comp(shape, sp, cs, ss, shift):
    return reduce(np.maximum, [ell3(shape, sp, tuple(float(c[i]) + shift[i] for i in range(3)), s) for c, s in zip(cs, ss)])


C, S = [(16, 20, 14), (30, 24, 20), (22, 32, 18), (14, 30, 18)], [(6, 7, 8), (5, 7, 8), (6, 6, 8), (6, 7, 7)]
Cv = [[x / 2 for x in c] for c in C]
pf, rf = comp((48, 48, 40), (1.0, 1.0, 2.0), C, S, (1.0, 1.0, 1.0)), comp((48, 48, 40), (1.0, 1.0, 2.0), C, S, (0.0, 0.0, 0.0))
pc, rc = comp((24, 24, 20), (2.0, 2.0, 4.0), Cv, S, (0.5, 0.5, 0.5)), comp((24, 24, 20), (2.0, 2.0, 4.0), Cv, S, (0.0, 0.0, 0.0))
t = lambda a: torch.nn.functional.one_hot(torch.as_tensor(a[None], dtype=torch.int64), 2).permute(0, 4, 1, 2, 3)
m = SurfaceDiceMetric(class_thresholds=[2.4], include_background=False, reduction="none")
fine, coarse = float(m(t(pf), t(rf), spacing=(1.0, 1.0, 2.0)).cpu().item()), float(m(t(pc), t(rc), spacing=(2.0, 2.0, 4.0)).cpu().item())
assert np.isfinite(fine) and np.isfinite(coarse) and fine >= 0.90 and coarse >= 0.90, f"bad scores: fine={fine}, coarse={coarse}"
assert abs(fine - coarse) <= 0.08, f"score depends on the voxel grid: fine={fine}, coarse={coarse}"
print("PASS")
