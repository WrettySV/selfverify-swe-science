import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from pymatgen.io.cif import CifParser, MagneticCifBlock
from pymatgen.symmetry.maggroups import MagneticSpaceGroup
from pymatgen.symmetry.settings import JonesFaithfulTransformation

BNS = [4, 9]
TRANS = "a,b,c;1/4,0,0"  # degenerate case: axes unchanged, pure origin shift
PROBE = np.array([0.19, 0.42, 0.66])
P, p = JonesFaithfulTransformation.parse_transformation_string(TRANS)
assert np.allclose(P, np.identity(3)), "test requires a pure origin-shift setting"
x_std = np.mod(np.asarray(P) @ PROBE + p, 1.0)
block = MagneticCifBlock(
    {"_space_group_magn.number_BNS": "4.9",
     "_space_group_magn.transform_BNS_Pp_abc": TRANS})
ops = CifParser().get_magsymops(block)
archive = sorted(
    tuple(np.round(np.mod(np.asarray(P) @ np.mod(op.operate(PROBE), 1.0) + p, 1.0), 6))
    for op in ops)
standard = sorted(
    tuple(np.round(np.mod(op.operate(x_std), 1.0), 6))
    for op in MagneticSpaceGroup(BNS).symmetry_ops)
assert archive == standard, (
    "pure origin-shift setting mishandled (translation must absorb (W-I)p):\n"
    f"  via setting '{TRANS}': {archive}\n  direct BNS standard: {standard}")
print("PASS")
