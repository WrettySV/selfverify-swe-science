#!/usr/bin/env python3
"""The wall-sensitive modal families must reach the outer-shell interval
blocks: vacuum potential blocks must be non-zero and differ between walls."""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "source"))
from _case_factory import make_case, make_walls, outer_response_for

case = make_case(surfs=8, ivac=3, dsvac=0.3, m_max=2, n_min=0, n_max=0,
                 nfp=1, parity="cos", nj=6, nk=2, seed=505)
wall_a, wall_b = make_walls(case, variant=4)
blocks_a = outer_response_for(case, wall_a, wall_scale=2.0, nowall=1).potential_blocks
blocks_b = outer_response_for(case, wall_b, wall_scale=2.0, nowall=1).potential_blocks
fields = ("A", "B", "C", "D", "E", "F", "G", "H", "BL", "BU")
max_abs = max(float(np.max(np.abs(getattr(blocks_a, n)))) for n in fields)
max_abs_b = max(float(np.max(np.abs(getattr(blocks_b, n)))) for n in fields)
max_diff = max(float(np.max(np.abs(getattr(blocks_a, n) - getattr(blocks_b, n)))) for n in fields)
scale = max(1.0, max_abs, max_abs_b)
assert max_abs > 1e-10, "outer-shell potential blocks are identically zero"
assert max_diff > 1e-8 * scale, (
    f"outer-shell potential blocks are wall-blind (max diff={max_diff})"
)
print("PASS")
