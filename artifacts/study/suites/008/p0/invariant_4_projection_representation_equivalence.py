import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from desc.stability.terpsichore import TerpsichoreModeTable, build_trig_table
from desc.stability.terpsichore.coefficients import _project_outer_shell_integrals_to_modal_coefficients as project, compute_fourin_mapping_indices

modes = TerpsichoreModeTable.from_bounds(M_max=1, N_min=0, N_max=0, nfp=1, parity="cos")
trig = build_trig_table(modes, nj=3, nk=2, nper=1)
rng = np.random.default_rng(41)
cna = 0.5 + rng.random((7, trig.lss + 1, 2))
cnb = 0.5 + rng.random((7, trig.lss + 1, 2))
dtdp, cospar = 1.7, 0.6
idx = compute_fourin_mapping_indices(modes, nper=trig.nper, lsx=trig.lsx)
got = project(cna=cna, cnb=cnb, mode_table=modes, nper=trig.nper, lsx=trig.lsx, dtdp=dtdp, cospar=cospar)
for name, kind, row in (("c2", "a", 1), ("c6", "a", 2), ("c7", "a", 3), ("c5", "a", 4), ("c0", "a", 6), ("c1", "b", 1), ("c3", "b", 2), ("c4", "b", 3)):
    src, sign = (cna, -1.0) if kind == "a" else (cnb, 1.0)
    want = dtdp * (src[row, idx["ld"]] + sign * cospar * src[row, idx["lp"]])
    have = np.asarray(got.get(name))
    assert float(np.max(np.abs(want))) > 1e-8, f"degenerate reference values for {name}"
    assert np.allclose(have, want, rtol=1e-12, atol=1e-14), f"modal coefficient {name} breaks the FOURIN sum/difference projection (max deviation {float(np.max(np.abs(have - want))):.3e})"
print("PASS")
