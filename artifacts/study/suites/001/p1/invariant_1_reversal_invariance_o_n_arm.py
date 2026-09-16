"""Rotor signature must be invariant to reaction reversal (C-O-H arm / CH2-NH2 cap TS)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source"))
import automol.graph as graph

GRA = (
    {801: ("C", 0, None), 802: ("H", 0, None), 803: ("C", 0, None), 805: ("O", 0, None),
     806: ("C", 0, None), 807: ("H", 0, None), 808: ("N", 0, None), 809: ("H", 0, None),
     810: ("H", 0, None), 811: ("H", 0, None), 812: ("H", 0, None)},
    {frozenset((802, 801)): (1, None), frozenset((803, 801)): (1, None), frozenset((803, 805)): (1, None),
     frozenset((805, 807)): (1, None), frozenset((801, 806)): (0.9, None), frozenset((806, 808)): (1, None),
     frozenset((806, 809)): (1, None), frozenset((806, 810)): (1, None), frozenset((808, 811)): (1, None),
     frozenset((808, 812)): (1, None)},
)

def sig(gra):
    syms = graph.atom_symbols(gra)
    seqs = [min(tuple(syms[k] for k in c), tuple(syms[k] for k in c[::-1])) for c in graph.rotational_coordinates(gra)]
    return sorted(seqs)

s_o, s_r = sig(GRA), sig(graph.ts.reverse(GRA))
assert s_o and len(s_o) == 2, f"expected two distinct rotor axes, got {s_o}"
assert s_o == s_r, f"reaction reversal changed the rotor signature: {s_o} != {s_r}"
print("PASS")
