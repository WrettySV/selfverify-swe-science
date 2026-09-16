import sys
from pathlib import Path
import numpy as np
import astropy.units as u
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from gammapy.astro.darkmatter import JFactory, profiles
from gammapy.maps import WcsGeom

geom = WcsGeom.create(skydir=(0, 0), width=(40, 40), binsz=10, frame="galactic")

def compute(distance, ndecade=500):
    factory = JFactory(geom=geom, profile=profiles.NFWProfile(), distance=distance, annihilation=True)
    with np.errstate(all="ignore"):
        try:
            return factory.compute_differential_jfactor(ndecade=ndecade)
        except Exception as exc:
            raise AssertionError(f"computation raised for distance={distance!r}: {type(exc).__name__}: {exc}")

j_kpc = compute(10.0 * u.kpc)
j_pc = compute(10000.0 * u.pc)
assert j_kpc.unit.is_equivalent(j_pc.unit), "returned units differ between kpc and pc distance inputs"
assert np.isfinite(j_kpc.value).all() and np.isfinite(j_pc.value).all(), "non-finite dJ/dOmega values"
a = j_kpc.to_value("GeV2 cm-5 sr-1")
b = j_pc.to_value("GeV2 cm-5 sr-1")
rel = float(np.abs(a / b - 1.0).max())
assert rel < 1e-9, f"physical result depends on the unit used for the distance (kpc vs pc): max rel diff {rel:.3e}"
print("PASS")
