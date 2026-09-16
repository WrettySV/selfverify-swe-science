import math
import sys
from pathlib import Path
import numpy as np
import astropy.units as u
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from gammapy.astro.darkmatter import JFactory, profiles
from gammapy.maps import WcsGeom
D = 8.33 * u.kpc
P = profiles.NFWProfile()
def los(s, sq):
    c = math.cos(s)
    l = np.linspace(0.0, D.value * (c + math.sqrt(c * c + 15.0)), 50_000) * D.unit
    f = P(np.sqrt(l**2 + D**2 - 2.0 * D * l * c))
    return np.trapezoid(f**2 if sq else f, l) / u.sr
GEOM = WcsGeom.create(skydir=(0, 0), width=(36, 36), binsz=4.5, frame="galactic")
SEP = GEOM.separation(GEOM.center_skydir).rad.ravel()
assert 0 < SEP.min() and np.degrees(SEP.max()) < 45, "test setup: small field, no on-axis pixel"
for ann, unit in ((True, "GeV2 cm-5 sr-1"), (False, "GeV cm-2 sr-1")):
    try:
        GOT = JFactory(geom=GEOM, profile=profiles.NFWProfile(), distance=D, annihilation=ann).compute_differential_jfactor(ndecade=2000).ravel()
    except Exception as exc:
        raise AssertionError(f"J-factor (annihilation={ann}) raised {type(exc).__name__}: {exc}") from None
    REF = np.array([los(s, ann).to_value(unit) for s in SEP])
    ERR = np.abs(GOT.to_value(unit) - REF) / REF
    if not np.isfinite(ERR).all() or ERR.max() > 3e-2:
        raise AssertionError(f"small-field J-factor (annihilation={ann}) off by up to {np.nanmax(ERR):.1%} vs direct LoS integral")
print("PASS")
