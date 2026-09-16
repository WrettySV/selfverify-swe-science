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

# New TS (not the public fixture): C20-C30 reaction edge (0.9, forming); C20 also bears CH3 (key 2) and O-H (keys 4, 6).
A = {20: ("C", 0, None), 30: ("C", 0, None), 2: ("C", 0, None), 4: ("O", 0, None),
     6: ("H", 0, None), 8: ("H", 0, None), 10: ("H", 0, None), 12: ("H", 0, None),
     14: ("H", 0, None), 16: ("H", 0, None), 18: ("H", 0, None)}
B = {frozenset({20, 30}): (0.9, None), frozenset({20, 2}): (1, None), frozenset({20, 4}): (1, None),
     frozenset({4, 6}): (1, None), frozenset({2, 8}): (1, None), frozenset({2, 10}): (1, None),
     frozenset({2, 12}): (1, None), frozenset({30, 14}): (1, None), frozenset({30, 16}): (1, None),
     frozenset({30, 18}): (1, None)}
GRA = (A, B)

if __name__ == "__main__":
    sig, sig_rev = _signature(GRA), _signature(graph.ts.reverse(GRA))
    assert sig, "expected a nonempty rotor observation for this rotatable TS"
    assert sig == sig_rev, f"reaction direction changed the rotor observation: fwd={sig} rev={sig_rev}"
    print("PASS")
