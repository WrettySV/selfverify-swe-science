#!/usr/bin/env python3
"""Wall-sensitive geometry must survive into the interval-level energy
accounting: per-interval pseudo-vacuum energy must be wall-dependent, and the
interior vacuum intervals (not just the wall boundary penalty) must be real."""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "source"))
from _case_factory import make_case, make_walls, payload_for

case = make_case(surfs=5, ivac=4, dsvac=0.4, m_max=3, n_min=0, n_max=0,
                 nfp=1, parity="cos", nj=5, nk=4, seed=303)
wall_a, wall_b = make_walls(case, variant=2)
ni = case["equilibrium_data"].radial_grid.ni
wp_a = payload_for(case, wall_a, wall_scale=1.9, nowall=1)["wp_by_interval"][ni:]
wp_b = payload_for(case, wall_b, wall_scale=1.9, nowall=1)["wp_by_interval"][ni:]
assert np.all(np.isfinite(wp_a)) and np.all(np.isfinite(wp_b)), \
    f"non-finite vacuum interval energies: {wp_a} vs {wp_b}"
scale = max(1.0, float(np.max(np.abs(wp_a))), float(np.max(np.abs(wp_b))))
assert float(np.max(np.abs(wp_a - wp_b))) > 1e-8 * scale, (
    f"vacuum interval energy identical for different walls: {wp_a} vs {wp_b}"
)
assert abs(float(wp_a[:-1].sum())) > 1e-10 * max(1.0, abs(float(wp_a.sum()))), (
    f"interior pseudo-vacuum intervals carry no energy (only wall penalty): {wp_a}"
)
print("PASS")
