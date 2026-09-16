"""The same TS written with a forming (0.1) edge must give the same rotor as with a breaking (0.9) edge."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from automol import graph

def build(atoms, bonds):
    return ({k: (s, 0, None) for k, s in atoms},
            {frozenset({a, b}): (o, None) for a, b, o in bonds})

def sig(gra):
    syms = graph.atom_symbols(gra)
    return sorted(min(tuple(syms[k] for k in c), tuple(syms[k] for k in c)[::-1])
                  for c in graph.rotational_coordinates(gra))

BRK = build([(101, "C"), (103, "H"), (107, "C"), (113, "S"), (119, "H"), (127, "C"),
             (131, "H"), (137, "H"), (143, "H")],
            [(101, 103, 1), (101, 107, 1), (101, 127, 0.9), (107, 113, 1), (113, 119, 1),
             (127, 131, 1), (127, 137, 1), (127, 143, 1)])
FRM = build([(211, "C"), (213, "H"), (217, "C"), (223, "S"), (229, "H"), (233, "C"),
             (239, "H"), (241, "H"), (247, "H")],
            [(211, 213, 1), (211, 217, 1), (211, 233, 0.1), (217, 223, 1), (223, 229, 1),
             (233, 239, 1), (233, 241, 1), (233, 247, 1)])
s_brk, s_frm = sig(BRK), sig(FRM)
assert s_brk and s_frm, "no observable rotor in one of the two presentations"
assert s_frm == s_brk, f"same TS written in opposite directions gave different rotors: {s_brk} vs {s_frm}"
assert sig(graph.ts.reverse(BRK)) == s_brk, "breaking-edge presentation not self-consistent under reversal"
assert sig(graph.ts.reverse(FRM)) == s_frm, "forming-edge presentation not self-consistent under reversal"
print("PASS")
