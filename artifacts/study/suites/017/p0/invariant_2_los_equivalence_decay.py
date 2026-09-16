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

D_KPC, prof = 6.0, profiles.BurkertProfile()
geom = WcsGeom.create(skydir=(0, 0), width=(60, 60), binsz=10, frame="galactic")
factory = JFactory(geom=geom, profile=prof, distance=D_KPC * u.kpc, annihilation=False)
with np.errstate(all="ignore"):
    try:
        dmap = factory.compute_differential_jfactor(ndecade=500)
    except Exception as exc:
        raise AssertionError(f"decay dOmega raised: {type(exc).__name__}: {exc}")
sep = geom.separation(geom.center_skydir).to_value(u.deg)
assert dmap.shape == geom.data_shape and np.isfinite(dmap.value).all(), "non-finite or mis-shaped decay map"
ref = np.array([[ref_los(prof, D_KPC, th, 1) for th in row] for row in sep])
rel = float(np.abs(dmap.value / ref - 1.0).max())
assert rel < 0.05, f"dOmega/decay map deviates from the direct line-of-sight integral by {rel:.1%} (tol 5%)"
print("PASS")
