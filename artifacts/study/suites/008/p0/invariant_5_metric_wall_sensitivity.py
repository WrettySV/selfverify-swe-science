import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from desc.stability.terpsichore import TerpsichoreModeTable, TerpsichoreRadialGrid, build_trig_table, build_vacmet_inputs, compute_vacmet_metrics, vacmet_boundary_from_geometry
from desc.stability.terpsichore.coefficients import _compute_outer_shell_integral_arrays_from_metric_data as integrals, _project_outer_shell_integrals_to_modal_coefficients as project

rng = np.random.default_rng(53)
geo = {k: o + 0.1 * rng.random(6) for k, o in (("R", 1.0), ("phi", 0.1), ("Z", -0.3), ("Rt", 0.5), ("phit", 0.1), ("Rp", 0.4), ("phip", 0.1), ("Zt", -0.2), ("Zp", -0.1), ("Rs", 0.3), ("Zs", -0.2), ("phis", 0.1))}
grid = TerpsichoreRadialGrid.uniform(surfs=4, ivac=2, dsvac=0.6)
modes = TerpsichoreModeTable.from_bounds(M_max=1, N_min=0, N_max=0, nfp=1, parity="cos")
trig = build_trig_table(modes, nj=3, nk=2, nper=1)
b = vacmet_boundary_from_geometry(geo)

def chain(dr, dz, rtd, ztd, rpd, zpd):
    w = {"rwall": b["rpvi"] + dr, "zwall": b["zpvi"] + dz, "rtwall": b["rtpvi"] + rtd, "ztwall": b["ztpvi"] + ztd, "rpwall": b["rppvi"] + rpd, "zpwall": b["zppvi"] + zpd}
    inp = build_vacmet_inputs(s_nodes=grid.s_nodes, ni=grid.ni, ivac=grid.ivac, dsvac=float(grid.s_nodes[-1] - 1.0), pvac=1.5, qvac=1.2, nowall=1, boundary=b, wall=w, wall_scale=1.0)
    cna, cnb = integrals(vacuum_grid_data=compute_vacmet_metrics(**inp).as_vacuum_grid_data(), trig_table=trig)
    return project(cna=cna, cnb=cnb, mode_table=modes, nper=trig.nper, lsx=trig.lsx, dtdp=1.0, cospar=1.0)

ca = chain(1.0, -0.7, 0.4, -0.3, 0.8, -0.5)
cb = chain(2.4, 0.9, -0.5, 0.4, -0.6, 0.7)
sel = ("c1", "c2", "c3", "c4", "c6")
diff = max(float(np.max(np.abs(np.asarray(ca.get(k)) - np.asarray(cb.get(k))))) for k in sel)
scale = max(float(np.max(np.abs(np.asarray(ca.get(k))))) for k in sel)
assert scale > 1e-10, "outer-shell modal coefficients vanish for a real conducting-wall geometry: wall integrals never reach the modal terms"
assert diff > 1e-10, f"modal coefficients identical for two materially different walls (max gap {diff:.3e}): wall sensitivity lost before the potential blocks"
print("PASS")
