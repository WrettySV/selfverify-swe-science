import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "source"))
import numpy as np, astropy.units as u
from gammapy.astro.darkmatter import JFactory, profiles
from gammapy.maps import WcsGeom
def rho(r):  # Burkert profile (finite at r=0), r in kpc, rho in GeV/cm3
    return 0.9 / ((1 + r / 11.7) * (1 + (r / 11.7) ** 2))
def branch(rlo, rhi, b, g, n=20001):  # int rho^g r/sqrt(r^2-b^2) dr, via r=b*cosh(t)
    if b <= 0:
        r = np.linspace(rlo, rhi, n)
        return np.trapezoid(rho(r) ** g, r)
    t = np.linspace(max(np.arccosh(rlo / b), 0.0), np.arccosh(rhi / b), n)
    return np.trapezoid(rho(b * np.cosh(t)) ** g * b * np.cosh(t), t)
def j_ref(th, D, g):  # model: 2*[b,D]+[D,4D] for th<=90 deg, else [D,4D] (cm units)
    b = D * np.sin(np.deg2rad(th))
    return (branch(D, 4 * D, b, g) + (2 * branch(b, D, b, g) if th <= 90 else 0.0)) * 3.085677581e21
D = 6.8 * u.kpc; geom = WcsGeom.create(skydir=(0, 0), width=(75, 75), binsz=25, frame="galactic")
prof = profiles.BurkertProfile(r_s=11.7 * u.kpc, rho_s=0.9 * u.GeV / u.cm**3); prof.DISTANCE_GC = D
try:
    j = JFactory(geom=geom, profile=prof, distance=D, annihilation=True).compute_differential_jfactor(ndecade=300)
except Exception as exc:
    raise AssertionError(f"wide-field JFactory map raised: {type(exc).__name__}: {exc}")
assert np.isfinite(j.value).all(), f"non-finite values in wide field (incl. theta=0 pixel): {j.value}"
sep = np.degrees(geom.separation(geom.center_skydir).rad)
for i, k in ((1, 1), (0, 1), (0, 0)):
    th, val = float(sep[i, k]), float(j.value[i, k])
    ref = j_ref(th, 6.8, 2)
    assert abs(val - ref) / ref < 0.03, f"burkert ann th={th:.2f} deg: {val:.4e} vs direct-LoS reference {ref:.4e}"
print("PASS")
