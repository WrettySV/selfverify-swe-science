"""FTOC invariant: dF/dt == f for a new parameterized rational input."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))

from sympy import Integral, Symbol, integrate

t = Symbol("t", real=True)
u, v = Symbol("u", real=True), Symbol("v", real=True)
f = t**3 * (u + 2*v + 4*t)**2 / ((u + 2*v + 4*t)**2 + 6)**2
F = integrate(f, t)
assert not F.has(Integral), f"expected an evaluated antiderivative, got {F}"
step, tol = 1e-6, 1e-5
for values in (({"u": 1.5, "v": 2.25, "t": 0.3}, {"u": -2.0, "v": 0.5, "t": 2.5})):
    pt = {s: values[s.name] for s in f.free_symbols}
    pt_plus, pt_minus = dict(pt), dict(pt)
    pt_plus[t], pt_minus[t] = pt[t] + step, pt[t] - step
    forward = complex(F.subs(pt_plus).evalf(80))
    backward = complex(F.subs(pt_minus).evalf(80))
    finite_difference = (forward - backward) / (2 * step)
    target = complex(f.subs(pt).evalf(80))
    assert abs(finite_difference - target) < tol, (
        f"FTOC violated at {values}: dF/dt={finite_difference}, f={target}"
    )
print("PASS")
