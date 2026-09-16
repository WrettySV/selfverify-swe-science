import os, sys, functools
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
def unit_mass(shape, sigma, npts=19):
    B = [np.outer(u, w) for u in onb1d(shape[0]) for w in onb1d(shape[1])]
    g = np.linspace(-10 * sigma, 10 * sigma, npts); w = np.full(npts, g[1] - g[0]); w[0] = w[-1] = w[0] / 2
    S = np.stack(np.meshgrid(*([g] * len(B)), indexing="ij"), axis=-1).reshape(-1, len(B))
    X = (S @ np.stack(B).reshape(len(B), -1)).reshape(-1, *shape)
    d = pm.ZeroSumNormal.dist(sigma=sigma, shape=X.shape, n_zerosum_axes=2)
    val = d.type()
    f = pytensor.function([val], pm.logp(d, val))
    F = np.exp(f(X)).reshape((npts,) * len(B))
    return functools.reduce(lambda a, b: np.tensordot(a, b, axes=([-1], [0])), [F] + [w] * len(B))
for shape, sigma in (((2, 2), 1.7), ((3, 3), 0.8)):
    m = unit_mass(shape, sigma)
    if abs(m - 1.0) > 0.01:
        raise AssertionError(f"ZSN density on support {shape} must integrate to total mass 1, got {m:.6f}")
print("PASS")
