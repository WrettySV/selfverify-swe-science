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
    return np.stack(out)
def second_moments(n, sigma, npts=19):
    B = np.stack(onb1d(n))
    g = np.linspace(-10 * sigma, 10 * sigma, npts); w = np.full(npts, g[1] - g[0]); w[0] = w[-1] = w[0] / 2
    D = B.shape[0]
    S = np.stack(np.meshgrid(*([g] * D), indexing="ij"), axis=-1).reshape(-1, D)
    d = pm.ZeroSumNormal.dist(sigma=sigma, shape=(S.shape[0], n), n_zerosum_axes=1)
    val = d.type()
    F = np.exp(pytensor.function([val], pm.logp(d, val))(S @ B))
    Wt = w
    for k in range(1, D): Wt = np.multiply.outer(Wt, w)
    W = F * Wt.reshape(-1); Z = W.sum()
    return np.array([[(W * S[:, k] * S[:, l]).sum() / Z for l in range(D)] for k in range(D)])
sigma = 1.3
C = second_moments(5, sigma)
if np.abs(C - sigma**2 * np.eye(4)).max() > 0.05:
    raise AssertionError(f"ZSN moments must equal the projected N(0, sigma^2 I): covariance in orthonormal zerosum coordinates must be sigma^2 I, max deviation {np.abs(C - sigma**2*np.eye(4)).max():.4f}")
print("PASS")
