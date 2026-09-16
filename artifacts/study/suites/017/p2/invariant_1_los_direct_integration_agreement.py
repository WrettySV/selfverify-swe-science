import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "source"))
import numpy as np, astropy.units as u
from gammapy.astro.darkmatter import JFactory, profiles
from gammapy.maps import WcsGeom
def rho(r):  # NFW profile, r in kpc, rho in GeV/cm3
    return 0.42 / ((r / 17.3) * (1 + r / 17.3) ** 2)
def branch(rlo, rhi, b, g, n=20001):  # int rho^g r/sqrt(r^2-b^2) dr, via r=b*cosh(t)
    if b <= 0:
        r = np.linspace(rlo, rhi, n)
        return np.trapezoid(rho(r) ** g, r)
    t = np.linspace(max(np.arccosh(rlo / b), 0.0), np.arccosh(rhi / b), n)
    return np.trapezoid(rho(b * np.cosh(t)) ** g * b * np.cosh(t), t)
def j_ref(th, D, g):  # model: 2*[b,D]+[D,4D] for th<=90 deg, else [D,4D] (cm units)
    b = D * np.sin(np.deg2rad(th))
    return (branch(D, 4 * D, b, g) + (2 * branch(b, D, b, g) if th <= 90 else 0.0)) * 3.085677581e21
D = 7.9 * u.kpc; geom = WcsGeom.create(skydir=(0, 0), width=(60, 60), binsz=10, frame="galactic")
prof = profiles.NFWProfile(r_s=17.3 * u.kpc, rho_s=0.42 * u.GeV / u.cm**3); prof.DISTANCE_GC = D
try:
    jann = JFactory(geom=geom, profile=prof, distance=D, annihilation=True).compute_differential_jfactor(ndecade=300)
    jdec = JFactory(geom=geom, profile=prof, distance=D, annihilation=False).compute_differential_jfactor(ndecade=300)
except Exception as exc:
    raise AssertionError(f"JFactory map computation raised: {type(exc).__name__}: {exc}")
sep = np.degrees(geom.separation(geom.center_skydir).rad)
for mode, jmap_, gexp in (("annihilation", jann, 2), ("decay", jdec, 1)):
    for i, k in ((1, 1), (0, 2), (5, 5)):
        th, val = float(sep[i, k]), float(jmap_.value[i, k])
        ref = j_ref(th, 7.9, gexp)
        assert np.isfinite(val) and abs(val - ref) / ref < 0.03, f"{mode} th={th:.2f} deg: {val:.4e} vs direct-LoS reference {ref:.4e}"
print("PASS")
