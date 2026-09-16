#!/usr/bin/env python3
"""Distinct conducting walls must give distinct global energy/stability
observations (new mesh, new mode table, new walls). Pre-fix the dead
outer-region path collapses both walls to identical internal-only values."""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "source"))
from _case_factory import make_case, make_walls, payload_for

case = make_case(surfs=6, ivac=3, dsvac=0.5, m_max=2, n_min=-1, n_max=1,
                 nfp=2, parity="cos", nj=4, nk=3, seed=101)
wall_a, wall_b = make_walls(case, variant=0)
result_a = payload_for(case, wall_a, wall_scale=1.6, nowall=1)["result"]
result_b = payload_for(case, wall_b, wall_scale=1.6, nowall=1)["result"]
obs_a = np.array([result_a.wp, result_a.omega2, result_a.growth_rate])
obs_b = np.array([result_b.wp, result_b.omega2, result_b.growth_rate])
assert np.all(np.isfinite(obs_a)) and np.all(np.isfinite(obs_b)), \
    f"non-finite stability observations: {obs_a} vs {obs_b}"
scale = max(1.0, float(np.max(np.abs(obs_a))), float(np.max(np.abs(obs_b))))
assert abs(result_a.wp - result_b.wp) > 1e-8 * scale, (
    "global potential energy identical for two materially different walls "
    f"(wp_a={result_a.wp}, wp_b={result_b.wp}); wall coupling absent"
)
print("PASS")
