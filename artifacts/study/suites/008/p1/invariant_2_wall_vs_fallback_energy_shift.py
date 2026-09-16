#!/usr/bin/env python3
"""An explicit conducting wall must shift the global potential energy relative
to the scaled no-explicit-wall fallback (which stays runnable/finite).
Pre-fix the wall never couples, so both return identical energies."""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "source"))
from _case_factory import make_case, make_walls, payload_for

case = make_case(surfs=6, ivac=3, dsvac=0.5, m_max=2, n_min=-1, n_max=1,
                 nfp=2, parity="cos", nj=4, nk=3, seed=202)
wall, _ = make_walls(case, variant=1)
wall_result = payload_for(case, wall, wall_scale=2.2, nowall=1)["result"]
fallback = payload_for(case, None, wall_scale=2.2, nowall=-1)["result"]
obs = np.array([wall_result.wp, wall_result.omega2, wall_result.growth_rate,
                fallback.wp, fallback.omega2, fallback.growth_rate])
assert np.all(np.isfinite(obs)), f"non-finite observations: {obs}"
scale = max(1.0, abs(wall_result.wp), abs(fallback.wp))
assert abs(wall_result.wp - fallback.wp) > 1e-8 * scale, (
    "explicit wall leaves global potential energy unchanged vs scaled "
    f"fallback (wp_wall={wall_result.wp}, wp_fallback={fallback.wp})"
)
print("PASS")
