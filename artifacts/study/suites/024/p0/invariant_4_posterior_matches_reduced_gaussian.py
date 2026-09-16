# Posterior of the centered factorial-effects model must equal the exact
# Gaussian posterior from an independent reduced-coordinate implementation
# (new shapes 4x3, new scales/seed/data; fixture is 4x5 with other values).
import sys
from pathlib import Path

import numpy as np

import os  # noqa: E402

sys.path.insert(0, os.environ.get("PM_SOURCE_DIR") or str(Path(__file__).resolve().parents[2] / "source"))
import pymc as pm  # noqa: E402

L, P, SEED, NDRAW = 4, 3, 4242, 1500
SM, SA, SB, SG, SE = 10.0, 0.8, 0.7, 0.2, 0.5

rng = np.random.default_rng(SEED)
a = rng.normal(0.0, 0.4, L); a -= a.mean()
b = rng.normal(0.0, 0.4, P); b -= b.mean()
g = rng.normal(0.0, 0.3, (L, P)); g -= g.mean(0, keepdims=True) + g.mean(1, keepdims=True) - g.mean()
y = (0.5 + a[:, None] + b[None, :] + g + rng.normal(0.0, 0.2, (L, P))).ravel()

ca = lambda i: 2 * (np.arange(L - 1) == i) - 1
cb = lambda j: 2 * (np.arange(P - 1) == j) - 1
CA, CB = 2 * np.eye(L) - 1, 2 * np.eye(P) - 1
X = np.column_stack([np.ones(L * P), np.repeat(CA[:, :L - 1], P, 0), np.tile(CB[:, :P - 1], (L, 1)),
                     np.einsum("ik,jl->ijkl", CA[:, :L - 1], CB[:, :P - 1]).reshape(L * P, -1)])
d = X.shape[1]
ix = np.arange((L - 1) * (P - 1))
Mg = (np.ones((ix.size, ix.size)) + np.equal(ix[:, None] // (P - 1), ix[None, :] // (P - 1))
      + np.equal(ix[:, None] % (P - 1), ix[None, :] % (P - 1)) + np.eye(ix.size))
Pp = np.zeros((d, d)); Pp[0, 0] = 1 / SM**2
Pp[1:L, 1:L] = (np.eye(L - 1) + np.ones((L - 1, L - 1))) / SA**2
Pp[L:L + P - 1, L:L + P - 1] = (np.eye(P - 1) + np.ones((P - 1, P - 1))) / SB**2
Pp[L + P - 1:, L + P - 1:] = Mg / SG**2
prec = X.T @ X / SE**2 + Pp
mu = np.linalg.solve(prec, X.T @ y / SE**2); cov = np.linalg.inv(prec)

with pm.Model():
    gm = pm.Normal("gm", 0.0, SM); la = pm.ZeroSumNormal("la", sigma=SA, shape=(L,))
    pr = pm.ZeroSumNormal("pr", sigma=SB, shape=(P,)); it = pm.ZeroSumNormal("it", sigma=SG, shape=(L, P), n_zerosum_axes=2)
    pm.Normal("obs", mu=gm + la[:, None] + pr[None, :] + it, sigma=SE, observed=y.reshape(L, P))
    idata = pm.sample(draws=NDRAW, tune=500, chains=2, cores=1, random_seed=SEED,
                      target_accept=0.9, progressbar=False, compute_convergence_checks=False)

la_s, pr_s, it_s = (idata.posterior["la"].values, idata.posterior["pr"].values, idata.posterior["it"].values)

def cint(i1, j1, i2, j2):
    c = np.zeros(d)
    for (i, j, w) in [(i1, j1, 1.0), (i1, j2, -1.0), (i2, j1, -1.0), (i2, j2, 1.0)]:
        c[L + P - 1:] += w * np.outer(ca(i), cb(j)).ravel()
    return c

def check(name, c, vals):
    em, es = float(c @ mu), float(np.sqrt(c @ cov @ c)); gm_, gs_ = float(vals.mean()), float(vals.std(ddof=1))
    assert abs(gm_ - em) <= max(5 * es / np.sqrt(vals.size), 0.05) and abs(gs_ - es) <= 0.08 * es, (
        f"{name}: posterior mean/sd ({gm_:.4f}, {gs_:.4f}) deviate from exact reduced-coordinate "
        f"Gaussian posterior ({em:.4f}, {es:.4f}): ZeroSumNormal prior precision is mis-scaled")

check("interaction (0,1)-(0,2)-(1,1)+(1,2)", cint(0, 1, 1, 2),
      (it_s[..., 0, 1] - it_s[..., 0, 2] - it_s[..., 1, 1] + it_s[..., 1, 2]).ravel())
check("interaction (1,0)-(1,2)-(2,0)+(2,2)", cint(1, 0, 2, 2),
      (it_s[..., 1, 0] - it_s[..., 1, 2] - it_s[..., 2, 0] + it_s[..., 2, 2]).ravel())
cp = np.zeros(d); cp[L:L + P - 1] = cb(0) - cb(1)
check("protocol 0-1", cp, (pr_s[..., 0] - pr_s[..., 1]).ravel())
print("PASS")
