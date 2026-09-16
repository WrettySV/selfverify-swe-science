"""FTC: d/dx integrate(f, x) == f for a new parameterized integrand x^2/((x+a)^2+b)."""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "source"
sys.path.insert(0, str(_SRC if _SRC.is_dir() else Path.cwd() / "source"))

from sympy import Symbol, integrate

x, a, b = (Symbol(n, real=True) for n in "xab")
f = x**2 / ((x + a)**2 + b)
F = integrate(f, x)
TOL = 1e-5


def num_deriv(expr, pt, var, step=1e-7):
    c = float(pt[var])
    p, m = dict(pt), dict(pt)
    p[var], m[var] = c + step, c - step
    return (complex(expr.subs(p).evalf(80)) - complex(expr.subs(m).evalf(80))) / (2 * step)


for pt in ({a: 1.7, b: 2.3, x: 0.8}, {a: -0.5, b: 4.1, x: 1.9}):
    err = abs(num_deriv(F, pt, x) - complex(f.subs(pt).evalf(80)))
    assert err < TOL, f"FTC violated: |dF/dx - f| = {err:.3e} at {pt}; antiderivative is wrong"

print("PASS")
