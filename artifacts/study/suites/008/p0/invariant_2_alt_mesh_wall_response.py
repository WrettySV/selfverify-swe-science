import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from desc.stability.terpsichore import (TerpsichoreEquilibriumData, TerpsichoreModeTable, TerpsichoreRadialGrid, build_trig_table, build_external_region_payload, vacmet_inputs_from_equilibrium_data)

seed, surfs, ivac, dsvac = 29, 6, 2, 0.8
rng = np.random.default_rng(seed)
grid = TerpsichoreRadialGrid.uniform(surfs=surfs, ivac=ivac, dsvac=dsvac)
modes = TerpsichoreModeTable.from_bounds(M_max=1, N_min=0, N_max=0, nfp=1, parity="cos")
trig = build_trig_table(modes, nj=3, nk=2, nper=1)
b = 0.1 * rng.random((trig.pol.size, grid.ni + 1))
geom = {k: o + s * b for k, o, s in (("R", 3.4, 0.12), ("phi", 0.25, 0.06), ("Z", 0.3, 0.18), ("R_r", 0.95, 0.08), ("R_t", 0.75, 0.05), ("R_z", 0.65, 0.04), ("Z_r", 0.55, 0.06), ("Z_t", 0.45, 0.07), ("Z_z", 0.35, 0.03), ("phi_r", 0.18, 0.015), ("phi_t", 0.12, 0.016), ("phi_z", 0.09, 0.013))}
coeffs = {k: 0.2 + 0.3 * rng.random((modes.size, modes.size, grid.ni)) for k in ("c0", "c1", "c2", "c4", "c5", "c6", "c9", "c8", "c10", "c11")}
prof = {k: o + 0.1 * rng.random(grid.ni) for k, o in (("ftp", 1.1), ("fpp", 2.2), ("ftpp", 0.25), ("fppp", 0.12), ("ci", 0.85), ("cj", 1.35))}
eq = TerpsichoreEquilibriumData(grid=None, radial_grid=grid, data={**geom, "pvac": 1.3, "qvac": 1.8, "terpsichore_coefficients": {**coeffs, **prof, "fixed_boundary": False, "igreen": 0}})
xr = np.random.default_rng(33)
xi, eta = 0.3 * xr.random((modes.size, grid.n_intervals + 1)), 0.3 * xr.random((modes.size, grid.n_intervals))
bi = vacmet_inputs_from_equilibrium_data(eq, wall=None, wall_scale=1.0, nowall=1)
wa = {"rwall": bi["rpvi"] + 2.2, "zwall": bi["zpvi"] - 0.6, "rtwall": bi["rtpvi"] + 0.5, "ztwall": bi["ztpvi"] + 0.3, "rpwall": bi["rppvi"] + 1.1, "zpwall": bi["zppvi"] - 0.4}
wb = {"rwall": bi["rpvi"] + 0.7, "zwall": bi["zpvi"] + 1.6, "rtwall": bi["rtpvi"] - 0.6, "ztwall": bi["ztpvi"] + 0.4, "rpwall": bi["rppvi"] - 0.9, "zpwall": bi["zppvi"] + 0.5}
ra = build_external_region_payload(eq, mode_table=modes, trig_table=trig, xi=xi, eta=eta, wall=wa, wall_scale=1.4, nowall=1)
rb = build_external_region_payload(eq, mode_table=modes, trig_table=trig, xi=xi, eta=eta, wall=wb, wall_scale=1.4, nowall=1)
rf = build_external_region_payload(eq, mode_table=modes, trig_table=trig, xi=xi, eta=eta, wall=None, wall_scale=1.4, nowall=-1)
oa, ob, of = (np.array([r["result"].wp, r["result"].omega2, r["result"].growth_rate]) for r in (ra, rb, rf))
assert np.all(np.isfinite(np.concatenate([oa, ob, of]))), f"non-finite observation: wall_a={oa} wall_b={ob} fallback={of}"
gw, gf = float(np.max(np.abs(oa - ob))), float(np.max(np.abs(oa - of)))
assert gw > 1e-9 and gf > 1e-9, f"wall response collapsed on alternate mesh (wall gap {gw:.3e}, no-wall fallback gap {gf:.3e}); outer-region wall coupling is missing"
print("PASS")
