"""
BCMC-VRPHD Benchmark Instance Generator
========================================
Generates Excel instances for the Bi-Objective Capacitated Military
Convoy VRP with Heterogeneous Demand (deterministic formulation).

Supply classes: I, II, III-W, IV, VIII, IX
(NATO STANAG I-V + US Army VIII/IX per ISAF/IJC CJ4 practice)

Sheets: Nodes, Vehicles, TravelTime, Demand, ServiceRate, Baseline, Regions
"""

import numpy as np
import pandas as pd
from pathlib import Path
import itertools

SUPPLY_CLASSES = ["I", "II", "III-W", "IV", "VIII", "IX"]

# ISAF Regional Commands
AO_REGIONS = ["RC-N", "RC-W", "RC-S", "RC-E", "RC-Capital"]

# Vehicle platforms used in ISAF ground convoys
PLATFORMS = [
    {"name": "HEMTT-A4",  "cap": 120, "speed": 0.85, "obs": True,
     "classes": ["I", "II", "IV"]},
    {"name": "M978-Tanker", "cap": 200, "speed": 0.80, "obs": True,
     "classes": ["III-W"]},
    {"name": "LMTV-M1078", "cap": 60,  "speed": 1.00, "obs": False,
     "classes": ["I", "II", "VIII", "IX"]},
    {"name": "PLS-M1075",  "cap": 150, "speed": 0.75, "obs": True,
     "classes": ["I", "II", "IV", "IX"]},
    {"name": "MRAP-MaxxPro", "cap": 30, "speed": 0.70, "obs": False,
     "classes": ["VIII", "IX"]},
]

NODE_TYPES = ["COP", "VSP", "ANP", "FOB", "PRT"]


def _haversine_minutes(x1, y1, x2, y2, base_speed_kmh=40):
    """Euclidean distance (km) → travel time (minutes) at base_speed."""
    dist_km = np.sqrt((x1 - x2)**2 + (y1 - y2)**2)
    return max(1.0, dist_km / base_speed_kmh * 60)


