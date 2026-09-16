"""ZeroSumNormal kernel must be exp(-||x||^2 / (2 sigma^2)) on the zero-sum support.

For any x with sum(x) == 0, the logp difference logp(x) - logp(0) must equal
-||x||^2 / (2 sigma^2): the documented ZSN(sigma) = N(0, sigma^2 (I - J/n)) has
precision sigma^-2 on every direction of the hyperplane. The pre-fix code
multiplies the whole elementwise logp sum by dof/size, which scales this
quadratic term down by (n-1)/n and is therefore wrong for any x != 0.
"""
import sys
from pathlib import Path

import numpy as np

import os  # noqa: E402

sys.path.insert(0, os.environ.get("PM_SOURCE_DIR") or str(Path(__file__).resolve().parents[2] / "source"))
import pymc as pm  # noqa: E402

SIGMA, N = 1.7, 7  # new scale and new length (public fixture uses other values)

rng = np.random.default_rng(77)
dist = pm.ZeroSumNormal.dist(sigma=SIGMA, shape=(N,))
logp0 = float(pm.logp(dist, np.zeros(N)).eval())
for k in range(3):
    z = rng.normal(size=N)
    x = z - z.mean()
    assert abs(x.sum()) < 1e-12
    expected = -float(np.sum(x**2)) / (2.0 * SIGMA**2)
    got = float(pm.logp(dist, x).eval()) - logp0
    assert abs(got - expected) < 1e-7, (
        f"logp(x)-logp(0) = {got:.6f}, expected {expected:.6f}: "
        f"precision on the zero-sum support is not sigma^-2 "
        f"(quadratic term wrongly scaled by dof/size)"
    )
print("PASS")
