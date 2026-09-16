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


bns = [4, 9]
T1, T2 = (JonesFaithfulTransformation.from_transformation_string(s) for s in ("a,2b,c;0,0,0", "b,a,c;0,0,0"))
fam1, fam2 = (parser_ops(bns, s) for s in ("a,2b,c;0,0,0", "b,a,c;0,0,0"))
mapped = [T2.transform_symmop(T1.inverse.transform_symmop(op)) for op in fam1]
assert keyset(mapped) == keyset(fam2), "operation family is not equivariant under a change of producer basis"
print("PASS")
