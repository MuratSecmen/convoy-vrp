"""
data/generate_instances.py
===========================
Generates ISAF-calibrated BCMC-VRPHD benchmark instances.

Feasibility guards:
  G1. Per-class demand <= 50% of min serving vehicle capacity
  G2. All demand nodes for each vehicle in same AO region
  G3. L_bar = 90% of estimated AO-constrained tour
"""

import os
import numpy as np
import pandas as pd

np.random.seed(42)

SUPPLY_CLASSES = ["I", "II", "III-W", "IV", "IX", "VIII"]
REGIONS = ["RC-Capital", "RC-E", "RC-N", "RC-S", "RC-W"]


def _generate(n_nodes, n_vehicles, name):
    # -- Coordinates (50km radius ~ ISAF regional AO scale)
    xs = np.concatenate([[0], np.random.uniform(-50, 50, n_nodes)])
    ys = np.concatenate([[0], np.random.uniform(-50, 50, n_nodes)])
    node_ids = list(range(n_nodes + 1))
    types = ["depot"] + np.random.choice(
        ["COP", "FOB", "VSP", "ANP"], n_nodes).tolist()

    # -- Vehicles
    veh_ids = list(range(1, n_vehicles + 1))
    capabilities = {}
    for i, cls in enumerate(SUPPLY_CLASSES):
        veh = veh_ids[i % n_vehicles]
        capabilities.setdefault(veh, set()).add(cls)
    for v in veh_ids:
        capabilities.setdefault(v, set())
        for _ in range(np.random.randint(0, 3)):
            capabilities[v].add(np.random.choice(SUPPLY_CLASSES))

    obs_set = set(np.random.choice(
        veh_ids, size=max(1, n_vehicles // 2 + 1), replace=False))
    capacities = np.random.uniform(80, 250, n_vehicles).round(1)
    speed_factors = np.random.uniform(0.8, 1.2, n_vehicles).round(3)

    df_veh = pd.DataFrame({
        "vehicle_id": veh_ids,
        "platform": [np.random.choice(
            ["MRAP", "LMTV", "HEMTT", "M978-Tanker", "MTV"]
        ) for _ in veh_ids],
        "capacity": capacities,
        "speed_factor": speed_factors,
        "observable": [v in obs_set for v in veh_ids],
        "capable_classes": [",".join(sorted(capabilities[v])) for v in veh_ids],
    })

    # -- Travel Time
    tt_lookup = {}
    tt_rows = []
    for i in node_ids:
        for j in node_ids:
            if i == j:
                continue
            dist = np.sqrt((xs[i] - xs[j])**2 + (ys[i] - ys[j])**2)
            for v in veh_ids:
                sf = speed_factors[v - 1]
                noise = np.random.uniform(0.9, 1.3)
                time_min = round(max(5.0, dist / (40 * sf) * noise * 60), 1)
                tt_rows.append({"from": i, "to": j, "vehicle_id": v,
                                "time_min": time_min})
                tt_lookup[(i, j, v)] = time_min
    df_tt = pd.DataFrame(tt_rows)

    # -- Service Rate
    sr_lookup = {}
    sr_rows = []
    for v in veh_ids:
        for cls in capabilities[v]:
            rate = round(np.random.uniform(2, 12), 2)
            sr_rows.append({"vehicle_id": v, "class": cls,
                            "rate_units_per_min": rate})
            sr_lookup[(v, cls)] = rate
    df_sr = pd.DataFrame(sr_rows)

    # -- Demand (G1: capacity-aware)
    cap_budget = {}
    for cls in SUPPLY_CLASSES:
        serving = [v for v in veh_ids if cls in capabilities[v]]
        if not serving:
            cap_budget[cls] = 0
            continue
        min_cap = min(capacities[v - 1] for v in serving)
        cap_budget[cls] = min_cap * 0.5

    dem_rows = []
    for nid in range(1, n_nodes + 1):
        n_cls = np.random.randint(1, min(4, len(SUPPLY_CLASSES) + 1))
        for cls in np.random.choice(SUPPLY_CLASSES, n_cls, replace=False):
            remaining = cap_budget.get(cls, 0)
            if remaining <= 3:
                continue
            qty = round(min(np.random.uniform(2, 15), remaining * 0.35), 1)
            cap_budget[cls] -= qty
            dem_rows.append({"node_id": nid, "class": cls, "quantity": qty})
    if not dem_rows:
        for nid in range(1, min(3, n_nodes + 1)):
            cls = SUPPLY_CLASSES[nid % len(SUPPLY_CLASSES)]
            dem_rows.append({"node_id": nid, "class": cls, "quantity": 5.0})
    df_dem = pd.DataFrame(dem_rows)

    # -- Regions (G2: all vehicle demand nodes in same region)
    regions = ["RC-Capital"] + [None] * n_nodes
    veh_nodes = {v: set() for v in veh_ids}
    for _, row in df_dem.iterrows():
        cls = row["class"]
        nid = int(row["node_id"])
        for v in veh_ids:
            if cls in capabilities[v]:
                veh_nodes[v].add(nid)

    assigned = {}
    for v in veh_ids:
        nodes = veh_nodes[v]
        if not nodes:
            continue
        existing = set(assigned[n] for n in nodes if n in assigned)
        if len(existing) == 1:
            reg = existing.pop()
        elif len(existing) == 0:
            reg = np.random.choice(REGIONS)
        else:
            from collections import Counter
            cnt = Counter(assigned[n] for n in nodes if n in assigned)
            reg = cnt.most_common(1)[0][0]
        for n in nodes:
            assigned[n] = reg

    for nid in range(1, n_nodes + 1):
        regions[nid] = assigned.get(nid, np.random.choice(REGIONS))

    df_nodes = pd.DataFrame({
        "node_id": node_ids, "type": types,
        "x_km": xs.round(1), "y_km": ys.round(1), "ao_region": regions,
    })

    # -- Baseline (G3: achievable within AO)
    # Estimate actual tour: depot -> demand nodes in vehicle's region
    baselines = {}
    for v in veh_ids:
        demand_nodes = sorted(veh_nodes[v])
        if not demand_nodes:
            baselines[v] = 20.0
            continue

        # Estimate tour time
        bl = 0
        prev = 0
        for n in demand_nodes[:4]:
            bl += tt_lookup.get((prev, n, v), 30)
            for cls in capabilities[v]:
                qi = 0
                for _, r in df_dem.iterrows():
                    if int(r["node_id"]) == n and r["class"] == cls:
                        qi = float(r["quantity"])
                        break
                if qi > 0:
                    rd = sr_lookup.get((v, cls), 5.0)
                    bl += qi / rd
            prev = n

        # 90% of estimated tour — achievable but binding
        baselines[v] = round(max(20.0, bl * 0.9), 1)

    df_bl = pd.DataFrame({
        "vehicle_id": veh_ids,
        "baseline_min": [baselines[v] for v in veh_ids],
    })

    reg_rows = [{"node_id": nid, "ao_region": regions[nid]} for nid in node_ids]
    df_reg = pd.DataFrame(reg_rows)

    out_dir = os.path.join(os.path.dirname(__file__), "instances")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{name}.xlsx")

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df_nodes.to_excel(writer, sheet_name="Nodes", index=False)
        df_veh.to_excel(writer, sheet_name="Vehicles", index=False)
        df_tt.to_excel(writer, sheet_name="TravelTime", index=False)
        df_dem.to_excel(writer, sheet_name="Demand", index=False)
        df_sr.to_excel(writer, sheet_name="ServiceRate", index=False)
        df_bl.to_excel(writer, sheet_name="Baseline", index=False)
        df_reg.to_excel(writer, sheet_name="Regions", index=False)

    print(f"  Generated: {out_path}  (baselines: {baselines})")
    return out_path


if __name__ == "__main__":
    print("Generating BCMC-VRPHD benchmark instances...")
    _generate(5,  3,  "small_n5_k3")
    _generate(10, 5,  "medium_n10_k5")
    _generate(15, 7,  "large_n15_k7")
    print("Done.")
