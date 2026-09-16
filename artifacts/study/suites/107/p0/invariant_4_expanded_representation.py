"""Metamorphic invariant: representation equivalence. Same rational function
t**2*w**3/(w**2+7)**2 (w = 3r-2s-5t) integrated in factored vs fully expanded
form must yield antiderivatives agreeing up to a constant, with F' = f."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from sympy import Integral, Symbol, integrate

r, s, t = (Symbol(n, real=True) for n in "rst")
w = 3*r - 2*s - 5*t
f = t**2 * w**3 / (w**2 + 7)**2
num, den = f.as_numer_denom()
f_exp = num.expand() / den.expand()
F_fact = integrate(f, t)
F_exp = integrate(f_exp, t)
for F in (F_fact, F_exp):
    if isinstance(F, Integral):
        raise AssertionError("integrate returned an unevaluated Integral")
step, tol = 1e-6, 1e-5
for rv, sv, tv in [(1, 3, 0.5), (-2, 5, 1.5)]:
    sub = {r: rv, s: sv, t: tv}
    fp = {**sub, t: tv + step}
    fm = {**sub, t: tv - step}
    inc_f = complex(F_fact.subs(fp).evalf(60)) - complex(F_fact.subs(fm).evalf(60))
    inc_e = complex(F_exp.subs(fp).evalf(60)) - complex(F_exp.subs(fm).evalf(60))
    if abs(inc_f - inc_e) >= tol * 2 * step:
        raise AssertionError(f"representation dependence at r={rv}, s={sv}, t={tv}")
    if abs(inc_e / (2*step) - complex(f_exp.subs(sub).evalf(60))) >= tol:
        raise AssertionError(f"F' != f (expanded form) at r={rv}, s={sv}, t={tv}")
print("PASS")
