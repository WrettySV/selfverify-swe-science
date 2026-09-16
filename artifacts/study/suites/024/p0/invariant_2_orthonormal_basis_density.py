"""Representation equivalence on the 2-axis zero-sum support.

The documented ZSN(sigma) on doubly-zero-sum (A x B) tensors must equal the
pushforward of N(0, sigma^2 I_dof), dof = (A-1)(B-1), under any orthonormal
basis of the support. In such a basis the logp is the product density of dof
i.i.d. N(0, sigma^2) coordinates:
    logp(x) = -dof/2 log(2 pi sigma^2) - ||u||^2 / (2 sigma^2).
The pre-fix code scales the elementwise logp sum by dof/(A*B), so the
quadratic part of this identity is broken by a factor (A*B - dof)/(A*B).
"""
import sys
from pathlib import Path

import numpy as np

import os  # noqa: E402

sys.path.insert(0, os.environ.get("PM_SOURCE_DIR") or str(Path(__file__).resolve().parents[2] / "source"))
import pymc as pm  # noqa: E402

SIGMA, A, B = 2.3, 3, 4  # new scales and shape (fixture is 4x5, sigma 0.5)
DOF = (A - 1) * (B - 1)

rng = np.random.default_rng(11)

def double_center(z):
    return z - z.mean(axis=0, keepdims=True) - z.mean(axis=1, keepdims=True) + z.mean(axis=(0, 1), keepdims=True)

Q, _ = np.linalg.qr(double_center(rng.normal(size=(A, B, DOF))).reshape(A * B, DOF))
assert np.abs(Q.reshape(A, B, DOF).sum(axis=(0, 1))).max() < 1e-12  # basis lies on the support

u = rng.normal(size=DOF)
x = (Q.reshape(A, B, DOF) * u).sum(axis=-1)
reference = -0.5 * DOF * np.log(2.0 * np.pi * SIGMA**2) - np.sum(u**2) / (2.0 * SIGMA**2)
dist = pm.ZeroSumNormal.dist(sigma=SIGMA, shape=(A, B), n_zerosum_axes=2)
got = float(pm.logp(dist, x).eval())
assert abs(got - reference) < 1e-7, (
    f"logp(x) = {got:.6f}, but the product N(0, sigma^2) density in an orthonormal "
    f"basis gives {reference:.6f}: the density on the zero-sum support is not "
    f"representation-equivalent to the documented degenerate normal"
)
print("PASS")
