import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from desc.stability.terpsichore import TerpsichoreModeTable, TerpsichoreRadialGrid
from desc.stability.terpsichore.assembly import _assemble_outer_shell_potential_blocks_from_modal_terms as outer

def terms(seed):
    rng = np.random.default_rng(seed)
    return {k: 0.2 + 0.4 * rng.random((2, 2, 2)) for k in ("c1", "c2", "c3", "c4", "c5", "c6")}

def gap(a, b):
    return max(float(np.max(np.abs(np.asarray(getattr(a, f)) - np.asarray(getattr(b, f))))) for f in a.__dataclass_fields__)

grid = TerpsichoreRadialGrid.uniform(surfs=4, ivac=2, dsvac=0.65)
modes = TerpsichoreModeTable.from_bounds(M_max=1, N_min=0, N_max=0, nfp=1, parity="cos")
kw = dict(radial_grid=grid, mode_table=modes)
base = outer(ftp_edge=1.2, fpp_edge=2.0, **terms(31), **kw)
alt = outer(ftp_edge=1.2, fpp_edge=2.0, **terms(37), **kw)
bare = outer(ftp_edge=1.2, fpp_edge=2.0, **{k: np.zeros((2, 2, 2)) for k in ("c1", "c2", "c3", "c4", "c5", "c6")}, **kw)
edge = outer(ftp_edge=1.4, fpp_edge=2.3, **terms(31), **kw)
assert gap(base, bare) > 1e-9, "non-zero modal terms c1..c6 left the outer-shell potential blocks as the bare scaffold"
assert gap(base, alt) > 1e-9, "outer-shell potential blocks do not respond to different modal coefficient sets, so wall dependence cannot reach them"
assert gap(base, edge) > 1e-9, "outer-shell potential blocks ignore the frozen plasma-edge profile values (ftp_edge/fpp_edge)"
print("PASS")
