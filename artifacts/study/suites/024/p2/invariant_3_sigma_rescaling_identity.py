import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
import pymc as pm


def main() -> None:
    rng = np.random.default_rng(23)
    k, sigma0, sigma1 = 6, 0.8, 2.5
    dof = k - 1
    x = rng.normal(size=(24, k))
    x = x - x.mean(axis=1, keepdims=True)
    logp0 = np.asarray(pm.logp(pm.ZeroSumNormal.dist(sigma=sigma0, shape=(24, k)), x).eval(), dtype=float)
    logp1 = np.asarray(pm.logp(pm.ZeroSumNormal.dist(sigma=sigma1, shape=(24, k)), x).eval(), dtype=float)
    quad = np.sum(x * x, axis=1) / 2.0 * (1.0 / (sigma0 * sigma0) - 1.0 / (sigma1 * sigma1))
    # at fixed x: log f(x; s0) - log f(x; s1) = (D/2) log(s1^2/s0^2) - quad
    resid = logp0 - logp1 - dof / 2.0 * np.log((sigma1 * sigma1) / (sigma0 * sigma0)) + quad
    max_err = float(np.max(np.abs(resid)))
    if not max_err < 1e-8:
        raise AssertionError(
            f"sigma-unit consistency violated at fixed data: max |resid| = {max_err}; the exponent must carry "
            f"||x||^2/(2 s^2) with coefficient 1 (s = sd of the underlying unconstrained Normal)"
        )
    print("PASS")


main()
