"""Conservation of integral value: symbolic F(hi)-F(lo) must match direct numerical quadrature."""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "source"
sys.path.insert(0, str(_SRC if _SRC.is_dir() else Path.cwd() / "source"))

import mpmath
from sympy import Symbol, integrate

u, r, s = (Symbol(n, real=True) for n in "urs")
f = u**2 * (r + s - 3*u)**3 / ((r + s - 3*u)**2 + 2)**2
F = integrate(f, u)
TOL, lo, hi, rv, sv = 1e-8, 0.4, 1.6, 3, 5
mpmath.mp.dps = 50


def f_num(t):
    return (t**2 * (rv + sv - 3*t)**3) / ((rv + sv - 3*t)**2 + 2)**2


quad = mpmath.quad(f_num, [mpmath.mpf(lo), mpmath.mpf(hi)])
sym = complex(F.subs({u: hi, r: rv, s: sv}).evalf(80)) - complex(F.subs({u: lo, r: rv, s: sv}).evalf(80))
err = abs(sym - complex(quad))
assert err < TOL, (
    f"integral-value conservation violated: symbolic F({hi})-F({lo}) = {sym} vs "
    f"numerical quadrature {quad}, discrepancy {err:.3e} > {TOL}"
)

print("PASS")
