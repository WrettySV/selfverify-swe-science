import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from automol import graph  # noqa: E402
def _signature(gra):
    syms = graph.atom_symbols(gra)
    return sorted(min(tuple(syms[k] for k in it), tuple(syms[k] for k in reversed(it)))
                  for it in graph.rotational_coordinates(gra))

def _presentations(gra):
    keys = sorted(gra[0])
    perms = (None, {k: 500 + 11 * i for i, k in enumerate(reversed(keys))})
    for perm in perms:
        g = gra if perm is None else (
            {perm[k]: v for k, v in gra[0].items()},
            {frozenset(perm[k] for k in b): v for b, v in gra[1].items()})
        yield g, graph.ts.reverse(g)

# New TS (not the public fixture): C31-C33 reaction edge (0.9); C31 bears CH3 (key 3) and N-H (7, 9); C33 is a CH3.
A = {31: ("C", 0, None), 33: ("C", 0, None), 3: ("C", 0, None), 7: ("N", 0, None), 35: ("H", 0, None),
     36: ("H", 0, None), 38: ("H", 0, None), 9: ("H", 0, None), 15: ("H", 0, None), 17: ("H", 0, None), 19: ("H", 0, None)}
B = {frozenset({31, 33}): (0.9, None), frozenset({31, 3}): (1, None), frozenset({31, 7}): (1, None), frozenset({7, 9}): (1, None),
     frozenset({3, 35}): (1, None), frozenset({3, 36}): (1, None), frozenset({3, 38}): (1, None), frozenset({33, 15}): (1, None),
     frozenset({33, 17}): (1, None), frozenset({33, 19}): (1, None)}
GRA = (A, B)

sigs = [s for g, rg in _presentations(GRA) for s in (_signature(g), _signature(rg))]
assert sigs and all(s == sigs[0] for s in sigs), ("equivalent presentations (relabeling and/or reaction reversal) must give the same nonempty rotor observation: "
                                               + " | ".join(map(str, sigs)))
print("PASS")
