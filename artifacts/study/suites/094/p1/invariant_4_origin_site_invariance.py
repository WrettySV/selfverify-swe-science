import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from pymatgen.io.cif import CifParser, MagneticCifBlock
from pymatgen.symmetry.maggroups import MagneticSpaceGroup
from pymatgen.symmetry.settings import JonesFaithfulTransformation

BNS = [4, 11]
TRANS = "a,b,c;1/3,0,0"
PROBE = np.zeros(3)  # high-symmetry boundary site: the origin
P, p = JonesFaithfulTransformation.parse_transformation_string(TRANS)
x_std = np.mod(np.asarray(P) @ PROBE + p, 1.0)
block = MagneticCifBlock(
    {"_space_group_magn.number_BNS": "4.11",
     "_space_group_magn.transform_BNS_Pp_abc": TRANS})
ops = CifParser().get_magsymops(block)
archive = sorted(
    tuple(np.round(np.mod(np.asarray(P) @ np.mod(op.operate(PROBE), 1.0) + p, 1.0), 6))
    for op in ops)
standard = sorted(
    tuple(np.round(np.mod(op.operate(x_std), 1.0), 6))
    for op in MagneticSpaceGroup(BNS).symmetry_ops)
assert archive == standard, (
    "origin-site orbit of the nonsymmorphic operation (2z|1/2,0,0) is wrong "
    "under an origin-shift setting:\n  via setting "
    f"'{TRANS}': {archive}\n  direct BNS standard: {standard}")
print("PASS")
