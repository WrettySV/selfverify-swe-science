"""The catalogue-frame orbit of an archived site must be a COMPLETE orbit:
closed under every BNS operation (symmetry-equivalent sites form a group orbit)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))

from pymatgen.io.cif import CifParser, MagneticCifBlock
from pymatgen.symmetry.maggroups import MagneticSpaceGroup
from pymatgen.symmetry.settings import JonesFaithfulTransformation

TRANSFORM, PROBE = "c,a,b;0,0,0", [0.2, 0.45, 0.61]  # cyclic permutation, generic site

block = MagneticCifBlock({"_space_group_magn.number_BNS": "4.11",
                          "_space_group_magn.transform_BNS_Pp_abc": TRANSFORM})
archive_ops = CifParser().get_magsymops(block)
bns_ops = MagneticSpaceGroup([4, 11]).symmetry_ops
t = JonesFaithfulTransformation.from_transformation_string(TRANSFORM)
P, p = np.array(t.P, dtype=float), np.array(t.p, dtype=float)

orbit = [tuple(np.round(np.mod(P @ np.mod(op.operate(np.array(PROBE)), 1.0) + p, 1.0), 6))
         for op in archive_ops]
for y in set(orbit):
    for h in bns_ops:
        hy = tuple(np.round(np.mod(h.operate(np.array(y)), 1.0), 6))
        if hy not in orbit:
            raise AssertionError(f"catalogue orbit not closed under BNS op: {hy} missing from {orbit}")
print("PASS")
