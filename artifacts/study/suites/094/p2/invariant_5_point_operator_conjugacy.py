"""Under a basis change the rotation parts of the operation family must
transform by conjugation W -> P^-1 W P (point-operator representation law)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))

from pymatgen.io.cif import CifParser, MagneticCifBlock
from pymatgen.symmetry.maggroups import MagneticSpaceGroup
from pymatgen.symmetry.settings import JonesFaithfulTransformation

TRANSFORM = "b,c,a;0,0,0"  # cyclic permutation mixing axes of the 2z rotation

block = MagneticCifBlock({"_space_group_magn.number_BNS": "4.9",
                          "_space_group_magn.transform_BNS_Pp_abc": TRANSFORM})
archive_ops = CifParser().get_magsymops(block)
bns_ops = MagneticSpaceGroup([4, 9]).symmetry_ops
t = JonesFaithfulTransformation.from_transformation_string(TRANSFORM)
P = np.array(t.P, dtype=float)
Q = np.linalg.inv(P)

expected = {tuple(np.round(Q @ W @ P, 6).flatten()) for W in (op.rotation_matrix for op in bns_ops)}
got = {tuple(np.round(op.rotation_matrix, 6).flatten()) for op in archive_ops}
assert got == expected, (
    f"rotation parts not conjugated into archive basis: {sorted(got)} != {sorted(expected)}")
print("PASS")
