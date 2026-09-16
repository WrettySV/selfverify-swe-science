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
sigma, c = 0.9, 2.0
def logp_at(x, sig):
    d = pm.ZeroSumNormal.dist(sigma=sig, shape=(3, 4), n_zerosum_axes=2)
    val = d.type()
    return float(pytensor.function([val], pm.logp(d, val))(x))
for seed in (1, 2, 3):
    s = np.random.default_rng(seed).standard_normal(6)
    x = sum(a * b for a, b in zip(s, B))
    got = logp_at(x, c * sigma) - logp_at(x, sigma)
    want = -6.0 * np.log(c) + (1 - 1 / c**2) * s @ s / (2 * sigma**2)
    if abs(got - want) > 1e-8:
        raise AssertionError(
            f"rescaling sigma by {c} must shift logp by {want:.10f}, got {got:.10f}: "
            "logp must transform as a proper Gaussian density under sigma -> c*sigma"
        )
print("PASS")
