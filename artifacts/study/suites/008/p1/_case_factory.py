"""Shared case factory for the TERPSICHORE vacuum-plus-wall invariant tests.

Each test script in this directory imports this helper to build a *new*
reduced vacuum-plus-wall external-region case (its own radial mesh, mode
table, trigonometric tables, equilibrium geometry, perturbation amplitudes,
and conducting walls).  Nothing here reuses the public reproduction fixture:
every array is constructed from scratch with deterministic, parameterized
values so that the invariant tests probe generalization (new lattice
constants, new meshes, new mode tables, new unit-like scalings) rather than
the single public case.
"""

from __future__ import annotations

import numpy as np

from desc.stability.terpsichore.equilibrium import (
    TerpsichoreEquilibriumData,
    vacmet_inputs_from_equilibrium_data,
)
from desc.stability.terpsichore.modes import TerpsichoreModeTable
from desc.stability.terpsichore.radial import TerpsichoreRadialGrid
from desc.stability.terpsichore.trig import build_trig_table


def _smooth_geometry(pol, ni):
    """Build rank-2 (points, ni+1) equilibrium geometry arrays on the
    plasma side of a new toroidal-flux grid.  All fields are smooth,
    single-valued in the angles and strictly positive where the VACMET
    Jacobian requires it."""
    pts = pol.size
    s_col = np.linspace(0.0, 1.0, ni + 1)

    def tile(column):
        return np.broadcast_to(np.asarray(column, dtype=float)[None, :], (pts, ni + 1))

    r0 = 3.0 + 0.35 * np.cos(pol) + 0.10 * np.cos(2.0 * pol)
    z0 = 0.55 * np.sin(pol)
    geometry = {
        "R": r0[:, None] * (1.0 + 0.06 * s_col[None, :]),
        "Z": z0[:, None] * (0.4 + 0.6 * s_col[None, :]),
        "phi": tile((2.0 * np.pi / ni) * s_col),
        "R_r": tile(0.18 + 0.05 * s_col) + 0.02 * np.cos(pol)[:, None],
        "R_t": -0.40 * np.sin(pol)[:, None] - 0.05 * np.sin(2.0 * pol)[:, None],
        "R_z": tile(np.full(ni + 1, 0.22)) + 0.03 * np.cos(pol)[:, None],
        "Z_r": tile(0.09 + 0.04 * s_col) + 0.02 * np.sin(pol)[:, None],
        "Z_t": 0.50 * np.cos(pol)[:, None],
        "Z_z": tile(np.full(ni + 1, 0.15)) + 0.02 * np.sin(pol)[:, None],
        "phi_r": tile(0.03 + 0.01 * s_col),
        "phi_t": np.full((pts, ni + 1), 1.0),
        "phi_z": tile(np.full(ni + 1, 0.98)) + 0.01 * np.cos(pol)[:, None],
    }
    return geometry


def _plasma_coefficients(lmns, ni):
    """Diagonally dominant (lmns, lmns, ni) coefficient stack with a smooth
    radial scale so the plasma branch of LHSMAT/RHSMAT stays well posed."""
    base = 1.2 * np.eye(lmns) + 0.2 * np.ones((lmns, lmns))
    alt = 0.5 * np.eye(lmns) - 0.1 * np.ones((lmns, lmns))
    layers = [
        (base + (0.1 * i + 0.05) * alt) * (1.0 + 0.07 * i) for i in range(ni)
    ]
    return np.stack(layers, axis=2)


def make_case(
    *,
    surfs,
    ivac,
    dsvac,
    m_max,
    n_min,
    n_max,
    nfp,
    parity,
    nj,
    nk,
    seed,
    pvac=1.55,
    qvac=1.20,
):
    """Assemble one self-contained vacuum-plus-wall case (equilibrium data,
    mode table, trig tables, and generic perturbation amplitudes)."""
    radial_grid = TerpsichoreRadialGrid.uniform(surfs=surfs, ivac=ivac, dsvac=dsvac)
    mode_table = TerpsichoreModeTable.from_bounds(
        M_max=m_max, N_min=n_min, N_max=n_max, nfp=nfp, parity=parity
    )
    trig_table = build_trig_table(mode_table, nj=nj, nk=nk, nper=nfp)
    lmns = mode_table.size
    ni = radial_grid.ni
    geometry = _smooth_geometry(trig_table.pol, ni)
    stack = _plasma_coefficients(lmns, ni)
    profiles = {
        "ftp": np.linspace(1.50, 1.70, ni),
        "fpp": np.linspace(1.10, 1.30, ni),
        "ftpp": np.linspace(0.20, 0.30, ni),
        "fppp": np.linspace(0.14, 0.19, ni),
        "ci": np.linspace(0.80, 0.95, ni),
        "cj": np.linspace(1.20, 1.35, ni),
    }
    data = dict(
        geometry,
        pvac=pvac,
        qvac=qvac,
        terpsichore_coefficients={
            "c0": stack,
            "c1": stack,
            "c2": stack,
            "c4": stack,
            "c5": stack,
            "c6": stack,
            "c9": stack,
            "c8": stack,
            "c10": stack,
            "c11": stack,
            **profiles,
            "fixed_boundary": False,
            "igreen": 0,
        },
        terpsichore_dtdp=1.0,
        terpsichore_cospar=1.0,
        terpsichore_ftp_edge=profiles["ftp"][-1],
        terpsichore_fpp_edge=profiles["fpp"][-1],
    )
    equilibrium_data = TerpsichoreEquilibriumData(
        grid=None, radial_grid=radial_grid, data=data
    )
    rng = np.random.default_rng(seed)
    xi = 0.12 * rng.standard_normal((lmns, ni + ivac + 1))
    eta = 0.06 * rng.standard_normal((lmns, ni + ivac))
    return {
        "equilibrium_data": equilibrium_data,
        "mode_table": mode_table,
        "trig_table": trig_table,
        "xi": xi,
        "eta": eta,
    }


