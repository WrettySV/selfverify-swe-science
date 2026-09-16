import sys, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from desc.stability.terpsichore import TerpsichoreEquilibriumData, TerpsichoreModeTable, TerpsichoreRadialGrid, build_external_region_payload, build_trig_table, vacmet_inputs_from_equilibrium_data
def case(surfs, ivac, dsvac, R0, M_max, pvac=1.7, qvac=1.35):
    rg = TerpsichoreRadialGrid.uniform(surfs=surfs, ivac=ivac, dsvac=dsvac)
    mt = TerpsichoreModeTable.from_bounds(M_max=M_max, N_min=-1, N_max=1, nfp=1, parity="cos")
    tt = build_trig_table(mt, nj=4, nk=3, nper=1)
    ni, lm, nn = rg.ni, mt.size, rg.ni + ivac + 1; idx = np.arange(tt.pol.size * (ni + 1), dtype=float).reshape(tt.pol.size, ni + 1)
    d = np.arange(lm) - lm / 2; B = np.eye(lm) + 0.1 * np.abs(d[:, None] - d[None, :]) + 0.05 * R0; A = 0.05 * np.outer(d, d)
    s = 0.4 + 0.1 * np.arange(ni)
    C = {k: np.stack([B + (v - 0.4) * A * m for v in s], axis=2) for k, m in dict(c0=.1, c1=.2, c2=-.07, c4=.06, c5=-.04, c6=.09, c9=.13, c8=.05, c10=.03, c11=-.02).items()}
    prof = {k: b + a * np.arange(ni) for k, (a, b) in dict(ftp=(.1, 1.4), fpp=(.08, 1.1), ftpp=(.03, .2), fppp=(.02, .1), ci=(.04, .9), cj=(.05, 1.2)).items()}
    geo = {k: idx * a + b for k, (a, b) in dict(R=(.03, R0), phi=(.04, .25), Z=(.3, -.5), R_r=(.05, .8), R_t=(.04, .7), R_z=(.03, .6), Z_r=(.06, .5), Z_t=(.07, .45), Z_z=(.02, .35), phi_r=(.011, .18), phi_t=(.013, .09), phi_z=(.009, .07)).items()}
    data = {**geo, "pvac": pvac, "qvac": qvac, "terpsichore_coefficients": {**C, **prof, "fixed_boundary": False, "igreen": 0}, "terpsichore_dtdp": 1.0, "terpsichore_cospar": 1.0, "terpsichore_ftp_edge": prof["ftp"][-1], "terpsichore_fpp_edge": prof["fpp"][-1]}
    xi = np.resize(0.05 + 0.03 * np.arange(nn)[None, :], (lm, nn)) * (0.8 + 0.04 * np.arange(lm)[:, None])
    return TerpsichoreEquilibriumData(grid=None, radial_grid=rg, data=data), mt, tt, xi, 0.4 * xi[:, :-1]
def wall(eq, o, tilt):
    si = vacmet_inputs_from_equilibrium_data(eq, wall=None, wall_scale=1.25, nowall=1)
    r = np.linspace(0, 1, si["rpvi"].size)
    return dict(rwall=si["rpvi"] + o + tilt * r, zwall=si["zpvi"] - 0.4 * o + 0.15 * r, rtwall=si["rtpvi"] + 0.5 * o, ztwall=si["ztpvi"] - 0.3 * o, rpwall=si["rppvi"] + 0.3 * o + 0.1 * r, zpwall=si["zppvi"] - 0.2 * o)

eq, mt, tt, xi, eta = case(6, 3, 0.5, 2.9, 1, pvac=1.6, qvac=1.4)
res = [build_external_region_payload(eq, mode_table=mt, trig_table=tt, xi=xi, eta=eta, wall=wall(eq, o, t), wall_scale=1.25, nowall=1)["result"] for o, t in ((0.5, .2), (0.9, .35), (1.3, .5), (1.7, .65))]
obs = np.array([[r.wp, r.omega2] for r in res])
assert np.all(np.isfinite(obs)), f"non-finite stability observations over wall family: {obs.tolist()}"
diffs = np.abs(obs[:, None, :] - obs[None, :, :])
i, j = np.triu_indices(4, k=1); assert np.all(diffs[i, j] > 1e-9 * np.maximum(1.0, np.abs(obs)).max(axis=0)), f"materially different wall geometries collapsed to identical (wp, omega2) for some pairs:\n{obs.tolist()}\noff-diagonal gaps={np.round(diffs[i, j], 12).tolist()}"
print("PASS")
