import os, sys
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for cand in (_root, os.getcwd()):
    if os.path.isdir(os.path.join(cand, "source", "pymc")):
        sys.path.insert(0, os.path.join(cand, "source")); break
import numpy as np, pymc as pm, pytensor
import pytensor.tensor as pt
def onb1d(n):
    out = []
    for i in range(n - 1):
        v = np.zeros(n); v[i], v[-1] = 1.0, -1.0
        for c in out: v -= v @ c * c
        out.append(v / np.linalg.norm(v))
    return np.stack(out)
U3, U4, tau, nsd = onb1d(3), onb1d(4), 0.8, 0.4
B4 = np.stack([np.outer(u, w) for u in U3 for w in U4]).reshape(6, 3, 4)
rng = np.random.default_rng(41)
fit0 = 1.1 + (U3.T @ rng.standard_normal(2))[:, None] + (U4.T @ rng.standard_normal(3))[None, :] + (rng.standard_normal(6) @ B4.reshape(6, 12)).reshape(3, 4)
y = fit0 + nsd * rng.standard_normal((3, 4))
def inter(phi): return pt.reshape(phi @ B4.reshape(6, 12), (3, 4))
def fit_of(gm, lab, pro, phi): return gm + (U3.T @ lab)[:, None] + (U4.T @ pro)[None, :] + inter(phi)
gm, lab, pro, phi = pt.scalar("gm"), pt.vector("lab"), pt.vector("pro"), pt.vector("phi")
A = pt.stack([pt.sum(pm.logp(pm.Normal.dist(0.0, 5.0), gm)), pt.sum(pm.logp(pm.ZeroSumNormal.dist(sigma=tau, shape=(3,)), U3.T @ lab)), pt.sum(pm.logp(pm.ZeroSumNormal.dist(sigma=tau, shape=(4,)), U4.T @ pro)), pt.sum(pm.logp(pm.ZeroSumNormal.dist(sigma=tau, shape=(3, 4), n_zerosum_axes=2), inter(phi))), pt.sum(pm.logp(pm.Normal.dist(mu=fit_of(gm, lab, pro, phi), sigma=nsd), y))]).sum()
B = pt.stack([pt.sum(pm.logp(pm.Normal.dist(0.0, 5.0), gm)), pt.sum(pm.logp(pm.Normal.dist(0.0, tau, shape=(2,)), lab)), pt.sum(pm.logp(pm.Normal.dist(0.0, tau, shape=(3,)), pro)), pt.sum(pm.logp(pm.Normal.dist(0.0, tau, shape=(6,)), phi)), pt.sum(pm.logp(pm.Normal.dist(mu=fit_of(gm, lab, pro, phi), sigma=nsd), y))]).sum()
fnA, fnB = (pytensor.function([gm, lab, pro, phi], A), pytensor.function([gm, lab, pro, phi], B))
for k in range(3):
    gv, lv, pv, qv = rng.normal(1.0, 0.3), rng.standard_normal(2), rng.standard_normal(3), rng.standard_normal(6)
    if abs(float(fnA(gv, lv, pv, qv)) - float(fnB(gv, lv, pv, qv))) > 1e-6:
        raise AssertionError(f"centered model joint density {fnA(gv, lv, pv, qv):.8f} != reduced-coordinate joint density {fnB(gv, lv, pv, qv):.8f}: both must describe the same Gaussian model")
print("PASS")