def generate_instance(n_nodes: int, n_vehicles: int, seed: int = 42):
    """Generate a single BCMC-VRPHD instance.

    Parameters
    ----------
    n_nodes : int
        Number of delivery nodes (excluding depot).
    n_vehicles : int
        Number of convoy vehicles.
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    dict of DataFrames, keyed by sheet name.
    """
    rng = np.random.RandomState(seed)

    # ── Nodes ────────────────────────────────────────────────
    # Determine active AO regions first
    if n_vehicles <= 3:
        active_regions = [AO_REGIONS[0]]  # single AO for small instances
    else:
        n_regions = min(len(AO_REGIONS), n_vehicles)
        active_regions = AO_REGIONS[:n_regions]

    region_assignments = [active_regions[i % len(active_regions)]
                          for i in range(n_nodes)]
    rng.shuffle(region_assignments)

    # Depot (vertex 0) in first active region
    nodes = [{"node_id": 0, "type": "depot", "x_km": 50.0, "y_km": 50.0,
              "ao_region": active_regions[0]}]

    # Region center offsets for spatial clustering
    region_centers = {
        "RC-N": (50, 90), "RC-W": (10, 50), "RC-S": (50, 10),
        "RC-E": (90, 50), "RC-Capital": (50, 50),
    }

    for i in range(1, n_nodes + 1):
        reg = region_assignments[i - 1]
        cx, cy = region_centers[reg]
        x = cx + rng.uniform(-20, 20)
        y = cy + rng.uniform(-20, 20)
        ntype = rng.choice(NODE_TYPES)
        nodes.append({"node_id": i, "type": ntype,
                       "x_km": round(x, 1), "y_km": round(y, 1),
                       "ao_region": reg})

    df_nodes = pd.DataFrame(nodes)

    # ── Vehicles ─────────────────────────────────────────────
    vehicles = []
    for k in range(1, n_vehicles + 1):
        plat = PLATFORMS[(k - 1) % len(PLATFORMS)]
        cap_noise = rng.uniform(0.9, 1.1)
        vehicles.append({
            "vehicle_id": k,
            "platform": plat["name"],
            "capacity": round(plat["cap"] * cap_noise, 1),
            "speed_factor": plat["speed"],
            "observable": plat["obs"],
            "capable_classes": ",".join(plat["classes"]),
        })
    df_vehicles = pd.DataFrame(vehicles)

    # ── Travel Time ──────────────────────────────────────────
    travel_rows = []
    for k_row in vehicles:
        kid = k_row["vehicle_id"]
        sf = k_row["speed_factor"]
        obs = k_row["observable"]
        for i in range(n_nodes + 1):
            ni = df_nodes.iloc[i]
            for j in range(n_nodes + 1):
                if i == j:
                    continue
                nj = df_nodes.iloc[j]
                base_min = _haversine_minutes(
                    ni["x_km"], ni["y_km"],
                    nj["x_km"], nj["y_km"])
                # Speed-adjusted
                adjusted = base_min / sf
                # Non-observable: add EWMA noise (threat + road)
                if not obs:
                    threat = rng.uniform(0, 15)
                    road = rng.uniform(0, 10)
                    adjusted += threat + road
                travel_rows.append({
                    "from": i, "to": j,
                    "vehicle_id": kid,
                    "time_min": round(adjusted, 1),
                })
    df_travel = pd.DataFrame(travel_rows)

    # ── Demand ───────────────────────────────────────────────
    # Determine which classes are actually serviceable
    available_classes = set()
    for v_row in vehicles:
        for cls in v_row["capable_classes"].split(","):
            available_classes.add(cls.strip())
    available_classes = sorted(available_classes)

    demand_rows = []
    for i in range(1, n_nodes + 1):
        # Each node demands 1-2 random supply classes from available
        n_classes = rng.randint(1, min(3, len(available_classes) + 1))
        chosen = rng.choice(available_classes, size=n_classes, replace=False)
        for cls in chosen:
            qty = rng.randint(5, 25)  # small quantities for feasibility
            demand_rows.append({
                "node_id": i, "class": cls, "quantity": qty,
            })
    df_demand = pd.DataFrame(demand_rows)

    # ── Capacity feasibility check: scale down if needed ─────
    # For each class d: total demand must not exceed aggregate
    # capacity of all capable vehicles.
    # Key insight: MCNF eq(11) forces depot_out_k_d = total_delivered_k_d
    # and eq(8) forces sum_d depot_out_k_d <= C_k.
    # So for each vehicle k: sum over d of (total it delivers in d) <= C_k.
    # Worst case: single vehicle carries a class alone.
    veh_cap = {v["vehicle_id"]: v["capacity"] for v in vehicles}
    veh_classes = {}
    for v in vehicles:
        for cls in v["capable_classes"].split(","):
            veh_classes.setdefault(cls.strip(), []).append(v["vehicle_id"])

    for cls in available_classes:
        total_dem = df_demand[df_demand["class"] == cls]["quantity"].sum()
        agg_cap = sum(veh_cap[k] for k in veh_classes.get(cls, []))
        if total_dem > 0 and agg_cap > 0 and total_dem > agg_cap * 0.4:
            scale = (agg_cap * 0.3) / total_dem
            mask = df_demand["class"] == cls
            df_demand.loc[mask, "quantity"] = (
                df_demand.loc[mask, "quantity"] * scale
            ).round().astype(int).clip(lower=1)

    # ── Service Rate ─────────────────────────────────────────
    srate_rows = []
    base_rates = {"I": 8, "II": 6, "III-W": 12, "IV": 4, "VIII": 5, "IX": 3}
    for k_row in vehicles:
        kid = k_row["vehicle_id"]
        capable = k_row["capable_classes"].split(",")
        for cls in capable:
            rate = base_rates.get(cls, 5) * rng.uniform(0.8, 1.2)
            srate_rows.append({
                "vehicle_id": kid, "class": cls,
                "rate_units_per_min": round(rate, 2),
            })
    df_srate = pd.DataFrame(srate_rows)

    # ── Baseline (planned travel times from CJ4 briefing) ───
    baseline_rows = []
    for k_row in vehicles:
        kid = k_row["vehicle_id"]
        # Baseline = average of possible route times + small buffer
        avg_times = df_travel[df_travel["vehicle_id"] == kid]["time_min"]
        base_val = avg_times.mean() * rng.uniform(1.5, 2.5)
        baseline_rows.append({
            "vehicle_id": kid,
            "baseline_min": round(base_val, 1),
        })
    df_baseline = pd.DataFrame(baseline_rows)

    # ── Regions ──────────────────────────────────────────────
    df_regions = df_nodes[["node_id", "ao_region"]].copy()

    return {
        "Nodes": df_nodes,
        "Vehicles": df_vehicles,
        "TravelTime": df_travel,
        "Demand": df_demand,
        "ServiceRate": df_srate,
        "Baseline": df_baseline,
        "Regions": df_regions,
    }


def save_instance(sheets: dict, filepath: str):
    """Write instance sheets to an Excel file."""
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
    print(f"  ✓ {filepath}")


def main():
    out_dir = Path(__file__).parent / "instances"
    out_dir.mkdir(parents=True, exist_ok=True)

    configs = [
        ("small_n5_k3",   5,  3,  42),
        ("medium_n10_k5", 10, 5,  123),
        ("large_n15_k7",  15, 7,  456),
    ]

    print("Generating BCMC-VRPHD benchmark instances...")
    for name, n, k, seed in configs:
        sheets = generate_instance(n_nodes=n, n_vehicles=k, seed=seed)
        save_instance(sheets, str(out_dir / f"{name}.xlsx"))

    print("Done.")


if __name__ == "__main__":
    main()
