import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "source"))
import numpy as np, astropy.units as u
from gammapy.astro.darkmatter import JFactory, profiles
from gammapy.maps import WcsGeom
def jmap(dist):
    geom = WcsGeom.create(skydir=(0, 0), width=(40, 40), binsz=10, frame="galactic")
    prof = profiles.NFWProfile(r_s=13.6 * u.kpc, rho_s=0.55 * u.GeV / u.cm**3)
    prof.DISTANCE_GC = dist
    return JFactory(geom=geom, profile=prof, distance=dist, annihilation=True).compute_differential_jfactor(ndecade=300)
try:
    jk = jmap(7.9 * u.kpc)
except Exception as exc:
    raise AssertionError(f"map with distance in kpc raised: {type(exc).__name__}: {exc}")
try:
    jp = jmap((7.9 * u.kpc).to(u.pc))
except Exception as exc:
    raise AssertionError(f"map with distance in pc raised (unit handling broken): {type(exc).__name__}: {exc}")
assert np.isfinite(jk.value).all() and np.isfinite(jp.value).all(), "non-finite J-factor values"
dev = float(np.max(np.abs(jp.value / jk.value - 1.0)))
assert dev < 1e-3, f"same physical setup in kpc vs pc differs: max relative deviation {dev:.3e}"
print("PASS")
