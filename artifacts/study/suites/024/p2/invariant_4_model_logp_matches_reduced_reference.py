import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
import pymc as pm


def centered(rng, shape, n_axes):
    x = rng.normal(size=shape)
    for ax in range(n_axes):
        x = x - x.mean(axis=-ax - 1, keepdims=True)
    return x


rng = np.random.default_rng(31)
k, l, s_l, s_p, s_i = 6, 7, 1.4, 2.1, 1.9
lab, proto, inter = centered(rng, (k,), 1), centered(rng, (l,), 1), centered(rng, (k, l), 2)
se = rng.uniform(0.2, 0.8, size=(k, l))
mu = lab[:, None] + proto[None, :] + inter
y = mu + rng.normal(size=(k, l)) * se
like = float(np.sum(-0.5 * np.log(2.0 * np.pi * se * se) - (y - mu) ** 2 / (2.0 * se * se)))
pymc_logp = sum(float(pm.logp(pm.ZeroSumNormal.dist(sigma=s, shape=sh, n_zerosum_axes=ax), x).eval())
                for s, sh, ax, x in ((s_l, (k,), 1, lab), (s_p, (l,), 1, proto), (s_i, (k, l), 2, inter)))
ref_logp = sum(-dof / 2.0 * np.log(2.0 * np.pi * s * s) - float(np.sum(x * x)) / (2.0 * s * s)
               for s, dof, x in ((s_l, k - 1, lab), (s_p, l - 1, proto), (s_i, (k - 1) * (l - 1), inter)))
err = abs((pymc_logp + like) - (ref_logp + like))
if not err < 1e-8:
    raise AssertionError(f"calibration-model logp disagrees with reduced-coordinate reference by {err}")
print("PASS")
