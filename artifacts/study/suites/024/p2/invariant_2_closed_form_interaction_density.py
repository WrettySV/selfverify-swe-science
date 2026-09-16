import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
import pymc as pm


def main() -> None:
    rng = np.random.default_rng(11)
    k, l, sigma = 6, 7, 1.4
    dof = (k - 1) * (l - 1)
    w = rng.normal(size=(12, k, l))
    a = w - w.mean(axis=2, keepdims=True)
    x = a - a.mean(axis=1, keepdims=True)
    logp_vals = np.asarray(
        pm.logp(pm.ZeroSumNormal.dist(sigma=sigma, shape=(12, k, l), n_zerosum_axes=2), x).eval(),
        dtype=float,
    )
    expected = -dof / 2.0 * np.log(2.0 * np.pi * sigma * sigma) - np.sum(x * x, axis=(1, 2)) / (2.0 * sigma * sigma)
    max_err = float(np.max(np.abs(logp_vals - expected)))
    if not max_err < 1e-8:
        raise AssertionError(
            f"two-axis (interaction) ZeroSumNormal density wrong: max |logp - expected| = {max_err} "
            f"({k}x{l}, s={sigma}, D={dof}); the fix must count only the D free coordinates in the normalizer"
        )
    print("PASS")


main()
