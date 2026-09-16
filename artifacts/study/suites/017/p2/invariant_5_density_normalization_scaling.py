import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "source"))
import numpy as np, astropy.units as u
from gammapy.astro.darkmatter import JFactory, profiles
from gammapy.maps import WcsGeom
D = 7.9 * u.kpc; q = 3.2
def jmaps(rho0, ann):
    geom = WcsGeom.create(skydir=(0, 0), width=(90, 90), binsz=15, frame="galactic")
    prof = profiles.NFWProfile(r_s=17.3 * u.kpc, rho_s=rho0); prof.DISTANCE_GC = D
    return JFactory(geom=geom, profile=prof, distance=D, annihilation=ann).compute_differential_jfactor(ndecade=300)
try:
    a1 = jmaps(0.42 * u.GeV / u.cm**3, True); a2 = jmaps(0.42 * q * u.GeV / u.cm**3, True)
    d1 = jmaps(0.42 * u.GeV / u.cm**3, False); d2 = jmaps(0.42 * q * u.GeV / u.cm**3, False)
except Exception as exc:
    raise AssertionError(f"scaling maps raised (wide-field pixels beyond 45 deg): {type(exc).__name__}: {exc}")
for tag, jm in (("ann q=1", a1), ("ann q=3.2", a2), ("dec q=1", d1), ("dec q=3.2", d2)):
    assert np.isfinite(jm.value).all(), f"non-finite values in {tag} map"
ra, rd = a2.value / a1.value, d2.value / d1.value
assert np.allclose(ra, q ** 2, rtol=1e-6), f"annihilation must scale as rho^2: max dev {float(np.max(np.abs(ra - q ** 2))):.3e}"
assert np.allclose(rd, q, rtol=1e-6), f"decay must scale as rho: max dev {float(np.max(np.abs(rd - q))):.3e}"
print("PASS")
