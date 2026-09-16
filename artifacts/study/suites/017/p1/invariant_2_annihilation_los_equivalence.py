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
def los(s):
    c = math.cos(s)
    l = np.linspace(0.0, D.value * (c + math.sqrt(c * c + 15.0)), 100_000) * D.unit
    return np.trapezoid(P(np.sqrt(l**2 + D**2 - 2.0 * D * l * c)) ** 2, l) / u.sr
GEOM = WcsGeom.create(skydir=(0, 0), width=(96, 72), binsz=12, frame="galactic")
SEP = GEOM.separation(GEOM.center_skydir).rad.ravel()
assert np.degrees(SEP.max()) > 45, "test setup must include wide angles"
try:
    GOT = JFactory(geom=GEOM, profile=profiles.NFWProfile(), distance=D, annihilation=True).compute_differential_jfactor(ndecade=2000).ravel()
except Exception as exc:
    raise AssertionError(f"J-factor computation raised {type(exc).__name__}: {exc}") from None
if not np.isfinite(GOT.value).all():
    raise AssertionError("non-finite J-factor values in a wide field")
REF = np.array([los(s).to_value("GeV2 cm-5 sr-1") for s in SEP])
ERR = np.abs(GOT.to_value("GeV2 cm-5 sr-1") - REF) / REF
if ERR.max() > 5e-2:
    raise AssertionError(f"annihilation J-factor deviates up to {ERR.max():.1%} from the direct line-of-sight integral")
print("PASS")