def make_walls(case, variant=0):
    """Return two materially different explicit conducting walls derived from
    the plasma-vacuum boundary of ``case``.  ``variant`` selects distinct
    radial offsets, shapes and phase harmonics so different invariant tests
    exercise different wall geometries."""
    equilibrium_data = case["equilibrium_data"]
    boundary = vacmet_inputs_from_equilibrium_data(
        equilibrium_data, wall=None, wall_scale=1.0, nowall=1
    )
    pol = case["trig_table"].pol
    ramp = np.linspace(0.20 + 0.05 * variant, 0.60 + 0.05 * variant, pol.size)
    base_a = 1.50 - 0.05 * variant
    base_b = 1.20 + 0.05 * variant
    wall_a = {
        "rwall": base_a * boundary["rpvi"] + 0.40 + 0.15 * np.cos(pol),
        "zwall": -1.15 - 0.50 * np.sin(pol) - 0.30 * ramp,
        "rtwall": boundary["rtpvi"] + 0.65,
        "ztwall": boundary["ztpvi"] - 0.45,
        "rpwall": boundary["rppvi"] + 0.42 + 0.30 * ramp,
        "zpwall": boundary["zppvi"] - 0.22 - 0.30 * ramp,
    }
    wall_b = {
        "rwall": base_b * boundary["rpvi"] + 1.15 + 0.45 * np.sin(2.0 * pol),
        "zwall": 0.85 + 0.70 * np.cos(pol) + 0.40 * ramp,
        "rtwall": boundary["rtpvi"] - 0.50,
        "ztwall": boundary["ztpvi"] + 0.60,
        "rpwall": boundary["rppvi"] - 0.35 + 0.50 * ramp,
        "zpwall": boundary["zppvi"] + 0.55 - 0.20 * ramp,
    }
    return wall_a, wall_b


def payload_for(case, wall, *, wall_scale, nowall=1):
    """Run the wall-coupled external-region pipeline on ``case``."""
    from desc.stability.terpsichore.external_region import build_external_region_payload

    return build_external_region_payload(
        case["equilibrium_data"],
        mode_table=case["mode_table"],
        trig_table=case["trig_table"],
        xi=case["xi"],
        eta=case["eta"],
        wall=wall,
        wall_scale=wall_scale,
        nowall=nowall,
    )


def outer_response_for(case, wall, *, wall_scale, nowall=1):
    """Run the reduced outer-region chain (VACMET -> modal projection ->
    outer-shell assembly) on ``case`` and return the response payload."""
    from desc.stability.terpsichore.outer_region import (
        assemble_outer_region_response_payload,
        build_outer_region_metric_payload,
        build_outer_region_operator_payload,
    )
    from desc.stability.terpsichore.vacuum import compute_vacmet_metrics

    inputs = vacmet_inputs_from_equilibrium_data(
        case["equilibrium_data"], wall=wall, wall_scale=wall_scale, nowall=nowall
    )
    metric_payload = build_outer_region_metric_payload(
        equilibrium_data=case["equilibrium_data"],
        vacuum_grid_data=compute_vacmet_metrics(**inputs).as_vacuum_grid_data(),
    )
    operator_payload = build_outer_region_operator_payload(
        metric_payload=metric_payload,
        mode_table=case["mode_table"],
        trig_table=case["trig_table"],
        radial_grid=case["equilibrium_data"].radial_grid,
    )
    return assemble_outer_region_response_payload(
        metric_payload=metric_payload,
        operator_payload=operator_payload,
        mode_table=case["mode_table"],
        radial_grid=case["equilibrium_data"].radial_grid,
    )
