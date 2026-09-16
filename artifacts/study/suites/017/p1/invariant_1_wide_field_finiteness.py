import sys
from pathlib import Path
import numpy as np
import astropy.units as u
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from gammapy.astro.darkmatter import JFactory, profiles
from gammapy.maps import WcsGeom
D = 8.33 * u.kpc
GEOM = WcsGeom.create(skydir=(0, 0), width=(96, 72), binsz=8, frame="galactic")
MAX_SEP = GEOM.separation(GEOM.center_skydir).deg.max()
assert MAX_SEP > 45, f"test setup must include pixels beyond 45 deg, got {MAX_SEP:.1f}"
for ann in (True, False):
    fac = JFactory(geom=GEOM, profile=profiles.NFWProfile(), distance=D, annihilation=ann)
    try:
        res = fac.compute_differential_jfactor(ndecade=2000)
    except Exception as exc:
        raise AssertionError(f"J-factor (annihilation={ann}) raised {type(exc).__name__}: {exc}") from None
    if res.shape != GEOM.data_shape:
        raise AssertionError(f"unexpected result shape {res.shape}, expected {GEOM.data_shape}")
    if not np.isfinite(res.value).all():
        sep = GEOM.separation(GEOM.center_skydir).deg[~np.isfinite(res.value)]
        raise AssertionError(f"non-finite J-factor for separations up to {sep.max():.1f} deg (annihilation={ann})")
    if not (res.value > 0).all():
        raise AssertionError("J-factor must be strictly positive at every pixel")
print("PASS")
