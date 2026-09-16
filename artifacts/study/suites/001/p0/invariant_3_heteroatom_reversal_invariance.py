"""Rotor signature invariance under reaction-direction reversal on an N/O heteroatom TS (new elements)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from automol import graph

ATOMS = [(301, "C"), (303, "H"), (307, "C"), (311, "O"), (313, "H"),
         (317, "N"), (319, "H"), (323, "H")]
BONDS = [(301, 303, 1), (301, 307, 1), (301, 317, 0.9), (307, 311, 1),
         (311, 313, 1), (317, 319, 1), (317, 323, 1)]

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
print("PASS")
