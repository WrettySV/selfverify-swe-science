import sys
from pathlib import Path
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from monai.metrics import SurfaceDiceMetric

# Reference rectangle: cols x in [2,10), rows y in [2,8). Prediction extends the right side by
# 3 px (cols x in [2,13)). With spacing (1,1) and tolerance 1.5, the fraction of physical
# boundary edge length within tolerance is exactly 48/62 = 24/31 (independent face oracle).
ref = np.zeros((10, 16), bool)
pre = np.zeros((10, 16), bool)
ref[2:8, 2:10] = True
pre[2:8, 2:13] = True
oh = lambda m: torch.nn.functional.one_hot(torch.as_tensor(m[None], dtype=torch.int64), 2).permute(0, 3, 1, 2)
met = SurfaceDiceMetric(class_thresholds=[1.5], include_background=False, reduction="none")
got = float(met(oh(pre), oh(ref), spacing=(1.0, 1.0)).reshape(-1)[0])
expected = 24.0 / 31.0
assert abs(got - expected) <= 1e-6, (
    f"NSD={got:.6f} != physical boundary fraction 24/31={expected:.6f}; boundary is counted "
    "per voxel (grid-dependent) instead of per physical edge length"
)
print("PASS", f"nsd={got:.6f} expected={expected:.6f}")
