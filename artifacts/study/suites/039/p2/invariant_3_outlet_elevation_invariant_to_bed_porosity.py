import sys, warnings, fcntl
from pathlib import Path
import numpy as np
warnings.filterwarnings("ignore"); sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
_lock = open("/tmp/nst_invariant_load.lock", "a"); fcntl.flock(_lock, fcntl.LOCK_EX)
from workflow.load_candidate import load_candidate_landlab; load_candidate_landlab()
from landlab.components import FlowDirectorSteepest, NetworkSedimentTransporter
from landlab.grid.network import NetworkModelGrid; from landlab.data_record import DataRecord
def run(porosity):
    g = NetworkModelGrid(([0.]*4, [0., 1., 2., 3.]), [(0, 1), (1, 2), (2, 3)])
    for k, v in {"topographic__elevation": [3., 2., 1., 0.], "bedrock__elevation": [3., 2., 1., 0.]}.items(): g.at_node[k] = v
    for k, v in {"reach_length": [100.]*3, "channel_width": [10.]*3, "flow_depth": [1.]*3}.items(): g.at_link[k] = v
    fd = FlowDirectorSteepest(g); fd.run_one_step()
    dr = DataRecord(g, items={"grid_element": "link", "element_id": np.arange(3).reshape(-1, 1)}, time=[0.0], data_vars={
        "abrasion_rate": (["item_id"], np.zeros(3)), "density": (["item_id"], np.full(3, 2650.)),
        "time_arrival_in_link": (["item_id", "time"], np.zeros((3, 1))), "active_layer": (["item_id", "time"], np.ones((3, 1))),
        "location_in_link": (["item_id", "time"], np.full((3, 1), 0.25)), "D": (["item_id", "time"], np.full((3, 1), 0.05)),
        "volume": (["item_id", "time"], np.full((3, 1), 20.0))}, dummy_elements={"link": [NetworkSedimentTransporter.OUT_OF_NETWORK]})
    m = NetworkSedimentTransporter(g, dr, fd, bed_porosity=porosity, g=9.81, fluid_density=1000.)
    [m.run_one_step(60.0) for _ in range(3)]
    return float(g.at_node["topographic__elevation"][-1]), float(m._vol_stor[-1])
e1, s1 = run(0.25)
e2, s2 = run(0.40)
assert s1 > 0.0 and s2 > 0.0, "vacuous setup: final reach holds no stored sediment"
assert abs(e1 - e2) < 1e-9, (
    f"outlet elevation must not depend on channel-bed porosity (no downstream bed stores sediment at the outlet): "
    f"{e1} m at porosity 0.25 vs {e2} m at porosity 0.40")
print("PASS")
