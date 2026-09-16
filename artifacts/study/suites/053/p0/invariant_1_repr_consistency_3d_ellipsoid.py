"""3D representation invariance (anisotropic spacing): score of a fixed physical ellipsoid pair must not depend on the voxel grid."""
import sys
from pathlib import Path
import numpy as np
import torch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source"))
from monai.metrics import SurfaceDiceMetric


def ell3(shape, sp, c, s):
    g = [np.arange(n) for n in shape]
    X, Y, Z = np.meshgrid(*g, indexing="ij")
    return (((X - c[0]) * sp[0] / s[0]) ** 2 + ((Y - c[1]) * sp[1] / s[1]) ** 2 + ((Z - c[2]) * sp[2] / s[2]) ** 2) <= 1.0


def score(shape, sp, c, ref_semi, pred_semi):
    t = lambda a: torch.nn.functional.one_hot(torch.as_tensor(a[None], dtype=torch.int64), 2).permute(0, 4, 1, 2, 3)
    m = SurfaceDiceMetric(class_thresholds=[2.4], include_background=False, reduction="none")
    return float(m(t(ell3(shape, sp, c, pred_semi)), t(ell3(shape, sp, c, ref_semi)), spacing=tuple(sp)).cpu().item())


fine = score((48, 48, 40), (1.0, 1.0, 2.0), (24, 24, 20), (10, 12, 14), (12, 14, 16))
coarse = score((24, 24, 20), (2.0, 2.0, 4.0), (12, 12, 10), (10, 12, 14), (12, 14, 16))
assert np.isfinite(fine) and np.isfinite(coarse), f"non-finite scores: fine={fine}, coarse={coarse}"
assert fine >= 0.90 and coarse >= 0.90, f"surface agreement lost in a representation: fine={fine}, coarse={coarse}"
assert abs(fine - coarse) <= 0.10, f"score depends on the voxel grid: fine={fine}, coarse={coarse}"
print("PASS")
