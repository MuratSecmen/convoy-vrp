"""
src/loader.py
=============
Parse BCMC-VRPHD instance from Excel.
Expected sheets: Nodes, Vehicles, TravelTime, Demand,
                 ServiceRate, Baseline, Regions
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple
import pandas as pd
import numpy as np


@dataclass
class Instance:
    """Parsed BCMC-VRPHD instance."""

    # Sets
    V: List[int]                     # All nodes (0 = depot)
    V0: List[int]                    # Delivery nodes (V \ {0})
    K: List[int]                     # All vehicles
    K_obs: List[int]                 # Observable vehicles
    K_unobs: List[int]               # Non-observable vehicles
    K_d: Dict[str, List[int]]        # vehicles capable per class
    D: List[str]                     # Supply classes present
    V_d: Dict[str, List[int]]        # nodes demanding class d
    G_r: List[str]                   # AO regions
    V_g: Dict[str, List[int]]        # nodes per region
    E: List[Tuple[int, int]]         # Arc set (i,j), i!=j

    # Parameters
    p: Dict[Tuple[int, int, int], float]   # p[i,j,k] travel time
    s: Dict[int, float]                     # speed factor
    q: Dict[Tuple[int, str], float]         # q[i,d] demand
    r: Dict[Tuple[int, str], float]         # r[k,d] service rate
    C: Dict[int, float]                     # capacity
    L_bar: Dict[int, float]                 # baseline travel time
    node_region: Dict[int, str]             # node -> region
    n_nodes: int
    n_vehicles: int
    name: str = ""


def load_instance(filepath: str) -> Instance:
    """Load instance from Excel file."""

    xls = pd.ExcelFile(filepath)

    # -- Nodes -------------------------------------------------
    df_nodes = pd.read_excel(xls, "Nodes")
    V = sorted(df_nodes["node_id"].tolist())
    V0 = [v for v in V if v != 0]
    node_region = dict(zip(df_nodes["node_id"], df_nodes["ao_region"]))

    # -- Vehicles ----------------------------------------------
    df_veh = pd.read_excel(xls, "Vehicles")
    K = sorted(df_veh["vehicle_id"].tolist())
    K_obs = sorted(df_veh[df_veh["observable"] == True]["vehicle_id"].tolist())
    K_unobs = sorted(df_veh[df_veh["observable"] == False]["vehicle_id"].tolist())

    s = dict(zip(df_veh["vehicle_id"], df_veh["speed_factor"]))
    C = dict(zip(df_veh["vehicle_id"], df_veh["capacity"]))

    # K_d: which vehicles carry which class
    K_d = {}
    for _, row in df_veh.iterrows():
        for cls in str(row["capable_classes"]).split(","):
            cls = cls.strip()
            if cls:
                K_d.setdefault(cls, []).append(row["vehicle_id"])

    # -- Travel Time -------------------------------------------
    df_tt = pd.read_excel(xls, "TravelTime")
    p = {}
    for _, row in df_tt.iterrows():
        p[(int(row["from"]), int(row["to"]), int(row["vehicle_id"]))] = float(row["time_min"])

    # -- Demand ------------------------------------------------
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

    # -- Service Rate ------------------------------------------
    df_sr = pd.read_excel(xls, "ServiceRate")
    r = {}
    for _, row in df_sr.iterrows():
        r[(int(row["vehicle_id"]), str(row["class"]))] = float(row["rate_units_per_min"])

    # -- Baseline ----------------------------------------------
    df_bl = pd.read_excel(xls, "Baseline")
    L_bar = dict(zip(df_bl["vehicle_id"].astype(int), df_bl["baseline_min"].astype(float)))

    # -- Regions -----------------------------------------------
    df_reg = pd.read_excel(xls, "Regions")
    G_r = sorted(df_reg["ao_region"].unique().tolist())
    V_g = {}
    for _, row in df_reg.iterrows():
        reg = str(row["ao_region"])
        nid = int(row["node_id"])
        V_g.setdefault(reg, [])
        if nid not in V_g[reg]:
            V_g[reg].append(nid)

    # -- Arc set -----------------------------------------------
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
