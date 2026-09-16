import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from pymatgen.io.cif import CifParser, MagneticCifBlock
from pymatgen.symmetry.maggroups import MagneticSpaceGroup
from pymatgen.symmetry.settings import JonesFaithfulTransformation

BNS = [4, 9]
TRANS = "-a+b,c,a;1/2,0,0"
P, _ = JonesFaithfulTransformation.parse_transformation_string(TRANS)
Pinv = np.linalg.inv(np.asarray(P, dtype=float))
block = MagneticCifBlock(
    {"_space_group_magn.number_BNS": "4.9",
     "_space_group_magn.transform_BNS_Pp_abc": TRANS})
ops = CifParser().get_magsymops(block)
std = MagneticSpaceGroup(BNS).symmetry_ops

def keys(seq, conjugate):
    return sorted((tuple(int(round(float(v))) for v in
                         (Pinv @ R @ P if conjugate else R).ravel()),
                   int(op.time_reversal))
                  for op in seq for R in [np.asarray(op.rotation_matrix, dtype=float)])

expected = keys(std, conjugate=True)
actual = keys(ops, conjugate=False)
assert actual == expected, ("point-group ops not conjugated into producer setting: "
                            f"actual={actual} expected={expected}")
print("PASS")
