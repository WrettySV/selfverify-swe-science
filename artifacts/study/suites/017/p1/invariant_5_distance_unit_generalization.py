import math, sys, pathlib
import numpy as np
import astropy.units as u
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "source"))
from gammapy.astro.darkmatter import JFactory, profiles
from gammapy.maps import WcsGeom
def los(s, d):
    c = math.cos(s)
    l = np.linspace(0.0, d.value * (c + math.sqrt(c * c + 15.0)), 100_000) * d.unit
    return np.trapezoid(profiles.NFWProfile(r_s=20 * u.kpc)(np.sqrt(l**2 + d**2 - 2.0 * d * l * c)) ** 2, l) / u.sr
GEOM = WcsGeom.create(skydir=(0, 0), width=(48, 48), binsz=8, frame="galactic")
SEP = GEOM.separation(GEOM.center_skydir).rad.ravel()
def run(d):
    try:
        return JFactory(geom=GEOM, profile=profiles.NFWProfile(r_s=20 * u.kpc), distance=d, annihilation=True).compute_differential_jfactor(ndecade=2000).ravel()
    except Exception as exc:
        raise AssertionError(f"J-factor for distance {d} raised {type(exc).__name__}: {exc}") from None
def check(got, d, label):
    ref = np.array([los(s, d).to_value("GeV2 cm-5 sr-1") for s in SEP])
    err = np.abs(got.to_value("GeV2 cm-5 sr-1") - ref) / ref
    if not np.isfinite(err).all() or err.max() > 3e-2:
        raise AssertionError(f"{label}: J-factor off by up to {np.nanmax(err):.1%} vs direct LoS integral")
A = run(8.33 * u.kpc)
check(A, 8.33 * u.kpc, "halo at 8.33 kpc")
B = run(8330 * u.pc)
REL = ((B - A) / A).value
if not np.isfinite(REL).all() or np.abs(REL).max() > 1e-9:
    raise AssertionError(f"expressing the same distance in pc instead of kpc changed the result by {np.nanmax(np.abs(REL)):.2e}")
check(run(21 * u.kpc), 21 * u.kpc, "halo at 21 kpc")
print("PASS")
