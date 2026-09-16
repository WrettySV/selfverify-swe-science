import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source"))
sys.path.insert(0, str(ROOT))

from pymatgen.symmetry.maggroups import MagneticSpaceGroup
from pymatgen.symmetry.settings import JonesFaithfulTransformation
from workflow.magnetic_catalogue import MagneticRecord, operation_family

bns, basis = [4, 9], "a,c,b;0,0,0"
probe = [0.2, 0.31, 0.42]
record = MagneticRecord(record_id="inv4", bns_number=tuple(bns), archive_basis=basis,
                        probe_fractional_site=np.array(probe))
family = operation_family(record)
T = JonesFaithfulTransformation.from_transformation_string(basis)
q_bns = np.mod(np.array(T.P) @ np.array(probe) + np.array(T.p), 1.0)
expected = sorted((int(op.time_reversal), tuple(np.round(np.mod(op.operate(q_bns), 1.0), 6)))
                  for op in MagneticSpaceGroup(bns).symmetry_ops)
got = sorted((pt["time"], tuple(np.round(pt["catalogue_xyz"], 6))) for pt in family["probe_orbit"])
assert got == expected, (
    "catalogue orbit of a generic probe point depends on the producer coordinate convention: %r != %r"
    % (got, expected))
print("PASS")
