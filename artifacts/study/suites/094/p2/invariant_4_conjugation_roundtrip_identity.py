"""Re-expressing the archived family through the inverse transformation must
reproduce the raw BNS family exactly (change of setting twice is identity)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))

from pymatgen.io.cif import CifParser, MagneticCifBlock
from pymatgen.symmetry.maggroups import MagneticSpaceGroup
from pymatgen.symmetry.settings import JonesFaithfulTransformation

TRANSFORM = "a,b,c;-1/3,1/2,0"  # origin shift, new convention

block = MagneticCifBlock({"_space_group_magn.number_BNS": "4.9",
                          "_space_group_magn.transform_BNS_Pp_abc": TRANSFORM})
archive_ops = CifParser().get_magsymops(block)
bns_ops = MagneticSpaceGroup([4, 9]).symmetry_ops
t = JonesFaithfulTransformation.from_transformation_string(TRANSFORM)

def key(op):
    return (tuple(np.round(op.rotation_matrix, 6).flatten()),
            tuple(np.round(np.mod(op.translation_vector, 1.0), 6)), int(op.time_reversal))

mapped = {key(t.inverse.transform_symmop(op)) for op in archive_ops}
bns_family = {key(op) for op in bns_ops}
assert mapped == bns_family, (
    f"round-trip through inverse setting is not identity: {sorted(map(str, mapped))} != {sorted(map(str, bns_family))}")
print("PASS")
