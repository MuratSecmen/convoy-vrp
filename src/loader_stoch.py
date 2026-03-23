"""
src/loader.py — Stochastic instance Excel loader
"""

import pandas as pd
from src.stochastic_model import StochasticInstance, Scenario

SUPPLY_CLASSES = ["I","II","III_W","IV","VIII","IX"]


def load_instance(path: str) -> StochasticInstance:
    xl = pd.ExcelFile(path)

    def parse(sheet):
        return xl.parse(sheet, header=2)

    # Nodes
    df_n    = parse("Nodes")
    nodes   = df_n["node_id"].tolist()
    depot   = int(df_n.loc[df_n["type"]=="depot","node_id"].iloc[0])

    # Vehicles
    df_v    = parse("Vehicles")
    vehicles = df_v["vehicle_id"].tolist()
    capacity = dict(zip(df_v["vehicle_id"],df_v["capacity_tonnes"]))

    # TravelTime
    df_tt = parse("TravelTime")
    travel_time = {}
    for _, r in df_tt.iterrows():
        travel_time[(int(r["from"]),int(r["to"]),
                     int(r["vehicle_id"]))] = float(r["time_min"])

    # Demand
    df_d = parse("Demand")
    demand = {}
    for _, r in df_d.iterrows():
        demand[(int(r["node_id"]),str(r["class"]))] = float(r["quantity"])

    # ServiceRate
    df_sr = parse("ServiceRate")
    service_rate = {}
    vehicle_for_class = {d:[] for d in SUPPLY_CLASSES}
    for _, r in df_sr.iterrows():
        k = int(r["vehicle_id"]); d = str(r["class"])
        rv = float(r["rate"])
        service_rate[(k,d)] = rv
        if rv > 0 and k not in vehicle_for_class[d]:
            vehicle_for_class[d].append(k)

    # Baseline
    df_bl = parse("Baseline")
    baseline_time = dict(zip(df_bl["vehicle_id"],df_bl["baseline_min"]))

    # Regions
    df_r  = parse("Regions")
    region = dict(zip(df_r["node_id"],df_r["ao_region"]))

    # Scenarios
    df_s = parse("Scenarios")
    # BlockedArcs per scenario
    try:
        df_ba = parse("BlockedArcs")
        blocked_map = {}
        for _, r in df_ba.iterrows():
            oid = int(r["omega_id"])
            blocked_map.setdefault(oid,[]).append(
                (int(r["from"]),int(r["to"])))
    except Exception:
        blocked_map = {}

    scenarios = []
    for _, r in df_s.iterrows():
        oid = int(r["omega_id"])
        scenarios.append(Scenario(
            omega_id    = oid,
            label       = str(r["label"]),
            probability = float(r["probability"]),
            blocked_arcs= blocked_map.get(oid, []),
            delta       = float(r["delta"]),
            kappa       = float(r["kappa"]),
        ))

    name = path.split("/")[-1].replace(".xlsx","")
    return StochasticInstance(
        name=name, nodes=nodes, depot=depot,
        vehicles=vehicles, supply_classes=SUPPLY_CLASSES,
        travel_time=travel_time, demand=demand, capacity=capacity,
        service_rate=service_rate, vehicle_for_class=vehicle_for_class,
        baseline_time=baseline_time, region=region,
        scenarios=scenarios,
    )
