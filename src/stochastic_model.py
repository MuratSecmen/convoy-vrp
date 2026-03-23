"""
S-BCMC-VRPHD Solver
====================
Two-Stage Stochastic Bi-Objective Min-Max Military Convoy VRP
with Heterogeneous Demand — Stage-1 + Stage-2 MCNF

Objectives (both stochastic):
    f1 = W1 : min max_{omega} max_k  L_k(omega)   [operational efficiency]
    f2 = W2 : min max_{omega} max_k  (L_k(omega) - L_bar_k) / L_bar_k
              + kappa_omega * sum_k deviation_k(omega)  [plan stability + ROE]

Method : epsilon-constraint  ->  Pareto frontier
Solver : PuLP / CBC

References:
    Yakici & Karasakal (2013)  Optimization Letters
    Birge & Louveaux   (1997)  Introduction to Stochastic Programming
    Bektas & Gouveia   (2014)  EJOR
"""

import pulp
import numpy as np
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional


# ─────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────

@dataclass
class Scenario:
    omega_id:     int
    label:        str
    probability:  float          # p_omega
    blocked_arcs: List[Tuple]    # A_omega  (i,j) pairs
    delta:        float          # demand surge multiplier
    kappa:        float          # ROE coefficient


@dataclass
class StochasticInstance:
    name:           str
    nodes:          List[int]
    depot:          int
    vehicles:       List[int]
    supply_classes: List[str]
    travel_time:    Dict         # (i,j,k) -> minutes
    demand:         Dict         # (i,d)   -> service units
    capacity:       Dict         # k       -> tonnes
    service_rate:   Dict         # (k,d)   -> s.u./hour
    vehicle_for_class: Dict      # d       -> [k,...]
    baseline_time:  Dict         # k       -> minutes
    region:         Dict         # node    -> ao_id
    scenarios:      List[Scenario]


@dataclass
class StochasticSolution:
    instance_name: str
    epsilon:       float
    W1:            float
    W2:            float
    L_omega:       Dict          # (k, omega_id) -> minutes
    x:             Dict          # (i,j,k) -> {0,1}
    T:             Dict          # (k,i)   -> hours
    status:        str
    solve_time:    float
    feasible:      bool
    VSS:           Optional[float] = None
    EVPI:          Optional[float] = None


# ─────────────────────────────────────────────────────────────────────
# SOLVER
# ─────────────────────────────────────────────────────────────────────

