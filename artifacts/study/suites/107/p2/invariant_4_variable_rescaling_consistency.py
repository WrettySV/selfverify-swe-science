"""Scaling / change of variables: with x = 2y, d/dy F(2y; a=2) must equal 1/(2y^2+1)
for F = integrate(1/(x^2+a), x)."""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "source"
sys.path.insert(0, str(_SRC if _SRC.is_dir() else Path.cwd() / "source"))

from sympy import Symbol, integrate

x, a = (Symbol(n, real=True) for n in "xa")
y = Symbol("y", real=True)
F = integrate(1 / (x**2 + a), x)
TOL = 1e-5


def num_deriv(expr, pt, var, step=1e-7):
    c = float(pt[var])
    p, m = dict(pt), dict(pt)
    p[var], m[var] = c + step, c - step
    return (complex(expr.subs(p).evalf(80)) - complex(expr.subs(m).evalf(80))) / (2 * step)


H = F.subs({x: 2*y, a: 2})
for yv in (0.7, 1.2):
    target = complex((1 / (2*y**2 + 1)).subs(y, yv).evalf(80))
    err = abs(num_deriv(H, {y: yv}, y) - target)
    assert err < TOL, f"rescaling consistency violated: |d/dy F(2y) - 1/(2y^2+1)| = {err:.3e} at y={yv}"

print("PASS")
