"""Rotor signature must be invariant to reaction reversal (all-C/H propane-type homolysis)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source"))
import automol.graph as graph

GRA = (
    {901: ("C", 0, None), 902: ("H", 0, None), 903: ("C", 0, None), 904: ("H", 0, None),
     905: ("C", 0, None), 906: ("H", 0, None), 907: ("H", 0, None), 908: ("H", 0, None),
     909: ("H", 0, None), 910: ("H", 0, None)},
    {frozenset((901, 902)): (1, None), frozenset((901, 903)): (1, None), frozenset((901, 905)): (0.9, None),
     frozenset((903, 904)): (1, None), frozenset((903, 906)): (1, None), frozenset((903, 907)): (1, None),
     frozenset((905, 908)): (1, None), frozenset((905, 909)): (1, None), frozenset((905, 910)): (1, None)},
)

def sig(gra):
    syms = graph.atom_symbols(gra)
    seqs = [min(tuple(syms[k] for k in c), tuple(syms[k] for k in c[::-1])) for c in graph.rotational_coordinates(gra)]
    return sorted(seqs)

s_o, s_r = sig(GRA), sig(graph.ts.reverse(GRA))
assert s_o and len(s_o) == 2, f"expected two distinct rotor axes, got {s_o}"
assert s_o == s_r, f"reaction reversal changed the rotor signature: {s_o} != {s_r}"
print("PASS")
