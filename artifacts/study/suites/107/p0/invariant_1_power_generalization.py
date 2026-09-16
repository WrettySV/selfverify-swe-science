"""Metamorphic invariant: antiderivative consistency (FTC) under changed powers.

Integrand: t**3 * w**4 / (w**2 + 11)**2 with w = 2r + s - 7t. The numerator
power, the w-exponent and the quadratic constant all differ from any supplied
workbench case. A correct workflow must return F with F'(t) == f(t) at
generic real sample points.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from sympy import Integral, Symbol, integrate

r, s, t = (Symbol(n, real=True) for n in "rst")
f = t**3 * (2*r + s - 7*t)**4 / ((2*r + s - 7*t)**2 + 11)**2
F = integrate(f, t)
if isinstance(F, Integral):
    raise AssertionError("integrate returned an unevaluated Integral")
step, tol = 1e-6, 1e-5
for rv, sv, tv in [(2, 1, 0.4), (-1, 3, 1.2)]:
    sub = {r: rv, s: sv, t: tv}
    fp = complex(F.subs({**sub, t: tv + step}).evalf(60))
    fm = complex(F.subs({**sub, t: tv - step}).evalf(60))
    if abs((fp - fm) / (2*step) - complex(f.subs(sub).evalf(60))) >= tol:
        raise AssertionError(
            f"F'(t) != f(t) at r={rv}, s={sv}, t={tv}: "
            f"fd={(fp - fm) / (2*step)}, f={complex(f.subs(sub).evalf(60))}")
print("PASS")
