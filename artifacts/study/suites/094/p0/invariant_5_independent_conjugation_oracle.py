import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source"))

from pymatgen.io.cif import CifParser, MagneticCifBlock
from pymatgen.symmetry.maggroups import MagneticSpaceGroup

bns, p_shift = [4, 11], [-0.25, 0.0, 0.0]
P = np.identity(3)
block = MagneticCifBlock({"_space_group_magn.number_BNS": ".".join(map(str, bns)),
                          "_space_group_magn.transform_BNS_Pp_abc": "a,b,c;-1/4,0,0"})
got = CifParser().get_magsymops(block)
canonical = MagneticSpaceGroup(bns).symmetry_ops
oracle = sorted((tuple(map(tuple, np.round(np.linalg.inv(P) @ op.rotation_matrix @ P, 8))),
                 tuple(np.round(np.mod(np.linalg.inv(P) @ (op.translation_vector +
                        (op.rotation_matrix - P) @ p_shift), 1.0), 6)),
                 int(op.time_reversal)) for op in canonical)
keyset = sorted((tuple(map(tuple, np.round(op.rotation_matrix, 8))),
                 tuple(np.round(np.mod(op.translation_vector, 1.0), 6)),
                 int(op.time_reversal)) for op in got)
assert len(got) == len(canonical) and keyset == oracle, (
    "parser output is not the Jones-Faithful conjugate of the BNS ops for the origin-shifted setting")
print("PASS")
