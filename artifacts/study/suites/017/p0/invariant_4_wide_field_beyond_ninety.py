import sys
from pathlib import Path
import numpy as np
import astropy.units as u
from scipy import integrate
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from gammapy.astro.darkmatter import JFactory, profiles
from gammapy.maps import WcsGeom
def ref_los(prof, d, theta_deg, gamma):
    c, s = np.cos(np.deg2rad(theta_deg)), np.sin(np.deg2rad(theta_deg))
    l_cut = d * (c + np.sqrt(16.0 - s * s))
    f = lambda l: (prof(np.sqrt(l * l + d * d - 2 * l * d * c) * u.kpc)
                   ** gamma).to_value(u.Unit(f"GeV{gamma} cm{-3 * gamma}"))
    return integrate.quad(f, 0.0, l_cut, limit=2000)[0] * u.kpc.to(u.cm)

D_KPC, prof = 12.0, profiles.NFWProfile()
geom = WcsGeom.create(skydir=(0, 0), width=(240, 160), binsz=20, frame="galactic")
factory = JFactory(geom=geom, profile=prof, distance=D_KPC * u.kpc, annihilation=True)
with np.errstate(all="ignore"):
    try:
        jmap = factory.compute_differential_jfactor(ndecade=500)
    except Exception as exc:
        raise AssertionError(f"dJ/dOmega raised on field extending beyond 90 deg: {type(exc).__name__}: {exc}")
sep = geom.separation(geom.center_skydir).to_value(u.deg)
assert (sep > 90.0).any(), "test geometry must contain pixels with theta > 90 deg"
assert np.isfinite(jmap.value).all(), "non-finite dJ/dOmega at theta > 90 deg"
ref = np.array([[ref_los(prof, D_KPC, th, 2) for th in row] for row in sep])
rel = float(np.abs(jmap.value / ref - 1.0).max())
assert rel < 0.05, f"dJ/dOmega deviates from the direct line-of-sight integral by {rel:.1%} (tol 5%)"
print("PASS")
