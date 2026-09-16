import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source"))

from pymatgen.io.cif import CifParser, MagneticCifBlock
from pymatgen.symmetry.maggroups import MagneticSpaceGroup
from pymatgen.symmetry.settings import JonesFaithfulTransformation


def keyset(ops):
    return sorted((tuple(map(tuple, np.round(op.rotation_matrix, 8))),
                   tuple(np.round(np.mod(op.translation_vector, 1.0), 6)),
                   int(op.time_reversal)) for op in ops)


def parser_ops(bns, transform):
    block = MagneticCifBlock({"_space_group_magn.number_BNS": ".".join(map(str, bns)),
                              "_space_group_magn.transform_BNS_Pp_abc": transform})
    return CifParser().get_magsymops(block)


bns, transform = [4, 9], "a,2b,c;0,0,0"
T = JonesFaithfulTransformation.from_transformation_string(transform)
back = [T.inverse.transform_symmop(op) for op in parser_ops(bns, transform)]
assert keyset(back) == keyset(MagneticSpaceGroup(bns).symmetry_ops), (
    "parser family in producer setting %r does not express back to the canonical BNS ops" % transform)
print("PASS")
