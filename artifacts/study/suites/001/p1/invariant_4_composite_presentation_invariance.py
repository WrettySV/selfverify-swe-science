import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source"))
import automol.graph as graph

GRA = (
    {701: ("C", 0, None), 703: ("C", 0, None), 704: ("H", 0, None), 705: ("C", 0, None),
     706: ("H", 0, None), 707: ("H", 0, None), 708: ("H", 0, None), 709: ("S", 0, None),
     710: ("H", 0, None), 711: ("H", 0, None), 712: ("H", 0, None)},
    {frozenset((701, 703)): (1, None), frozenset((701, 704)): (1, None), frozenset((701, 705)): (0.9, None),
     frozenset((703, 706)): (1, None), frozenset((703, 707)): (1, None), frozenset((703, 708)): (1, None),
     frozenset((705, 709)): (1, None), frozenset((705, 710)): (1, None), frozenset((705, 711)): (1, None),
     frozenset((709, 712)): (1, None)},
)
def remap(gra):
    atoms, bonds = gra
    m = dict(zip(sorted(atoms), reversed(sorted(atoms))))
    return ({m[k]: v for k, v in atoms.items()}, {frozenset(m[a] for a in b): v for b, v in bonds.items()})

def sig(gra):
    syms = graph.atom_symbols(gra)
    seqs = [min(tuple(syms[k] for k in c), tuple(syms[k] for k in c[::-1])) for c in graph.rotational_coordinates(gra)]
    return sorted(seqs)

s_o, s_r, s_m, s_mr = sig(GRA), sig(graph.ts.reverse(GRA)), sig(remap(GRA)), sig(remap(graph.ts.reverse(GRA)))
assert s_o, "expected a nonempty rotor observation for this rotatable TS"
assert s_o == s_r == s_m == s_mr, f"equivalent presentations disagree: {s_o} {s_r} {s_m} {s_mr}"
print("PASS")
