import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from desc.stability.terpsichore import (TerpsichoreEquilibriumData, TerpsichoreModeTable, TerpsichoreRadialGrid, build_trig_table, build_external_region_payload, vacmet_inputs_from_equilibrium_data)

seed, surfs, ivac, dsvac = 11, 5, 3, 0.55
rng = np.random.default_rng(seed)
grid = TerpsichoreRadialGrid.uniform(surfs=surfs, ivac=ivac, dsvac=dsvac)
modes = TerpsichoreModeTable.from_bounds(M_max=1, N_min=0, N_max=0, nfp=1, parity="cos")
trig = build_trig_table(modes, nj=3, nk=2, nper=1)
b = 0.1 * rng.random((trig.pol.size, grid.ni + 1))
geom = {k: o + s * b for k, o, s in (("R", 2.7, 0.1), ("phi", 0.2, 0.05), ("Z", -0.5, 0.2), ("R_r", 0.9, 0.07), ("R_t", 0.8, 0.06), ("R_z", 0.7, 0.04), ("Z_r", 0.6, 0.05), ("Z_t", 0.5, 0.08), ("Z_z", 0.4, 0.03), ("phi_r", 0.2, 0.012), ("phi_t", 0.1, 0.014), ("phi_z", 0.08, 0.011))}
coeffs = {k: 0.2 + 0.3 * rng.random((modes.size, modes.size, grid.ni)) for k in ("c0", "c1", "c2", "c4", "c5", "c6", "c9", "c8", "c10", "c11")}
prof = {k: o + 0.1 * rng.random(grid.ni) for k, o in (("ftp", 1.2), ("fpp", 2.0), ("ftpp", 0.2), ("fppp", 0.1), ("ci", 0.9), ("cj", 1.3))}
eq = TerpsichoreEquilibriumData(grid=None, radial_grid=grid, data={**geom, "pvac": 1.6, "qvac": 1.3, "terpsichore_coefficients": {**coeffs, **prof, "fixed_boundary": False, "igreen": 0}})
xr = np.random.default_rng(12)
xi, eta = 0.3 * xr.random((modes.size, grid.n_intervals + 1)), 0.3 * xr.random((modes.size, grid.n_intervals))
bi = vacmet_inputs_from_equilibrium_data(eq, wall=None, wall_scale=1.0, nowall=1)
wa = {"rwall": bi["rpvi"] + 1.0, "zwall": bi["zpvi"] - 0.7, "rtwall": bi["rtpvi"] + 0.4, "ztwall": bi["ztpvi"] - 0.3, "rpwall": bi["rppvi"] + 0.8, "zpwall": bi["zppvi"] - 0.5}
wb = {"rwall": bi["rpvi"] + 2.6, "zwall": bi["zpvi"] + 0.9, "rtwall": bi["rtpvi"] - 0.5, "ztwall": bi["ztpvi"] + 0.4, "rpwall": bi["rppvi"] - 0.6, "zpwall": bi["zppvi"] + 0.7}
ra = build_external_region_payload(eq, mode_table=modes, trig_table=trig, xi=xi, eta=eta, wall=wa, wall_scale=1.15, nowall=1)
rb = build_external_region_payload(eq, mode_table=modes, trig_table=trig, xi=xi, eta=eta, wall=wb, wall_scale=1.15, nowall=1)
oa = np.array([ra["result"].wp, ra["result"].omega2, ra["result"].growth_rate])
ob = np.array([rb["result"].wp, rb["result"].omega2, rb["result"].growth_rate])
assert np.all(np.isfinite(np.concatenate([oa, ob]))), f"non-finite wall-coupled observations: {oa} vs {ob}"
gap = float(np.max(np.abs(oa - ob)))
assert gap > 1e-9, f"materially different conducting walls collapsed to identical observations (max gap {gap:.3e}); wall coupling is missing from the outer region"
print("PASS")
