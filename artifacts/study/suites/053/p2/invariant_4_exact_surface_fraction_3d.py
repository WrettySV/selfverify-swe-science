import sys
from pathlib import Path
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from monai.metrics import SurfaceDiceMetric

# Reference box [2:10, 2:8, 2:8) (8x6x6). Prediction extends the +x side by 3 px (11x6x6).
# With unit spacing and tolerance 1.5, the fraction of physical face area within tolerance is
# exactly 500/600 = 5/6 (independent face-element oracle).
ref = np.zeros((14, 12, 12), bool)
pre = np.zeros((14, 12, 12), bool)
ref[2:10, 2:8, 2:8] = True
pre[2:13, 2:8, 2:8] = True
oh = lambda m: torch.nn.functional.one_hot(torch.as_tensor(m[None], dtype=torch.int64), 2).permute(0, 4, 1, 2, 3)
met = SurfaceDiceMetric(class_thresholds=[1.5], include_background=False, reduction="none")
got = float(met(oh(pre), oh(ref), spacing=(1.0, 1.0, 1.0)).reshape(-1)[0])
expected = 5.0 / 6.0
assert abs(got - expected) <= 1e-6, (
    f"NSD={got:.6f} != physical boundary fraction 5/6={expected:.6f}; boundary is counted "
    "per voxel (grid-dependent) instead of per physical face area"
)
print("PASS", f"nsd={got:.6f} expected={expected:.6f}")
