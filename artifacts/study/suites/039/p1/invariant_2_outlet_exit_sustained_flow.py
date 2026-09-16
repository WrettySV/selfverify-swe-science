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

NA = {"y": [0.0, 100.0, 200.0, 200.0, 320.0], "x": [0.0, 0.0, 0.0, -100.0, 0.0], "nal": [[1, 0], [2, 1], [3, 2], [4, 2]],
     "z": [0.0, 8.0, 16.0, 18.0, 26.0], "L": [100.0, 100.0, 141.42, 120.0], "W": [14.0] * 4, "D": [1.0] * 4}
_, rec = run(NA, [2], [0.2], 10, 300.0)
e = rec.dataset.element_id.values
assert np.all(e[:, -1] < 0), (
    "bed-material pulse never reached the network outlet under sustained flow "
    f"(trapped mid-network); final element_id={e[:, -1]} -- data assigned by link id reached the wrong reach"
)
print("PASS")
