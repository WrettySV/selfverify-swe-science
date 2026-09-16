"""Rotor signature must be invariant to reaction reversal (3-atom linear segment TS)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source"))
import automol.graph as graph

GRA = (
    {1001: ("C", 0, None), 1002: ("C", 0, None), 1003: ("C", 0, None), 1004: ("H", 0, None),
     1005: ("Cl", 0, None), 1006: ("H", 0, None), 1007: ("H", 0, None), 1008: ("C", 0, None),
     1009: ("H", 0, None), 1010: ("S", 0, None), 1011: ("H", 0, None)},
    {frozenset((1001, 1002)): (0.9, None), frozenset((1001, 1003)): (1, None), frozenset((1001, 1004)): (1, None),
     frozenset((1002, 1005)): (1, None), frozenset((1002, 1006)): (1, None), frozenset((1002, 1007)): (1, None),
     frozenset((1003, 1008)): (1, None), frozenset((1008, 1009)): (1, None), frozenset((1008, 1010)): (1, None),
     frozenset((1010, 1011)): (1, None)},
)

def sig(gra):
    syms = graph.atom_symbols(gra)
    seqs = [min(tuple(syms[k] for k in c), tuple(syms[k] for k in c[::-1])) for c in graph.rotational_coordinates(gra)]
    return sorted(seqs)

s_o, s_r = sig(GRA), sig(graph.ts.reverse(GRA))
assert s_o, "expected a nonempty rotor observation for this rotatable TS"
assert len(s_o) == len(s_r) == 1, f"axis count changed under reversal: {s_o} vs {s_r}"
assert s_o == s_r, f"reaction reversal changed the rotor signature: {s_o} != {s_r}"
print("PASS")
