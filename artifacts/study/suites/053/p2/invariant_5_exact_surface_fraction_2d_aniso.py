import sys
from pathlib import Path
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from monai.metrics import SurfaceDiceMetric

# Same rectangle pair as the unit-spacing case, but with anisotropic spacing (0.5, 2.0): the
# physical study is x in [1,5) mm x y in [4,16) mm, prediction extends x to 6.5 mm. With
# tolerance 1.5 mm the physical boundary fraction is exactly 76/88 = 19/22 (face oracle).
ref = np.zeros((10, 16), bool)
pre = np.zeros((10, 16), bool)
ref[2:8, 2:10] = True
pre[2:8, 2:13] = True
oh = lambda m: torch.nn.functional.one_hot(torch.as_tensor(m[None], dtype=torch.int64), 2).permute(0, 3, 1, 2)
met = SurfaceDiceMetric(class_thresholds=[1.5], include_background=False, reduction="none")
got = float(met(oh(pre), oh(ref), spacing=(0.5, 2.0)).reshape(-1)[0])
expected = 19.0 / 22.0
assert abs(got - expected) <= 1e-6, (
    f"NSD={got:.6f} != physical boundary fraction 19/22={expected:.6f}; anisotropic spacing is "
    "not applied per physical axis of the boundary"
)
print("PASS", f"nsd={got:.6f} expected={expected:.6f}")
