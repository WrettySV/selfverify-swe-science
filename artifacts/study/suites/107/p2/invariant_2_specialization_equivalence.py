"""Representation equivalence: F_general(a=2) and the directly specialized antiderivative
must agree up to an additive constant, i.e. the derivative of their difference vanishes."""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "source"
sys.path.insert(0, str(_SRC if _SRC.is_dir() else Path.cwd() / "source"))

from sympy import Symbol, integrate

x, a = (Symbol(n, real=True) for n in "xa")
F_general = integrate(1 / (x**2 + a), x)
F_special = integrate(1 / (x**2 + 2), x)
TOL = 1e-5


def num_deriv(expr, pt, var, step=1e-7):
    c = float(pt[var])
    p, m = dict(pt), dict(pt)
    p[var], m[var] = c + step, c - step
    return (complex(expr.subs(p).evalf(80)) - complex(expr.subs(m).evalf(80))) / (2 * step)


diff_expr = F_general.subs(a, 2) - F_special
for xv in (0.7, 1.6):
    err = abs(num_deriv(diff_expr, {x: xv}, x))
    assert err < TOL, f"specialization equivalence violated: |d/dx(F(a=2)-F_direct)| = {err:.3e} at x={xv}"

print("PASS")
