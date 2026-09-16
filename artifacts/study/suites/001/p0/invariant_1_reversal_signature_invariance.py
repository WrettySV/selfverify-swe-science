"""Rotor signature must not depend on the reaction direction (0.9 <-> 0.1 re-presentation)."""
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

def sig(gra):
    syms = graph.atom_symbols(gra)
    return sorted(min(tuple(syms[k] for k in c), tuple(syms[k] for k in c)[::-1])
                  for c in graph.rotational_coordinates(gra))

G = build(ATOMS, BONDS)
s_fwd, s_rev = sig(G), sig(graph.ts.reverse(G))
assert s_fwd, "no observable rotor: expected a nonempty rotational signature"
assert s_rev == s_fwd, f"reversing the reaction direction changed the rotor signature: {s_fwd} vs {s_rev}"
CTL = build(ATOMS, [(101, 103, 1), (101, 107, 1), (101, 127, 1), (107, 113, 1),
                    (107, 127, 0.9), (113, 119, 1), (127, 131, 1), (127, 137, 1), (127, 143, 1)])
assert sig(CTL) != s_fwd, "connectivity-changed control collapsed to the same rotor observation"
print("PASS")
