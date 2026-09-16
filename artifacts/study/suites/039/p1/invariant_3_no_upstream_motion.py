import sys; from pathlib import Path
import numpy as np
R = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(R))
from workflow.load_candidate import load_candidate_landlab; load_candidate_landlab()
from landlab.components import FlowDirectorSteepest, NetworkSedimentTransporter; from landlab.grid.network import NetworkModelGrid
from workflow.river_experiment import _make_parcels
def run(net, links, locs, steps, dt):
    g = NetworkModelGrid((net["y"], net["x"]), np.array(net["nal"], dtype=int))
    g.at_node["topographic__elevation"] = g.at_node["bedrock__elevation"] = np.array(net["z"], float)
    for f, v in (("reach_length", net["L"]), ("channel_width", net["W"]), ("flow_depth", net["D"])): g.at_link[f] = np.array(v, float)
    fd = FlowDirectorSteepest(g); fd.run_one_step()
    pp = [{"pulse_id": str(i), "starting_link": int(l), "normalized_location": float(o)} for i, (l, o) in enumerate(zip(links, locs))]
    rec = _make_parcels({"material": {"abrasion_rate_m_inverse": 0.0, "sediment_density_kg_m3": 2650.0, "grain_diameter_m": 0.02}, "physical_pulses": pp, "sediment_record": [{"pulse_id": q["pulse_id"], "volume_m3": 1.0} for q in pp]}, g)
    m = NetworkSedimentTransporter(g, rec, fd, bed_porosity=0.2, fluid_density=1000.0)
    for _ in range(steps):
        try: m.run_one_step(dt)
        except RuntimeError: break
    return g, rec
NC = {"y": [300.0, 200.0, 100.0, 0.0], "x": [0.0, 40.0, -30.0, 10.0], "nal": [[0, 1], [1, 2], [2, 3]], "z": [24.0, 16.0, 8.0, 0.0],
     "L": [125.0, 125.0, 125.0], "W": [15.0] * 3, "D": [1.0] * 3}
g, rec = run(NC, [0, 2], [0.1, 0.1], 4, 10.0); e = rec.dataset.element_id.values
X, Y = np.array(NC["x"], float), np.array(NC["y"], float)
pi = [int(np.argmax((np.abs(X - g.x_of_node[k]) < 1e-6) & (np.abs(Y - g.y_of_node[k]) < 1e-6))) for k in range(4)]
lm = [next(jj for jj, ab in enumerate(NC["nal"]) if set(pi[x] for x in g.nodes_at_link[j]) == set(ab)) for j in range(3)]
seq = [[lm[int(e[p, t])] if e[p, t] >= 0 else -1 for t in range(e.shape[1])] for p in range(2)]
dlink = [250.0, 125.0, 0.0]
up = [any(dlink[a] > dlink[b] + 1e-9 for a, b in zip(s[1:], s[:-1]) if min(a, b) >= 0) for s in seq]
assert not any(up), f"sediment moved upstream against the supplied topography (physical link sequence per parcel): {seq}"
texit = [next((t for t in range(e.shape[1]) if e[p, t] < 0), 99) for p in range(2)]; assert texit[1] <= texit[0], f"near-outlet release exited after far-outlet release (causality violated): {texit}"
print("PASS")
