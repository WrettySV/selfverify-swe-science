"""2D representation invariance + unit consistency: same physical ellipse pair on two grids, in mm vs cm, must give the same score."""
import sys
from pathlib import Path
import numpy as np
import torch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source"))
from monai.metrics import SurfaceDiceMetric


def ell2(shape, sp, c, s):
    X, Y = np.meshgrid(*[np.arange(n) for n in shape], indexing="ij")
    return (((X - c[0]) * sp[0] / s[0]) ** 2 + ((Y - c[1]) * sp[1] / s[1]) ** 2) <= 1.0


def score(pred, ref, sp, tau):
    t = lambda a: torch.nn.functional.one_hot(torch.as_tensor(a[None], dtype=torch.int64), 2).permute(0, 3, 1, 2)
    m = SurfaceDiceMetric(class_thresholds=[tau], include_background=False, reduction="none")
    return float(m(t(pred), t(ref), spacing=tuple(sp)).cpu().item())


rf = ell2((64, 64), (1.0, 1.0), (32, 32), (14, 22))
pf = ell2((64, 64), (1.0, 1.0), (32, 32), (16, 24))
rc, pc = ell2((32, 32), (2.0, 2.0), (16, 16), (14, 22)), ell2((32, 32), (2.0, 2.0), (16, 16), (16, 24))
fine, coarse = score(pf, rf, (1.0, 1.0), 2.4), score(pc, rc, (2.0, 2.0), 2.4)
in_cm = score(pf, rf, (0.1, 0.1), 0.24)
assert abs(fine - in_cm) < 1e-9, f"unit inconsistency: mm={fine}, cm={in_cm}"
assert fine >= 0.95 and coarse >= 0.95, f"surface agreement lost in a representation: fine={fine}, coarse={coarse}"
assert abs(fine - coarse) <= 0.05, f"score depends on the voxel grid: fine={fine}, coarse={coarse}"
print("PASS")
