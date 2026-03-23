"""
BCMC-VRPHD Solver
=================
Bi-Objective Capacitated Military Convoy Vehicle Routing Problem
with Heterogeneous Demand — Deterministic Layer

Objectives:
    f1 = W1  : min max travel time   (operational efficiency)
    f2 = W2  : min max plan deviation (plan stability)

Method: epsilon-constraint  →  Pareto frontier
        Primary: minimise W1
        Constraint: W2 <= epsilon

References:
    Yakici & Karasakal (2013) — Optimization Letters
    Karasakal et al. (2011)  — Naval Research Logistics
    Haimes et al. (1971)     — IEEE Trans. SMC
    Bektas & Gouveia (2014)  — EJOR
"""

import pulp
import numpy as np
import pandas as pd
import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional


# ─────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────

@dataclass
class Instance:
    """Full problem instance for BCMC-VRPHD."""
    name: str
    # Nodes: 0 = staging area (FOB), 1..n = delivery points
    nodes: List[int]
    depot: int
    # Travel times p[i][j][k]  (minutes)
    travel_time: Dict[Tuple[int,int,int], float]
    # Supply classes: I, II, III_W, IV, VIII, IX
    supply_classes: List[str]
    # Demand q[i][d]  (service units)
    demand: Dict[Tuple[int,str], float]
    # Vehicle capacity C[k]  (tonnes)
    capacity: Dict[int, float]
    # Service rate r[k][d]  (service units / hour)
    service_rate: Dict[Tuple[int,str], float]
    # Vehicle-class compatibility
    vehicle_for_class: Dict[str, List[int]]
    # Baseline plan L_bar[k]  (minutes) — CJ4 morning briefing
    baseline_time: Dict[int, float]
    # AO regions: region[v] -> g
    region: Dict[int, int]
    # Vehicles
    vehicles: List[int]


@dataclass
class Solution:
    """Solution container."""
    instance_name: str
    epsilon: float
    W1: float
    W2: float
    L: Dict[int, float]          # actual travel time per vehicle
    x: Dict[Tuple, int]          # routing arcs
    T: Dict[Tuple, float]        # service times
    flow: Dict[Tuple, float]     # commodity flows
    status: str
    solve_time: float
    feasible: bool


# ─────────────────────────────────────────────────────────────────────
# SOLVER
# ─────────────────────────────────────────────────────────────────────

