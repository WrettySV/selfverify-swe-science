"""FTOC invariant: dF/dt == f for a new parameterized rational input."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))

from sympy import Integral, Symbol, integrate

t = Symbol("t", real=True)
a, b = Symbol("a", real=True), Symbol("b", real=True)
f = 1 / ((t**2 + a) * (t - b))
F = integrate(f, t)
assert not F.has(Integral), f"expected an evaluated antiderivative, got {F}"
step, tol = 1e-6, 1e-5
for values in (({"a": 4.25, "b": -0.75, "t": 1.1}, {"a": 0.9, "b": 2.1, "t": -0.4})):
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
