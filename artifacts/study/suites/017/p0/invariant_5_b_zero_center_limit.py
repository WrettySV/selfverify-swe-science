import sys
from pathlib import Path
import numpy as np
import astropy.units as u
from scipy import integrate
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from gammapy.astro.darkmatter import JFactory, profiles
from gammapy.maps import WcsGeom
D_KPC = 9.0
prof = profiles.BurkertProfile()
geom = WcsGeom.create(skydir=(0, 0), width=(30, 30), binsz=10, frame="galactic")
sep = geom.separation(geom.center_skydir).to_value(u.deg)
assert sep[1, 1] == 0.0, "expected a pixel exactly on the halo center"
factory = JFactory(geom=geom, profile=prof, distance=D_KPC * u.kpc, annihilation=True)
with np.errstate(all="ignore"):
    try:
        jmap = factory.compute_differential_jfactor(ndecade=1000)
    except Exception as exc:
        raise AssertionError(f"central (b=0) sightline crashed: {type(exc).__name__}: {exc}")
center = jmap.value[1, 1]
assert np.isfinite(center), "central (b=0) pixel is not finite"
rho2 = lambda r: (prof(r * u.kpc) ** 2).to_value("GeV2 cm-6")
grid = np.geomspace(1e-6, 4 * D_KPC, 400001)
inner = grid[grid <= D_KPC]
outer = grid[grid >= D_KPC]
ref = (2 * integrate.trapezoid(rho2(inner), inner) + integrate.trapezoid(rho2(outer), outer)) * u.kpc.to(u.cm)
rel = abs(center / ref - 1.0)
assert rel < 0.03, (f"central pixel {center:.4e} deviates from 2*int[0,D] rho^2 dr + int[D,4D] rho^2 dr "
                    f"({ref:.4e}) by {rel:.1%}: the b=0 limit must integrate the original radial bounds")
print("PASS")