class SBCMCVRPHDSolver:

    def __init__(self, inst: StochasticInstance,
                 time_limit: int = 600,
                 verbose: bool = False):
        self.inst       = inst
        self.time_limit = time_limit
        self.verbose    = verbose

    # ── Build and solve for a given epsilon ──────────────────────────
    def solve_single(self, epsilon: float) -> StochasticSolution:
        inst = self.inst
        t0   = time.time()

        V    = inst.nodes
        K    = inst.vehicles
        D    = inst.supply_classes
        N    = [v for v in V if v != inst.depot]
        dep  = inst.depot
        OMG  = inst.scenarios

        prob = pulp.LpProblem(f"SBCMC_eps{epsilon:.4f}", pulp.LpMinimize)

        # ── Stage-1 variables ────────────────────────────────────────
        x = {(i,j,k): pulp.LpVariable(f"x_{i}_{j}_{k}", cat="Binary")
             for k in K for i in V for j in V if i != j}

        f = {(i,j,k,d): pulp.LpVariable(f"f_{i}_{j}_{k}_{d}", lowBound=0)
             for k in K for i in V for j in V for d in D
             if i != j and k in inst.vehicle_for_class.get(d, [])}

        T = {(k,i): pulp.LpVariable(f"T_{k}_{i}", lowBound=0)
             for k in K for i in N}

        # ── Stage-2 variables (per scenario) ─────────────────────────
        y = {(i,j,k,o.omega_id):
             pulp.LpVariable(f"y_{i}_{j}_{k}_{o.omega_id}", cat="Binary")
             for o in OMG for k in K for i in V for j in V if i != j}

        g = {(i,j,k,d,o.omega_id):
             pulp.LpVariable(f"g_{i}_{j}_{k}_{d}_{o.omega_id}", lowBound=0)
             for o in OMG for k in K for i in V for j in V for d in D
             if i != j and k in inst.vehicle_for_class.get(d, [])}

        S = {(k,i,o.omega_id): pulp.LpVariable(
                 f"S_{k}_{i}_{o.omega_id}", lowBound=0)
             for o in OMG for k in K for i in N}

        phi = {(d,i,o.omega_id): pulp.LpVariable(
                   f"phi_{d}_{i}_{o.omega_id}", lowBound=0)
               for o in OMG for d in D for i in N
               if inst.demand.get((i,d), 0) > 0}

        # ── Objective variables ───────────────────────────────────────
        W1  = pulp.LpVariable("W1",  lowBound=0)
        W2  = pulp.LpVariable("W2",  lowBound=0)
        W1o = {o.omega_id: pulp.LpVariable(f"W1o_{o.omega_id}", lowBound=0)
               for o in OMG}
        W2o = {o.omega_id: pulp.LpVariable(f"W2o_{o.omega_id}", lowBound=0)
               for o in OMG}
        Lko = {(k,o.omega_id): pulp.LpVariable(
                   f"Lko_{k}_{o.omega_id}", lowBound=0)
               for k in K for o in OMG}

        # ── Objective (S1) ────────────────────────────────────────────
        prob += W1

        # ── (S3–S4) W1,W2 scenario upper bounds ──────────────────────
        for o in OMG:
            prob += W1 >= W1o[o.omega_id], f"W1_scen_{o.omega_id}"
            prob += W2 >= W2o[o.omega_id], f"W2_scen_{o.omega_id}"

        # ── (S5) per-scenario W1 ──────────────────────────────────────
        for o in OMG:
            for k in K:
                prob += W1o[o.omega_id] >= Lko[k,o.omega_id], \
                        f"W1o_{o.omega_id}_{k}"

        # ── (S6) realised travel time ─────────────────────────────────
        M_big = 9999.0
        for o in OMG:
            blocked = set(o.blocked_arcs)
            for k in K:
                arc_t = pulp.lpSum(
                    (inst.travel_time.get((i,j,k), M_big) / 60.0) *
                    x[i,j,k]
                    for i in V for j in V if i != j and j != dep
                    if (i,j) not in blocked
                )
                svc_t = pulp.lpSum(T[k,i] for i in N)
                prob += Lko[k,o.omega_id] == arc_t + svc_t, \
                        f"Lko_def_{k}_{o.omega_id}"

        # ── (S7) plan deviation + ROE penalty ────────────────────────
        for o in OMG:
            for k in K:
                Lb = inst.baseline_time[k]
                if Lb > 0:
                    base_dev = (Lko[k,o.omega_id] - Lb) / Lb
                    roe_pen  = o.kappa * pulp.lpSum(
                        (Lko[kk,o.omega_id] - inst.baseline_time[kk]) /
                        max(inst.baseline_time[kk], 1e-6)
                        for kk in K
                    )
                    prob += W2o[o.omega_id] >= base_dev + roe_pen, \
                            f"W2o_{o.omega_id}_{k}"

        # ── (S8) early arrival prohibition ───────────────────────────
        for o in OMG:
            for k in K:
                prob += Lko[k,o.omega_id] >= inst.baseline_time[k], \
                        f"no_early_{k}_{o.omega_id}"

        # ── (S9) Non-anticipativity (structural — x has no omega idx) ─
        # Enforced by construction: x shared across all scenarios

        # ── (S10) Stage-1 demand satisfaction ────────────────────────
        for d in D:
            for i in N:
                if inst.demand.get((i,d), 0) > 0:
                    veh = inst.vehicle_for_class.get(d, [])
                    prob += (
                        pulp.lpSum(
                            (inst.service_rate.get((k,d), 0) /
                             inst.demand[(i,d)]) * T[k,i]
                            for k in veh
                        ) >= 1,
                        f"s1_dem_{i}_{d}"
                    )

        # ── (S11) Stage-1 capacity ────────────────────────────────────
        for k in K:
            prob += (
                pulp.lpSum(
                    f.get((dep,j,k,d), 0)
                    for j in N for d in D
                    if (dep,j,k,d) in f
                ) <= inst.capacity[k],
                f"s1_cap_{k}"
            )

        # ── (S12) single departure ────────────────────────────────────
        for k in K:
            prob += pulp.lpSum(x[dep,j,k] for j in N) <= 1, \
                    f"s1_dep_{k}"

        # ── (S13) Stage-1 flow conservation ──────────────────────────
        for k in K:
            for j in N:
                prob += (
                    pulp.lpSum(x[i,j,k] for i in V if i != j) ==
                    pulp.lpSum(x[j,i,k] for i in V if i != j),
                    f"s1_fc_{k}_{j}"
                )

        # ── (S14) Stage-1 MCNF depot source ──────────────────────────
        for k in K:
            for d in D:
                if k not in inst.vehicle_for_class.get(d, []):
                    continue
                prob += (
                    pulp.lpSum(
                        f.get((dep,j,k,d), 0) for j in N
                        if (dep,j,k,d) in f
                    ) ==
                    pulp.lpSum(
                        inst.service_rate.get((k,d), 0) * T[k,i]
                        for i in N
                    ),
                    f"s1_mcnf_src_{k}_{d}"
                )

        # ── (S15) Stage-1 MCNF flow conservation ─────────────────────
        for k in K:
            for d in D:
                if k not in inst.vehicle_for_class.get(d, []):
                    continue
                for i in N:
                    infl  = pulp.lpSum(
                        f.get((j,i,k,d), 0) for j in V if j != i
                        if (j,i,k,d) in f
                    )
                    outfl = pulp.lpSum(
                        f.get((i,j,k,d), 0) for j in V if j != i
                        if (i,j,k,d) in f
                    )
                    prob += infl - outfl == \
                            inst.service_rate.get((k,d), 0) * T[k,i], \
                            f"s1_mcnf_fc_{k}_{d}_{i}"

        # ── (S16) Stage-1 MCNF coupling ──────────────────────────────
        for k in K:
            for d in D:
                if k not in inst.vehicle_for_class.get(d, []):
                    continue
                for i in V:
                    for j in V:
                        if i == j or (i,j,k,d) not in f:
                            continue
                        prob += f[i,j,k,d] <= inst.capacity[k] * x[i,j,k], \
                                f"s1_coup_{k}_{d}_{i}_{j}"

        # ── (S17) Stage-2 MCNF flow conservation ─────────────────────
        for o in OMG:
            blocked = set(o.blocked_arcs)
            for k in K:
                for d in D:
                    if k not in inst.vehicle_for_class.get(d, []):
                        continue
                    for i in N:
                        q_eff = inst.demand.get((i,d), 0) * o.delta
                        infl  = pulp.lpSum(
                            g.get((j,i,k,d,o.omega_id), 0)
                            for j in V if j != i
                            and (j,i) not in blocked
                            if (j,i,k,d,o.omega_id) in g
                        )
                        outfl = pulp.lpSum(
                            g.get((i,j,k,d,o.omega_id), 0)
                            for j in V if j != i
                            and (i,j) not in blocked
                            if (i,j,k,d,o.omega_id) in g
                        )
                        delivered = inst.service_rate.get((k,d), 0) * \
                                    S[k,i,o.omega_id]
                        unmet = phi.get((d,i,o.omega_id), 0)
                        prob += infl - outfl == delivered - unmet, \
                                f"s2_fc_{o.omega_id}_{k}_{d}_{i}"

        # ── (S18) Stage-2 MCNF coupling ──────────────────────────────
        for o in OMG:
            for k in K:
                for d in D:
                    if k not in inst.vehicle_for_class.get(d, []):
                        continue
                    for i in V:
                        for j in V:
                            if i == j:
                                continue
                            key = (i,j,k,d,o.omega_id)
                            if key not in g:
                                continue
                            prob += g[key] <= \
                                    inst.capacity[k] * y[i,j,k,o.omega_id], \
                                    f"s2_coup_{o.omega_id}_{k}_{d}_{i}_{j}"

        # ── (S19) blocked arcs ────────────────────────────────────────
        for o in OMG:
            for (i,j) in o.blocked_arcs:
                for k in K:
                    if (i,j,k,o.omega_id) in y:
                        prob += y[i,j,k,o.omega_id] == 0, \
                                f"s2_block_{o.omega_id}_{k}_{i}_{j}"

        # ── (S20) Stage-2 demand satisfaction with surge ──────────────
        for o in OMG:
            for d in D:
                for i in N:
                    q_eff = inst.demand.get((i,d), 0) * o.delta
                    if q_eff <= 0:
                        continue
                    veh = inst.vehicle_for_class.get(d, [])
                    unmet = phi.get((d,i,o.omega_id), 0)
                    prob += (
                        pulp.lpSum(
                            (inst.service_rate.get((k,d), 0) / q_eff) *
                            S[k,i,o.omega_id]
                            for k in veh
                        ) + unmet / q_eff >= 1,
                        f"s2_dem_{o.omega_id}_{d}_{i}"
                    )

        # ── (S21) enforced recourse bound ────────────────────────────
        for o in OMG:
            for d in D:
                for i in N:
                    key = (d,i,o.omega_id)
                    if key not in phi:
                        continue
                    q_eff = inst.demand.get((i,d), 0) * o.delta
                    prob += phi[key] <= q_eff, \
                            f"s2_enf_{o.omega_id}_{d}_{i}"

        # ── (S22) Stage-2 open tour ───────────────────────────────────
        for o in OMG:
            for k in K:
                for i in V:
                    if (i,dep,k,o.omega_id) in y:
                        prob += y[i,dep,k,o.omega_id] == 0, \
                                f"s2_open_{o.omega_id}_{k}_{i}"

        # ── (S23–S24) AO separation ───────────────────────────────────
        A = {(k,g): pulp.LpVariable(f"A_{k}_{g}", cat="Binary")
             for k in K
             for g in set(inst.region.values()) if g != 0}
        regions = {}
        for nd, rg in inst.region.items():
            regions.setdefault(rg, []).append(nd)

        for k in K:
            prob += pulp.lpSum(
                A.get((k,g), 0)
                for g in set(inst.region.values()) if g != 0
            ) <= 1, f"ao_one_{k}"

        for k in K:
            for g, nodes_g in regions.items():
                if g == 0:
                    continue
                for ng in nodes_g:
                    if ng == dep:
                        continue
                    prob += (
                        pulp.lpSum(x[i,ng,k] for i in V if i != ng) <=
                        A.get((k,g), 1),
                        f"ao_arc_{k}_{g}_{ng}"
                    )

        # ── (S28–S29) domains already set via lowBound/cat ───────────

        # ── epsilon constraint on W2 ──────────────────────────────────
        prob += W2 <= epsilon, "eps_W2"

        # ── Solve ─────────────────────────────────────────────────────
        solver = pulp.PULP_CBC_CMD(
            timeLimit=self.time_limit,
            msg=1 if self.verbose else 0
        )
        prob.solve(solver)

        elapsed  = time.time() - t0
        status   = pulp.LpStatus[prob.status]
        feasible = status in ("Optimal", "Feasible")

        W1_val = pulp.value(W1) or 0.0
        W2_val = pulp.value(W2) or 0.0
        L_omega_val = {
            (k, o.omega_id): round(pulp.value(Lko[k,o.omega_id]) or 0.0, 4)
            for k in K for o in OMG
        }
        x_val = {key: int(round(pulp.value(v) or 0))
                 for key, v in x.items()}
        T_val = {key: round(pulp.value(v) or 0.0, 6)
                 for key, v in T.items()}

        return StochasticSolution(
            instance_name=inst.name,
            epsilon=epsilon,
            W1=round(W1_val, 4),
            W2=round(W2_val, 6),
            L_omega=L_omega_val,
            x=x_val,
            T=T_val,
            status=status,
            solve_time=round(elapsed, 2),
            feasible=feasible,
        )

    # ── Pareto frontier ───────────────────────────────────────────────
    def pareto_frontier(self, n_points: int = 8) -> list:
        sol_f1  = self.solve_single(epsilon=1e9)
        W2_max  = sol_f1.W2 if sol_f1.feasible else 1.0
        sol_f2  = self.solve_single(epsilon=0.0)
        W2_min  = sol_f2.W2 if sol_f2.feasible else 0.0

        epsilons = np.linspace(W2_max, max(W2_min, 0.0), n_points)
        frontier = []
        for eps in epsilons:
            sol = self.solve_single(float(eps))
            if sol.feasible:
                frontier.append(sol)
                print(f"  eps={eps:.4f}  W1={sol.W1:.2f}  "
                      f"W2={sol.W2:.4f}  [{sol.status}]  {sol.solve_time}s")
        return frontier

    # ── VSS ───────────────────────────────────────────────────────────
    def compute_vss(self, eps: float = 1e9) -> float:
        """
        VSS = EEV - RP
        EEV: mean-value solution applied to all scenarios
        RP:  stochastic solution
        """
        rp  = self.solve_single(eps)
        W_RP = rp.W1 if rp.feasible else float('inf')

        # Mean-value instance: average demand surge, no blockages
        mean_delta = sum(o.delta * o.probability
                         for o in self.inst.scenarios)
        mean_scen  = Scenario(
            omega_id=999, label="MeanValue",
            probability=1.0, blocked_arcs=[],
            delta=mean_delta, kappa=0.0
        )
        inst_mv       = StochasticInstance(**self.inst.__dict__)
        inst_mv.scenarios = [mean_scen]
        solver_mv     = SBCMCVRPHDSolver(inst_mv,
                                          time_limit=self.time_limit)
        eev           = solver_mv.solve_single(1e9)
        W_EEV         = eev.W1 if eev.feasible else float('inf')

        return round(W_EEV - W_RP, 4)
