import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
import pymc as pm


def main() -> None:
    rng = np.random.default_rng(7)
    for k, sigma in ((7, 1.1), (10, 2.8)):
        dof = k - 1
        x = rng.normal(size=(32, k))
        x = x - x.mean(axis=1, keepdims=True)
        logp_vals = np.asarray(
            pm.logp(pm.ZeroSumNormal.dist(sigma=sigma, shape=(32, k)), x).eval(), dtype=float
        )
        expected = -dof / 2.0 * np.log(2.0 * np.pi * sigma * sigma) - np.sum(x * x, axis=1) / (2.0 * sigma * sigma)
        max_err = float(np.max(np.abs(logp_vals - expected)))
        if not max_err < 1e-8:
            raise AssertionError(
                f"vector ZeroSumNormal density wrong: max |logp - (2 pi s^2)^(-D/2) exp(-||x||^2/2s^2)| "
                f"= {max_err} (k={k}, s={sigma}); a correct fix must put the Gaussian density "
                f"on the D={dof}-dim zero-sum hyperplane, not a rescaled product of entries"
            )
    print("PASS")


main()
