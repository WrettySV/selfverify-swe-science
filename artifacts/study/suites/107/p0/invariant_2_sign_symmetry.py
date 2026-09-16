"""Metamorphic invariant: sign symmetry + FTC. f- = t**2*(-w)**3/((-w)**2+9)**2
equals -f+ = -t**2*w**3/(w**2+9)**2 (w = r+4s-9t). A correct workflow must
return F+, F- with F+' = f+, F-' = f- (hence F-'+F+' = 0) at sample points."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from sympy import Integral, Symbol, integrate

r, s, t = (Symbol(n, real=True) for n in "rst")
w = r + 4*s - 9*t
f_pos = t**2 * w**3 / (w**2 + 9)**2
f_neg = t**2 * (-w)**3 / ((-w)**2 + 9)**2
F_pos, F_neg = integrate(f_pos, t), integrate(f_neg, t)
for F in (F_pos, F_neg):
    if isinstance(F, Integral):
        raise AssertionError("integrate returned an unevaluated Integral")
step, tol = 1e-6, 1e-5
for rv, sv, tv in [(4, 1, 0.8), (-3, 2, 1.1), (2, -5, 0.4)]:
    sub = {r: rv, s: sv, t: tv}
    fp = {**sub, t: tv + step}
    fm = {**sub, t: tv - step}
    fd_p = (complex(F_pos.subs(fp).evalf(60)) - complex(F_pos.subs(fm).evalf(60))) / (2*step)
    fd_n = (complex(F_neg.subs(fp).evalf(60)) - complex(F_neg.subs(fm).evalf(60))) / (2*step)
    if abs(fd_p - complex(f_pos.subs(sub).evalf(60))) >= tol:
        raise AssertionError(f"F_pos' != f_pos at r={rv}, s={sv}, t={tv}")
    if abs(fd_n - complex(f_neg.subs(sub).evalf(60))) >= tol:
        raise AssertionError(f"F_neg' != f_neg at r={rv}, s={sv}, t={tv}")
    if abs(fd_p + fd_n) >= tol:
        raise AssertionError(f"sign symmetry broken at r={rv}, s={sv}, t={tv}")
print("PASS")
