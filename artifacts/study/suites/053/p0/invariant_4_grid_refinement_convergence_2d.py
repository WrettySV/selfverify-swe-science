"""Grid-refinement (scaling) invariance: same physical ellipse pair on three nested resolutions must converge in score."""
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


def score_at(sp):
    n = int(round(64.0 / sp[0]))
    c = (n / 2.0, n / 2.0)
    t = lambda a: torch.nn.functional.one_hot(torch.as_tensor(a[None], dtype=torch.int64), 2).permute(0, 3, 1, 2)
    m = SurfaceDiceMetric(class_thresholds=[2.4], include_background=False, reduction="none")
    return float(m(t(ell2((n, n), sp, c, (18, 22))), t(ell2((n, n), sp, c, (16, 20))), spacing=tuple(sp)).cpu().item())


s_fine, s_mid, s_coarse = score_at((0.5, 0.5)), score_at((1.0, 1.0)), score_at((2.0, 2.0))
assert all(np.isfinite(v) for v in (s_fine, s_mid, s_coarse)), f"non-finite: {s_fine}, {s_mid}, {s_coarse}"
assert s_coarse >= 0.90, f"coarsest grid lost surface agreement: fine={s_fine}, mid={s_mid}, coarse={s_coarse}"
assert abs(s_fine - s_coarse) <= 0.10, f"no convergence under refinement: fine={s_fine}, coarse={s_coarse}"
print("PASS")
