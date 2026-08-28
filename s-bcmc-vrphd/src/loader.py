"""
src/loader.py
=============
Parse a BCMC-VRPHD base instance from Excel — identical schema and
Instance shape as bcmc-vrphd/src/loader.py (this file is a deliberate,
self-contained copy rather than a cross-directory import: the two
projects have no shared package/pyproject.toml, so importing across
`bcmc-vrphd/` and `s-bcmc-vrphd/` would need a sys.path hack; duplicating
this ~90-line loader is simpler and keeps each project runnable on its
own from its own directory, matching bcmc-vrphd's own style).

Expected sheets: Nodes, Vehicles, TravelTime, Demand,
                 ServiceRate, Baseline, Regions
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple
import pandas as pd


@dataclass
class Instance:
    """Parsed BCMC-VRPHD base instance (scenario-independent)."""

    V: List[int]
    V0: List[int]
    K: List[int]
    K_obs: List[int]
    K_unobs: List[int]
    K_d: Dict[str, List[int]]
    D: List[str]
    V_d: Dict[str, List[int]]
    G_r: List[str]
    V_g: Dict[str, List[int]]
    E: List[Tuple[int, int]]

    p: Dict[Tuple[int, int, int], float]
    s: Dict[int, float]
    q: Dict[Tuple[int, str], float]
    r: Dict[Tuple[int, str], float]
    C: Dict[int, float]
    L_bar: Dict[int, float]
    node_region: Dict[int, str]
    n_nodes: int
    n_vehicles: int
    name: str = ""


def load_instance(filepath: str) -> Instance:
    """Load base instance from Excel file (same schema as bcmc-vrphd)."""

    xls = pd.ExcelFile(filepath)

    df_nodes = pd.read_excel(xls, "Nodes")
    V = sorted(df_nodes["node_id"].tolist())
    V0 = [v for v in V if v != 0]
    node_region = dict(zip(df_nodes["node_id"], df_nodes["ao_region"]))

    df_veh = pd.read_excel(xls, "Vehicles")
    K = sorted(df_veh["vehicle_id"].tolist())
    K_obs = sorted(df_veh[df_veh["observable"] == True]["vehicle_id"].tolist())
    K_unobs = sorted(df_veh[df_veh["observable"] == False]["vehicle_id"].tolist())

    s = dict(zip(df_veh["vehicle_id"], df_veh["speed_factor"]))
    C = dict(zip(df_veh["vehicle_id"], df_veh["capacity"]))

    K_d = {}
    for _, row in df_veh.iterrows():
        for cls in str(row["capable_classes"]).split(","):
            cls = cls.strip()
            if cls:
                K_d.setdefault(cls, []).append(row["vehicle_id"])

    df_tt = pd.read_excel(xls, "TravelTime")
    p = {}
    for _, row in df_tt.iterrows():
        p[(int(row["from"]), int(row["to"]), int(row["vehicle_id"]))] = float(row["time_min"])

    df_dem = pd.read_excel(xls, "Demand")
    D = sorted(df_dem["class"].unique().tolist())
    q = {}
    V_d = {}
    for _, row in df_dem.iterrows():
        nid, cls, qty = int(row["node_id"]), str(row["class"]), float(row["quantity"])
        q[(nid, cls)] = qty
        V_d.setdefault(cls, [])
        if nid not in V_d[cls]:
            V_d[cls].append(nid)

    df_sr = pd.read_excel(xls, "ServiceRate")
    r = {}
    for _, row in df_sr.iterrows():
        r[(int(row["vehicle_id"]), str(row["class"]))] = float(row["rate_units_per_min"])

    df_bl = pd.read_excel(xls, "Baseline")
    L_bar = dict(zip(df_bl["vehicle_id"].astype(int), df_bl["baseline_min"].astype(float)))
    non_positive = {k: v for k, v in L_bar.items() if v <= 0}
    if non_positive:
        raise ValueError(
            f"Baseline sheet has non-positive baseline_min for vehicle(s) "
            f"{non_positive} in {filepath}; model.py divides by L_bar[k] "
            f"and requires L_bar[k] > 0."
        )

    df_reg = pd.read_excel(xls, "Regions")
    G_r = sorted(df_reg["ao_region"].unique().tolist())
    V_g = {}
    for _, row in df_reg.iterrows():
        reg = str(row["ao_region"])
        nid = int(row["node_id"])
        V_g.setdefault(reg, [])
        if nid not in V_g[reg]:
            V_g[reg].append(nid)

    E = [(i, j) for i in V for j in V if i != j]

    name = filepath.split("/")[-1].split("\\")[-1].replace(".xlsx", "")

    return Instance(
        V=V, V0=V0, K=K, K_obs=K_obs, K_unobs=K_unobs,
        K_d=K_d, D=D, V_d=V_d, G_r=G_r, V_g=V_g, E=E,
        p=p, s=s, q=q, r=r, C=C, L_bar=L_bar,
        node_region=node_region,
        n_nodes=len(V0), n_vehicles=len(K),
        name=name,
    )
