"""Same convention-invariance of the symmetry orbit, now with a non-identity
basis change P (axis swap + origin shift) on a different group and probe."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))

from pymatgen.io.cif import CifParser, MagneticCifBlock
from pymatgen.symmetry.maggroups import MagneticSpaceGroup
from pymatgen.symmetry.settings import JonesFaithfulTransformation

TRANSFORM = "b,a,c;-1/4,0,0"   # basis change with origin shift
PROBE = [0.22, 0.31, 0.55]     # generic archive-frame site

block = MagneticCifBlock({"_space_group_magn.number_BNS": "4.11",
                          "_space_group_magn.transform_BNS_Pp_abc": TRANSFORM})
archive_ops = CifParser().get_magsymops(block)
bns_ops = MagneticSpaceGroup([4, 11]).symmetry_ops
t = JonesFaithfulTransformation.from_transformation_string(TRANSFORM)
P, p = np.array(t.P, dtype=float), np.array(t.p, dtype=float)

x_arch, x_bns = np.array(PROBE), np.mod(P @ np.array(PROBE) + p, 1.0)
archive_pts = [np.mod(op.operate(x_arch), 1.0) for op in archive_ops]
catalogue_orbit = sorted({tuple(np.round(np.mod(P @ y + p, 1.0), 6)) for y in archive_pts})
bns_orbit = sorted({tuple(np.round(np.mod(op.operate(x_bns), 1.0), 6)) for op in bns_ops})
assert catalogue_orbit == bns_orbit, (
    f"orbit depends on coordinate convention: catalogue {catalogue_orbit} != BNS {bns_orbit}")
print("PASS")
