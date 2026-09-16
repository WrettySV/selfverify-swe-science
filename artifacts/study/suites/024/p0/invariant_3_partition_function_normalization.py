"""Total probability mass on the zero-sum support must be exactly 1.

Integrating exp(logp) over the (n-1)-dim hyperplane (via an orthonormal
basis, importance-sampled with the pushforward proposal N(0, sigma^2 I))
must give 1: logp is a proper density on the support. The pre-fix code
rescales the whole logp by dof/size, which leaves the quadratic term
unchanged in relative weight but inflates the integrated mass to
(size/dof)^(dof/2) > 1, so the estimator deviates from 1 by O(1).
"""
import sys
from pathlib import Path

import numpy as np

import os  # noqa: E402

sys.path.insert(0, os.environ.get("PM_SOURCE_DIR") or str(Path(__file__).resolve().parents[2] / "source"))
import pymc as pm  # noqa: E402
import pytensor  # noqa: E402
import pytensor.tensor as pt  # noqa: E402

SIGMA, N, NEVAL = 0.8, 7, 40000
DOF = N - 1

rng = np.random.default_rng(5)
Z = rng.normal(size=(N, DOF))
Z -= Z.mean(axis=0, keepdims=True)
Q, _ = np.linalg.qr(Z)
assert np.abs(Q.sum(axis=0)).max() < 1e-12

dist = pm.ZeroSumNormal.dist(sigma=SIGMA, shape=(N,))
u = pt.matrix("u")
logp = pm.logp(dist, u @ Q.T)
evaluate = pytensor.function([u], logp)
us = rng.normal(size=(DOF, NEVAL)) * SIGMA
lp = evaluate(us.T)
logphi = 0.5 * DOF * np.log(2.0 * np.pi * SIGMA**2) + (us**2).sum(axis=0) / (2.0 * SIGMA**2)
mass = float(np.exp(lp + logphi).mean())
assert abs(mass - 1.0) < 0.05, (
    f"integrated density over the support = {mass:.4f}, expected 1: "
    f"logp is not a properly normalised density on the zero-sum hyperplane"
)
print("PASS")
