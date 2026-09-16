import sys; from pathlib import Path
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from monai.metrics import SurfaceDiceMetric

def ell(shape, c, r, s):
    c, r = np.asarray(c).reshape(3, 1, 1, 1), np.asarray(r).reshape(3, 1, 1, 1)
    g = np.mgrid[tuple(slice(0, n) for n in shape)].astype(float)
    for a in range(3):
        g[a] = (g[a] + 0.5) * s[a]
    return ((((g - c) / r) ** 2).sum(0) < 1).astype(np.uint8)

def nsd(p, r, s, t):
    oh = lambda m: torch.nn.functional.one_hot(torch.as_tensor(m[None], dtype=torch.int64), 2).permute(0, 4, 1, 2, 3)
    met = SurfaceDiceMetric(class_thresholds=[t], include_background=False, reduction="none")
    return float(met(oh(p), oh(r), spacing=tuple(s)).reshape(-1)[0])

SF, SC = (1.0, 1.0, 2.0), (2.0, 2.0, 4.0)
ref_f, pre_f = ell((56, 56, 28), (28, 28, 28), (14, 10, 8), SF), ell((56, 56, 28), (28, 28, 28), (17, 12, 11), SF)
ref_c, pre_c = ell((28, 28, 14), (14, 14, 14), (14, 10, 8), SC), ell((28, 28, 14), (14, 14, 14), (17, 12, 11), SC)
fine, coarse = nsd(pre_f, ref_f, SF, 2.5), nsd(pre_c, ref_c, SC, 2.5)
spread = abs(fine - coarse)
assert fine > 0 and coarse > 0, f"non-positive scores: fine={fine}, coarse={coarse}"
assert spread <= 0.12, (
    f"representation inconsistency: fine={fine:.4f} coarse={coarse:.4f} spread={spread:.4f} > 0.12; "
    "score depends on voxel-grid resolution, not on a physical surface measure"
)
print("PASS", f"fine={fine:.4f} coarse={coarse:.4f} spread={spread:.4f}")
