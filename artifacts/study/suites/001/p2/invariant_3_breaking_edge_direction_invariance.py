import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "source"))
from automol import graph  # noqa: E402

def _signature(gra):
    syms = graph.atom_symbols(gra)
    out = []
    for item in graph.rotational_coordinates(gra):
        seq = tuple(syms[k] for k in item)
        out.append(min(seq, seq[::-1]))
    return sorted(out)

# New TS (not the public fixture): C40-C50 reaction edge (0.1, breaking); C40 also bears CH3 (key 3) and F (key 5).
A = {40: ("C", 0, None), 50: ("C", 0, None), 3: ("C", 0, None), 5: ("F", 0, None),
     9: ("H", 0, None), 12: ("H", 0, None), 13: ("H", 0, None),
     15: ("H", 0, None), 17: ("H", 0, None), 19: ("H", 0, None)}
B = {frozenset({40, 50}): (0.1, None), frozenset({40, 3}): (1, None), frozenset({40, 5}): (1, None),
     frozenset({3, 9}): (1, None), frozenset({3, 12}): (1, None), frozenset({3, 13}): (1, None),
     frozenset({50, 15}): (1, None), frozenset({50, 17}): (1, None), frozenset({50, 19}): (1, None)}
GRA = (A, B)

if __name__ == "__main__":
    sig, sig_rev = _signature(GRA), _signature(graph.ts.reverse(GRA))
    assert sig, "expected a nonempty rotor observation for this rotatable TS"
    assert sig == sig_rev, f"reaction direction changed the rotor observation: fwd={sig} rev={sig_rev}"
    print("PASS")
