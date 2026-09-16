"""The population of rotational segments must not depend on the reaction direction (branched TS)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from automol import graph

ATOMS = [(401, "C"), (403, "C"), (407, "C"), (411, "C"), (413, "H"), (419, "H"),
         (421, "H"), (427, "H"), (431, "H"), (437, "H"), (443, "S"), (449, "H")]
BONDS = [(401,407,1),(401,403,0.9),(401,411,1),(407,443,1),(443,449,1),(411,413,1),(411,419,1),(411,421,1),(403,427,1),(403,431,1),(403,437,1)]

def build(atoms, bonds):
    return ({k: (s, 0, None) for k, s in atoms},
            {frozenset({a, b}): (o, None) for a, b, o in bonds})

def segs(gra):
    return frozenset(frozenset(s) for s in graph.rotational_segment_keys(gra))

def sig(gra):
    syms = graph.atom_symbols(gra)
    return sorted(min(tuple(syms[k] for k in c), tuple(syms[k] for k in c)[::-1])
                  for c in graph.rotational_coordinates(gra))

G = build(ATOMS, BONDS)
a, b = segs(G), segs(graph.ts.reverse(G))
assert a, "no rotational segment found in this transition state"
assert a == b, (f"reaction-direction reversal changed the rotational segment population: "
                f"{sorted(map(sorted, a))} vs {sorted(map(sorted, b))}")
assert sig(G) == sig(graph.ts.reverse(G)), "rotor signatures changed with reaction direction"
print("PASS")
