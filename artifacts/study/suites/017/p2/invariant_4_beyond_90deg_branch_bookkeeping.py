import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "source"))
import numpy as np, astropy.units as u
from gammapy.astro.darkmatter import JFactory, profiles
from gammapy.maps import WcsGeom
def rho(r):  # NFW profile, r in kpc, rho in GeV/cm3
    return 0.42 / ((r / 17.3) * (1 + r / 17.3) ** 2)
def branch(rlo, rhi, b, g, n=20001):  # int rho^g r/sqrt(r^2-b^2) dr, via r=b*cosh(t)
    t = np.linspace(max(np.arccosh(rlo / b), 0.0), np.arccosh(rhi / b), n)
    return np.trapezoid(rho(b * np.cosh(t)) ** g * b * np.cosh(t), t)
D = 7.9 * u.kpc; geom = WcsGeom.create(skydir=(0, 0), width=(360, 30), binsz=15, frame="galactic")
prof = profiles.NFWProfile(r_s=17.3 * u.kpc, rho_s=0.42 * u.GeV / u.cm**3); prof.DISTANCE_GC = D
try:
    j = JFactory(geom=geom, profile=prof, distance=D, annihilation=True).compute_differential_jfactor(ndecade=300)
except Exception as exc:
    raise AssertionError(f"map covering theta>90 deg raised: {type(exc).__name__}: {exc}")
assert np.isfinite(j.value).all(), f"non-finite values at large separations: min={float(j.value.min()):.3e}"
sep = np.degrees(geom.separation(geom.center_skydir).rad)
for i, k in ((0, 5), (0, 6)):  # one pixel beyond, one below the 90 deg boundary
    th, val = float(sep[i, k]), float(j.value[i, k])
    b = 7.9 * np.sin(np.deg2rad(th))
    ref = (branch(7.9, 4 * 7.9, b, 2) + (2 * branch(b, 7.9, b, 2) if th <= 90 else 0.0)) * 3.085677581e21
    assert abs(val - ref) / ref < 0.03, f"th={th:.2f} deg: {val:.4e} vs branch reference {ref:.4e}"
assert j.value[0, 5] < j.value[0, 6], "J must drop when the doubled near branch is removed beyond 90 deg"
print("PASS")
