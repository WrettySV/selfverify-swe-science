"""Metamorphic invariant: FTC under an affine shift of the integration variable.

Integrand: (t + 2)**2 * w**3 / (w**2 + 5)**2 with w = r + 3s - 2t. The
integration variable enters both the outer factor (t + 2) and the linear
combination w, and the parameter combination / constant are new. A correct
workflow must return F with F'(t) == f(t) at generic real sample points.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from sympy import Integral, Symbol, integrate

r, s, t = (Symbol(n, real=True) for n in "rst")
f = (t + 2)**2 * (r + 3*s - 2*t)**3 / ((r + 3*s - 2*t)**2 + 5)**2
F = integrate(f, t)
if isinstance(F, Integral):
    raise AssertionError("integrate returned an unevaluated Integral")
step, tol = 1e-6, 1e-5
for rv, sv, tv in [(1, 1, 0.6), (5, -4, 2.2)]:
    sub = {r: rv, s: sv, t: tv}
    fp = complex(F.subs({**sub, t: tv + step}).evalf(60))
    fm = complex(F.subs({**sub, t: tv - step}).evalf(60))
    if abs((fp - fm) / (2*step) - complex(f.subs(sub).evalf(60))) >= tol:
        raise AssertionError(
            f"F'(t) != f(t) at r={rv}, s={sv}, t={tv}: "
            f"fd={(fp - fm) / (2*step)}, f={complex(f.subs(sub).evalf(60))}")
print("PASS")
