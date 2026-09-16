import os, sys
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for cand in (_root, os.getcwd()):
    if os.path.isdir(os.path.join(cand, "source", "pymc")):
        sys.path.insert(0, os.path.join(cand, "source")); break
import numpy as np, pymc as pm, pytensor

def onb1d(n):
    out = []
    for i in range(n - 1):
        v = np.zeros(n); v[i], v[-1] = 1.0, -1.0
        for c in out: v -= v @ c * c
        out.append(v / np.linalg.norm(v))
    return out

B = [np.outer(u, w) for u in onb1d(3) for w in onb1d(4)]
sigma = 0.9
dist = pm.ZeroSumNormal.dist(sigma=sigma, shape=(3, 4), n_zerosum_axes=2)
val = dist.type()
f = pytensor.function([val], pm.logp(dist, val))
for seed in (11, 12):
    s = np.random.default_rng(seed).standard_normal(len(B))
    x = sum(a * b for a, b in zip(s, B))
    got, ref = float(f(x)), -3.0 * np.log(2 * np.pi * sigma**2) - s @ s / (2 * sigma**2)
    if abs(got - ref) > 1e-8:
        raise AssertionError(
            f"ZSN logp {got:.10f} != reduced-coordinate Gaussian logp {ref:.10f}: "
            "density must equal N(0, sigma^2 I) expressed in an orthonormal basis of the zerosum subspace"
        )
print("PASS")
