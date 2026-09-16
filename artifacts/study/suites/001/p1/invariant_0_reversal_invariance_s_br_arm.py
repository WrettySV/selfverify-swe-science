"""Rotor signature must be invariant to reaction reversal (C-S/Br homolysis TS)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source"))
import automol.graph as graph

GRA = (
    {301: ("C", 0, None), 302: ("H", 0, None), 303: ("C", 0, None), 305: ("S", 0, None),
     306: ("C", 0, None), 307: ("H", 0, None), 308: ("Br", 0, None), 309: ("H", 0, None),
     310: ("H", 0, None)},
    {frozenset((301, 302)): (1, None), frozenset((301, 303)): (1, None), frozenset((303, 305)): (1, None),
     frozenset((305, 307)): (1, None), frozenset((301, 306)): (0.9, None), frozenset((306, 308)): (1, None),
     frozenset((306, 309)): (1, None), frozenset((306, 310)): (1, None)},
)
CTRL = (GRA[0], {**GRA[1], frozenset((301, 306)): (1, None), frozenset((301, 303)): (0.9, None)})

def sig(gra):
    syms = graph.atom_symbols(gra)
    seqs = [min(tuple(syms[k] for k in c), tuple(syms[k] for k in c[::-1])) for c in graph.rotational_coordinates(gra)]
    return sorted(seqs)

s_o, s_r = sig(GRA), sig(graph.ts.reverse(GRA))
assert s_o, "expected a nonempty rotor observation for this rotatable TS"
assert s_o == s_r, f"reaction reversal changed the rotor signature: {s_o} != {s_r}"
s_c = sig(CTRL)
assert s_c and s_c != s_o, f"changed-connectivity control collapsed onto reference: {s_c}"
print("PASS")
