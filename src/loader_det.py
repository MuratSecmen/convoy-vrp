"""
data/loader.py
==============
Load BCMC-VRPHD instance from Excel workbook.
Expected sheets: Nodes, Vehicles, TravelTime, Demand,
                 ServiceRate, Baseline, Regions
"""

import pandas as pd
import numpy as np
from src.deterministic_model import Instance


SUPPLY_CLASSES = ["I", "II", "III_W", "IV", "VIII", "IX"]


def load_instance(path: str) -> Instance:
    xl = pd.ExcelFile(path)

    # Each sheet has a title in row 1, blank row 2, headers row 3
    def parse(sheet):
        return xl.parse(sheet, header=2)

    # ── Nodes ──────────────────────────────────────────────────────
    df_nodes = parse("Nodes")
    nodes  = df_nodes["node_id"].tolist()
    depot  = int(df_nodes.loc[df_nodes["type"] == "depot",
                               "node_id"].iloc[0])

    # ── Vehicles ───────────────────────────────────────────────────
    df_veh   = parse("Vehicles")
    vehicles = df_veh["vehicle_id"].tolist()
    capacity = dict(zip(df_veh["vehicle_id"], df_veh["capacity_tonnes"]))

    # ── Travel time p[i][j][k]  (minutes) ─────────────────────────
    df_tt = parse("TravelTime")
    travel_time = {}
    for _, row in df_tt.iterrows():
        travel_time[(int(row["from"]), int(row["to"]),
                     int(row["vehicle_id"]))] = float(row["time_min"])

    # ── Demand q[i][d] ─────────────────────────────────────────────
    df_dem = parse("Demand")
    demand = {}
    for _, row in df_dem.iterrows():
        demand[(int(row["node_id"]), str(row["class"]))] = \
            float(row["quantity"])

    # ── Service rate r[k][d] ───────────────────────────────────────
    df_sr = parse("ServiceRate")
    service_rate = {}
    vehicle_for_class: dict = {d: [] for d in SUPPLY_CLASSES}
    for _, row in df_sr.iterrows():
        k = int(row["vehicle_id"])
        d = str(row["class"])
        r = float(row["rate"])
        service_rate[(k, d)] = r
        if r > 0 and k not in vehicle_for_class[d]:
            vehicle_for_class[d].append(k)

    # ── Baseline travel times L_bar[k] ────────────────────────────
    df_base = parse("Baseline")
    baseline_time = dict(zip(df_base["vehicle_id"],
                             df_base["baseline_min"]))

    # ── Regions ────────────────────────────────────────────────────
    df_reg = parse("Regions")
    region = dict(zip(df_reg["node_id"], df_reg["ao_region"]))

    name = path.split("/")[-1].replace(".xlsx", "")

    return Instance(
        name=name,
        nodes=nodes,
        depot=depot,
        travel_time=travel_time,
        supply_classes=SUPPLY_CLASSES,
        demand=demand,
        capacity=capacity,
        service_rate=service_rate,
        vehicle_for_class=vehicle_for_class,
        baseline_time=baseline_time,
        region=region,
        vehicles=vehicles,
    )