class BCMCVRPHDSolver:
    """
    Epsilon-constraint MIP solver for BCMC-VRPHD.
    Uses PuLP with CBC backend.
    """

    def __init__(self, instance: Instance, time_limit: int = 300,
                 verbose: bool = False):
        self.inst      = instance
        self.time_limit = time_limit
        self.verbose   = verbose

    def solve_single(self, epsilon: float) -> Solution:
        """
        Solve for a given epsilon (W2 <= epsilon).
        Returns Solution object.
        """
        inst = self.inst
        t0   = time.time()

        V  = inst.nodes
        K  = inst.vehicles
        D  = inst.supply_classes
        N  = [v for v in V if v != inst.depot]
        depot = inst.depot

        prob = pulp.LpProblem(f"BCMC_VRPHD_eps{epsilon:.3f}",
                              pulp.LpMinimize)

        # ── Decision variables ──────────────────────────────────────
        # x[i,j,k]  routing
        x = {(i,j,k): pulp.LpVariable(f"x_{i}_{j}_{k}", cat='Binary')
             for k in K for i in V for j in V if i != j}

        # f[i,j,k,d]  commodity flow
        f = {(i,j,k,d): pulp.LpVariable(f"f_{i}_{j}_{k}_{d}",
                                          lowBound=0)
             for k in K for i in V for j in V
             for d in D if i != j
             if k in inst.vehicle_for_class.get(d, [])}

        # T[k,i]  service time
        T = {(k,i): pulp.LpVariable(f"T_{k}_{i}", lowBound=0)
             for k in K for i in N}

        # L[k]  actual travel time
        L = {k: pulp.LpVariable(f"L_{k}", lowBound=0) for k in K}

        W1 = pulp.LpVariable("W1", lowBound=0)
        W2 = pulp.LpVariable("W2", lowBound=0)

        # ── Objective ───────────────────────────────────────────────
        prob += W1

        # ── (3) W1 upper bound ──────────────────────────────────────
        for k in K:
            prob += W1 >= L[k], f"W1_bound_{k}"

        # ── (4) Travel time definition ──────────────────────────────
        for k in K:
            arc_time = pulp.lpSum(
                (inst.travel_time.get((i,j,k), 0) / 60.0) * x[i,j,k]
                for i in V for j in V if i != j
                if j != depot
            )
            svc_time = pulp.lpSum(T[k,i] for i in N)
            prob += L[k] == arc_time + svc_time, f"Lk_def_{k}"

        # ── (5) Early arrival prohibition ───────────────────────────
        for k in K:
            prob += L[k] >= inst.baseline_time[k], f"no_early_{k}"

        # ── (6) W2 normalised lateness ──────────────────────────────
        for k in K:
            Lb = inst.baseline_time[k]
            if Lb > 0:
                prob += W2 >= (L[k] - Lb) / Lb, f"W2_bound_{k}"

        # ── (6b) Epsilon constraint ──────────────────────────────────
        prob += W2 <= epsilon, "eps_constraint"

        # ── (7) Demand satisfaction (split delivery) ─────────────────
        for d in D:
            for i in N:
                if inst.demand.get((i,d), 0) > 0:
                    veh = inst.vehicle_for_class.get(d, [])
                    prob += (
                        pulp.lpSum(
                            (inst.service_rate.get((k,d), 0) /
                             inst.demand.get((i,d), 1)) * T[k,i]
                            for k in veh
                        ) >= 1,
                        f"demand_{i}_{d}"
                    )

        # ── (8) Capacity via MCNF depot outflow ──────────────────────
        for k in K:
            prob += (
                pulp.lpSum(
                    f.get((depot,j,k,d), 0)
                    for j in N for d in D
                    if (depot,j,k,d) in f
                ) <= inst.capacity[k],
                f"capacity_{k}"
            )

        # ── (9) Single departure ─────────────────────────────────────
        for k in K:
            prob += (
                pulp.lpSum(x[depot,j,k] for j in N) <= 1,
                f"single_dep_{k}"
            )

        # ── (10) Flow conservation (routing) ─────────────────────────
        for k in K:
            for j in N:
                prob += (
                    pulp.lpSum(x[i,j,k] for i in V if i != j) ==
                    pulp.lpSum(x[j,i,k] for i in V if i != j),
                    f"flow_cons_{k}_{j}"
                )

        # ── (11) MCNF depot source balance ───────────────────────────
        for k in K:
            for d in D:
                if k not in inst.vehicle_for_class.get(d, []):
                    continue
                prob += (
                    pulp.lpSum(
                        f.get((depot,j,k,d), 0) for j in N
                        if (depot,j,k,d) in f
                    ) ==
                    pulp.lpSum(
                        inst.service_rate.get((k,d), 0) * T[k,i]
                        for i in N
                    ),
                    f"mcnf_src_{k}_{d}"
                )

        # ── (12) MCNF flow conservation at delivery nodes ────────────
        for k in K:
            for d in D:
                if k not in inst.vehicle_for_class.get(d, []):
                    continue
                for i in N:
                    inflow  = pulp.lpSum(
                        f.get((j,i,k,d), 0) for j in V if j != i
                        if (j,i,k,d) in f
                    )
                    outflow = pulp.lpSum(
                        f.get((i,j,k,d), 0) for j in V if j != i
                        if (i,j,k,d) in f
                    )
                    delivered = inst.service_rate.get((k,d), 0) * T[k,i]
                    prob += (
                        inflow - outflow == delivered,
                        f"mcnf_cons_{k}_{d}_{i}"
                    )

        # ── (13) MCNF flow-routing coupling ─────────────────────────
        for k in K:
            for d in D:
                if k not in inst.vehicle_for_class.get(d, []):
                    continue
                for i in V:
                    for j in V:
                        if i == j:
                            continue
                        if (i,j,k,d) not in f:
                            continue
                        prob += (
                            f[i,j,k,d] <= inst.capacity[k] * x[i,j,k],
                            f"mcnf_coup_{k}_{d}_{i}_{j}"
                        )

        # ── (14) Routing-service link ────────────────────────────────
        M_big = 1e6
        for k in K:
            for d in D:
                if k not in inst.vehicle_for_class.get(d, []):
                    continue
                for j in N:
                    if inst.demand.get((j,d), 0) == 0:
                        continue
                    r = inst.service_rate.get((k,d), 1)
                    q = inst.demand.get((j,d), 1)
                    prob += (
                        T[k,j] <= (q / r) *
                        pulp.lpSum(x[i,j,k] for i in V if i != j),
                        f"rout_svc_{k}_{d}_{j}"
                    )

        # ── (15-16) AO separation ────────────────────────────────────
        # Soft enforcement via large travel times for inter-region arcs
        # (already encoded in travel_time matrix as M_big)

        # ── Solve ────────────────────────────────────────────────────
        solver = pulp.PULP_CBC_CMD(
            timeLimit=self.time_limit,
            msg=1 if self.verbose else 0
        )
        prob.solve(solver)

        elapsed = time.time() - t0
        status  = pulp.LpStatus[prob.status]
        feasible = status in ("Optimal", "Feasible")

        # ── Extract solution ─────────────────────────────────────────
        W1_val = pulp.value(W1) or 0.0
        W2_val = pulp.value(W2) or 0.0
        L_val  = {k: pulp.value(L[k]) or 0.0 for k in K}
        x_val  = {key: int(round(pulp.value(v) or 0))
                  for key, v in x.items()}
        T_val  = {key: (pulp.value(v) or 0.0) for key, v in T.items()}
        f_val  = {key: (pulp.value(v) or 0.0) for key, v in f.items()}

        return Solution(
            instance_name=inst.name,
            epsilon=epsilon,
            W1=round(W1_val, 4),
            W2=round(W2_val, 6),
            L={k: round(v, 4) for k, v in L_val.items()},
            x=x_val,
            T=T_val,
            flow=f_val,
            status=status,
            solve_time=round(elapsed, 2),
            feasible=feasible,
        )

    def pareto_frontier(self, n_points: int = 10
                        ) -> List[Solution]:
        """
        Trace Pareto frontier by sweeping epsilon from W2_max to W2_min.
        Returns list of non-dominated solutions.
        """
        # Step 1: W2_max  (solve f1 only, epsilon = inf)
        sol_f1 = self.solve_single(epsilon=1e9)
        W2_max = sol_f1.W2 if sol_f1.feasible else 1.0

        # Step 2: W2_min  (solve f2 only — set epsilon = 0, maximise
        #          plan adherence, accept larger W1)
        sol_f2 = self.solve_single(epsilon=0.0)
        W2_min = sol_f2.W2 if sol_f2.feasible else 0.0

        if W2_max <= W2_min:
            return [sol_f1]

        epsilons = np.linspace(W2_max, W2_min, n_points)
        frontier = []
        for eps in epsilons:
            sol = self.solve_single(epsilon=float(eps))
            if sol.feasible:
                frontier.append(sol)
                print(f"  eps={eps:.4f}  W1={sol.W1:.2f}  "
                      f"W2={sol.W2:.4f}  [{sol.status}]  "
                      f"{sol.solve_time}s")
        return frontier
