"""The extended linear rotor segment (its in-line cap atoms) must not depend on reaction direction."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from automol import graph

ATOMS = [(101, "C"), (103, "H"), (107, "C"), (113, "S"), (119, "H"),
         (127, "C"), (131, "H"), (137, "H"), (143, "H")]
BONDS = [(101, 103, 1), (101, 107, 1), (101, 127, 0.9), (107, 113, 1),
         (113, 119, 1), (127, 131, 1), (127, 137, 1), (127, 143, 1)]

def build(atoms, bonds):
    return ({k: (s, 0, None) for k, s in atoms},
            {frozenset({a, b}): (o, None) for a, b, o in bonds})

def segs(gra):
    return frozenset(frozenset(s) for s in graph.linear_segments_atom_keys(gra, extend=True))

G = build(ATOMS, BONDS)
a, b = segs(G), segs(graph.ts.reverse(G))
assert a, "expected an extended linear segment in this transition state"
assert a == b, (f"reaction-direction reversal changed the in-line cap atoms of the linear "
                f"segment: {sorted(map(sorted, a))} vs {sorted(map(sorted, b))}")
print("PASS")
