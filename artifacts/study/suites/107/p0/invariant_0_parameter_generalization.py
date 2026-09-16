"""Metamorphic invariant: antiderivative consistency (FTC) for a NEW rational family.

Integrand: t**2 * w**3 / (w**2 + 7)**2 with w = 3r - 2s - 5t (new linear
combination and new constant, not the public workbench case). For a correct
symbolic integration workflow, F = integrate(f, t) must satisfy F'(t) == f(t)
at generic real sample points away from singularities (none here: w**2 + 7 > 0).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from sympy import Integral, Symbol, integrate

r, s, t = (Symbol(n, real=True) for n in "rst")
f = t**2 * (3*r - 2*s - 5*t)**3 / ((3*r - 2*s - 5*t)**2 + 7)**2
F = integrate(f, t)
if isinstance(F, Integral):
    raise AssertionError("integrate returned an unevaluated Integral")
step, tol = 1e-6, 1e-5
for rv, sv, tv in [(1, 3, 0.5), (-2, 5, 1.5), (7, -1, 0.7)]:
    sub = {r: rv, s: sv, t: tv}
    fp = complex(F.subs({**sub, t: tv + step}).evalf(60))
    fm = complex(F.subs({**sub, t: tv - step}).evalf(60))
    if abs((fp - fm) / (2*step) - complex(f.subs(sub).evalf(60))) >= tol:
        raise AssertionError(
            f"F'(t) != f(t) at r={rv}, s={sv}, t={tv}: "
            f"fd={(fp - fm) / (2*step)}, f={complex(f.subs(sub).evalf(60))}")
print("PASS")
