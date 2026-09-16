"""Boundary/degenerate limit: as a -> -1 the quadratic x^2+a splits into real linear
factors; the general antiderivative must still satisfy d/dx F(x; a=-1) = 1/(x^2-1)."""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "source"
sys.path.insert(0, str(_SRC if _SRC.is_dir() else Path.cwd() / "source"))

from sympy import Symbol, integrate

x, a = (Symbol(n, real=True) for n in "xa")
F = integrate(1 / (x**2 + a), x)
TOL = 1e-5


def num_deriv(expr, pt, var, step=1e-7):
    c = float(pt[var])
    p, m = dict(pt), dict(pt)
    p[var], m[var] = c + step, c - step
    return (complex(expr.subs(p).evalf(80)) - complex(expr.subs(m).evalf(80))) / (2 * step)


F_degen = F.subs(a, -1)
for xv in (2.0, 3.5):
    target = complex((1 / (x**2 - 1)).subs(x, xv).evalf(80))
    err = abs(num_deriv(F_degen, {x: xv}, x) - target)
    assert err < TOL, f"degenerate limit violated: |dF/dx - 1/(x^2-1)| = {err:.3e} at x={xv}"

print("PASS")
