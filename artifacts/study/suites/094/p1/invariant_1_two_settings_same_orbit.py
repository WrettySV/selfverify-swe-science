import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from pymatgen.io.cif import CifParser, MagneticCifBlock
from pymatgen.symmetry.settings import JonesFaithfulTransformation

BNS = "4.9"
T1, T2 = "b,c,a;0,0,0", "a,b,c;1/4,0,0"
X_STD0 = np.array([0.23, 0.47, 0.58])

def orbit_in_standard_coords(trans, x_prod):
    P, p = JonesFaithfulTransformation.parse_transformation_string(trans)
    block = MagneticCifBlock(
        {"_space_group_magn.number_BNS": BNS,
         "_space_group_magn.transform_BNS_Pp_abc": trans})
    ops = CifParser().get_magsymops(block)
    return sorted(
        tuple(np.round(np.mod(np.asarray(P) @ np.mod(op.operate(x_prod), 1.0) + p, 1.0), 6))
        for op in ops)

P1, p1 = JonesFaithfulTransformation.parse_transformation_string(T1)
P2, p2 = JonesFaithfulTransformation.parse_transformation_string(T2)
o1 = orbit_in_standard_coords(T1, np.mod(np.linalg.inv(P1) @ (X_STD0 - p1), 1.0))
o2 = orbit_in_standard_coords(T2, np.mod(np.linalg.inv(P2) @ (X_STD0 - p2), 1.0))
assert o1 == o2, (
    "two valid producer conventions for the same magnetic symmetry give "
    "different catalogue orbits:\n  " + T1 + f": {o1}\n  " + T2 + f": {o2}")
print("PASS")
