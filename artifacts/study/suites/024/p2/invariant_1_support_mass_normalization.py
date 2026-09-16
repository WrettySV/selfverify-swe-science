import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
import pymc as pm


def main() -> None:
    sigma = 1.35
    a = np.linspace(-12.0 * sigma, 12.0 * sigma, 4001)
    x = np.stack([a, -a], axis=1)
    logp_vals = np.asarray(
        pm.logp(pm.ZeroSumNormal.dist(sigma=sigma, shape=(a.size, 2)), x).eval(), dtype=float
    )
    # on the 2-dim support line x=(a,-a) the subspace measure is sqrt(2)*da (z = sqrt(2) a)
    mass = float(np.trapz(np.exp(logp_vals), a) * np.sqrt(2.0))
    if not abs(mass - 1.0) < 1e-3:
        raise AssertionError(
            f"ZeroSumNormal density must integrate to 1 over its support line, got total mass = {mass:.6f}; "
            f"the pre-fix code raises the density to the power D/N so its mass is not 1"
        )
    print("PASS")


main()
