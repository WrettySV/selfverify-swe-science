#!/usr/bin/env python3
"""Wall-sensitive VACMET metrics must reach the reduced outer-region modal
coefficients (FOURIN sum/difference projection): non-zero and wall-aware."""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "source"))
from _case_factory import make_case, make_walls, outer_response_for

case = make_case(surfs=7, ivac=2, dsvac=0.9, m_max=1, n_min=-1, n_max=1,
                 nfp=3, parity="sin", nj=3, nk=5, seed=404)
wall_a, wall_b = make_walls(case, variant=3)
coeff_a = outer_response_for(case, wall_a, wall_scale=1.4, nowall=1).coefficients
coeff_b = outer_response_for(case, wall_b, wall_scale=1.4, nowall=1).coefficients
names = ("c0", "c1", "c2", "c3", "c4", "c6")
max_abs_a = max(float(np.max(np.abs(coeff_a[n]))) for n in names)
max_abs_b = max(float(np.max(np.abs(coeff_b[n]))) for n in names)
max_diff = max(float(np.max(np.abs(coeff_a[n] - coeff_b[n]))) for n in names)
scale = max(1.0, max_abs_a, max_abs_b)
assert max_abs_a > 1e-10 and max_abs_b > 1e-10, (
    f"projected vacuum modal coefficients are identically zero ({max_abs_a}, {max_abs_b})"
)
assert max_diff > 1e-8 * scale, (
    f"projected vacuum modal coefficients are wall-blind (max diff={max_diff})"
)
print("PASS")
