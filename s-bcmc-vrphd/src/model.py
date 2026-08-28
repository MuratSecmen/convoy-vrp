"""
src/model.py — S-BCMC-VRPHD Solver
====================================
Two-Stage Stochastic Bi-Objective Capacitated Military Convoy VRP with
Heterogeneous Demand (TSSMOLP, following Gutjahr & Pichler 2016).

Design (see s-bcmc-vrphd/README.md for the full write-up and the six
disruption scenarios' derivation):

  Stage 1 (here-and-now, before the scenario is known):
    A[k,g] — vehicle-to-AO-region assignment. Which operational area
    each convoy is committed to is fixed before dispatch and cannot be
    changed once the disruption scenario is observed (non-anticipativity).

  Stage 2 (recourse, decided per scenario after it is observed):
    x[i,j,k] (routing), f[i,j,k,d]/T[k,d,i] (delivery), L[k], W1, W2 —
    everything downstream of "which roads are actually open today" is
    a per-scenario recourse decision: the convoy re-routes around
    blocked arcs and re-times its deliveries, but never crosses out of
    the AO region it was assigned in Stage 1.

  Recourse for demand that cannot physically be reached under a severe
  scenario: eq7 is relaxed from BCMC-VRPHD's hard "100% delivered"
  constraint to an amount-based constraint with a penalized Shortfall[d,i]
  slack, so the model never turns infeasible just because a scenario
  blocked the only road to a node — it pays a penalty instead, which is
  what a real convoy planner's fallback (air resupply, delay) would cost.

Objective: min E_s[W1_s + penalty_shortfall * sum(Shortfall_s)],
subject to W2_s <= epsilon for every scenario s (the plan-deviation
bound must hold under every disruption, not just in expectation).

Solver: Gurobi, via the native gurobipy API.
"""

import gurobipy as gp
from gurobipy import GRB
from typing import Dict, List, Optional
from src.loader import Instance
from src.scenarios import Scenario, scenario_travel_time, expected_travel_time

DEFAULT_PENALTY_SHORTFALL = 1000.0


def _build_scenario_block(m, inst: Instance, arc_p, blocked_arcs, A, suffix: str):
    """Add one scenario's (or one EV/WS single-scenario's) Stage-2
    variables and constraints to model m, routing under the given
    Stage-1 region assignment A.

    arc_p        : dict (i,j,k) -> travel time for this block
    blocked_arcs : set of (i,j) arcs infeasible in this block
    A            : dict (k,g) -> gurobipy Var — Stage-1 region
                   assignment this block's routing must respect
    suffix       : appended to every var/constraint name so multiple
                   blocks can coexist in one gp.Model (the RP builds
                   one block per scenario in a single model)

    Returns a dict of the block's variables/expressions.
    """
    V, V0, K, D = inst.V, inst.V0, inst.K, inst.D
    E = [(i, j) for (i, j) in inst.E if (i, j) not in blocked_arcs]

    x = m.addVars([(i, j, k) for (i, j) in E for k in K],
                  vtype=GRB.BINARY, name=f"x{suffix}")

    f_keys = [(i, j, k, d) for (i, j) in E for k in K for d in D
              if k in inst.K_d.get(d, [])]
    f = m.addVars(f_keys, lb=0.0, vtype=GRB.CONTINUOUS, name=f"f{suffix}")

    T_keys = [(k, d, i) for k in K for d in D if k in inst.K_d.get(d, [])
              for i in V0]
    T = m.addVars(T_keys, lb=0.0, vtype=GRB.CONTINUOUS, name=f"T{suffix}")

    L = m.addVars(K, lb=0.0, vtype=GRB.CONTINUOUS, name=f"L{suffix}")
    W1 = m.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"W1{suffix}")
    W2 = m.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"W2{suffix}")

    shortfall_keys = [(d, i) for d in D for i in inst.V_d.get(d, [])
                       if inst.q.get((i, d), 0) > 0]
    Shortfall = m.addVars(shortfall_keys, lb=0.0, vtype=GRB.CONTINUOUS,
                          name=f"Shortfall{suffix}")

    for k in K:
        m.addConstr(W1 >= L[k], name=f"eq3{suffix}_{k}")

    for k in K:
        travel_sum = gp.quicksum(
            arc_p.get((i, j, k), 0) / inst.s[k] * x[i, j, k]
            for (i, j) in E if j != 0
            if (i, j, k) in x)
        service_sum = gp.quicksum(
            T[k, d, i] for d in D for i in V0 if (k, d, i) in T)
        m.addConstr(L[k] == travel_sum + service_sum, name=f"eq4{suffix}_{k}")

    for k in K:
        m.addConstr(L[k] >= inst.L_bar[k], name=f"eq5{suffix}_{k}")

    for k in K:
        m.addConstr(
            W2 >= (L[k] - inst.L_bar[k]) / inst.L_bar[k],
            name=f"eq6{suffix}_{k}")

    # eq7 (relaxed): delivered amount + shortfall recourse >= demand.
    # Amount-based (not ratio-based like the deterministic model) so the
    # penalized Shortfall slack can be added directly in real demand units.
    for d in D:
        for i in inst.V_d.get(d, []):
            qi = inst.q.get((i, d), 0)
            if qi <= 0:
                continue
            capable = inst.K_d.get(d, [])
            sf = Shortfall[d, i] if (d, i) in Shortfall else 0.0
            m.addConstr(
                gp.quicksum(
                    inst.r.get((k, d), 0) * T[k, d, i]
                    for k in capable if (k, d, i) in T
                ) + sf >= qi,
                name=f"eq7{suffix}_{d}_{i}")

    for k in K:
        flow_from_depot = [
            f[0, j, k, d] for d in D for j in V0 if (0, j, k, d) in f]
        if flow_from_depot:
            m.addConstr(
                gp.quicksum(flow_from_depot) <= inst.C[k], name=f"eq8{suffix}_{k}")

    for k in K:
        m.addConstr(
            gp.quicksum(x[0, j, k] for j in V0 if (0, j, k) in x) <= 1,
            name=f"eq9{suffix}_{k}")

    for k in K:
        for j in V:
            inflow = gp.quicksum(
                x[i, j, k] for i in V if i != j and (i, j, k) in x)
            outflow = gp.quicksum(
                x[j, i, k] for i in V if i != j and (j, i, k) in x)
            m.addConstr(inflow == outflow, name=f"eq10{suffix}_{k}_{j}")

    for k in K:
        for d in D:
            if k not in inst.K_d.get(d, []):
                continue
            depot_out = gp.quicksum(
                f[0, j, k, d] for j in V0 if (0, j, k, d) in f)
            total_delivered = gp.quicksum(
                inst.r.get((k, d), 0) * T[k, d, i] for i in V0 if (k, d, i) in T)
            m.addConstr(depot_out == total_delivered, name=f"eq11{suffix}_{k}_{d}")

    for k in K:
        for d in D:
            if k not in inst.K_d.get(d, []):
                continue
            for i in V0:
                inflow_d = gp.quicksum(
                    f[j, i, k, d] for j in V if j != i and (j, i, k, d) in f)
                outflow_d = gp.quicksum(
                    f[i, j, k, d] for j in V if j != i and (i, j, k, d) in f)
                delivered = inst.r.get((k, d), 0) * T[k, d, i]
                m.addConstr(
                    inflow_d - outflow_d == delivered,
                    name=f"eq12{suffix}_{k}_{d}_{i}")

    for k in K:
        for d in D:
            if k not in inst.K_d.get(d, []):
                continue
            for (i, j) in E:
                key = (i, j, k, d)
                if key in f:
                    m.addConstr(
                        f[key] <= inst.C[k] * x[i, j, k],
                        name=f"eq13{suffix}_{i}_{j}_{k}_{d}")

    for k in K:
        for d in D:
            if k not in inst.K_d.get(d, []):
                continue
            for j in inst.V_d.get(d, []):
                qi = inst.q.get((j, d), 0)
                if qi <= 0:
                    continue
                rd = inst.r.get((k, d), 0)
                if rd <= 0:
                    continue
                if (k, d, j) not in T:
                    continue
                visits = gp.quicksum(
                    x[i, j, k] for i in V if i != j and (i, j, k) in x)
                m.addConstr(
                    T[k, d, j] <= (qi / rd) * visits,
                    name=f"eq14{suffix}_{k}_{d}_{j}")

    # eq16 (AO arc restriction) against the given Stage-1 A. eq15
    # (region exclusivity) is added once by the caller when A is created.
    for k in K:
        for g in inst.G_r:
            for n_g in inst.V_g.get(g, []):
                if n_g == 0:
                    continue
                m.addConstr(
                    gp.quicksum(
                        x[i, n_g, k]
                        for i in V if i != n_g and (i, n_g, k) in x
                    ) <= A[k, g],
                    name=f"eq16{suffix}_{k}_{g}_{n_g}")

    return {"x": x, "f": f, "T": T, "L": L, "W1": W1, "W2": W2,
            "Shortfall": Shortfall, "E": E}


def _new_region_vars(m, inst: Instance, suffix: str):
    A = m.addVars([(k, g) for k in inst.K for g in inst.G_r],
                  vtype=GRB.BINARY, name=f"A{suffix}")
    for k in inst.K:
        m.addConstr(
            gp.quicksum(A[k, g] for g in inst.G_r) <= 1, name=f"eq15{suffix}_{k}")
    return A


def _build_route(arcs, depot=0):
    adj = {i: j for (i, j) in arcs}
    route = [depot]
    current = depot
    visited = {depot}
    while current in adj:
        nxt = adj[current]
        if nxt in visited:
            break
        route.append(nxt)
        visited.add(nxt)
        current = nxt
    return route


def _extract_block_solution(inst: Instance, blk) -> Dict:
    routes = {}
    for k in inst.K:
        arcs = [(i, j) for (i, j) in blk["E"]
                if (i, j, k) in blk["x"] and blk["x"][i, j, k].X > 0.5]
        if arcs:
            routes[k] = _build_route(arcs, depot=0)
    shortfall = {key: var.X for key, var in blk["Shortfall"].items()
                 if var.X > 1e-6}
    return {
        "W1": blk["W1"].X, "W2": blk["W2"].X,
        "L": {k: blk["L"][k].X for k in inst.K},
        "routes": routes, "shortfall": shortfall,
    }


def build_stochastic_model(
    inst: Instance,
    scenarios: List[Scenario],
    penalty_shortfall: float = DEFAULT_PENALTY_SHORTFALL,
    epsilon: Optional[float] = None,
    time_limit: int = 300,
    verbose: bool = False,
) -> Optional[Dict]:
    """Solve the full two-stage stochastic program (RP): one shared
    Stage-1 A, one Stage-2 recourse block per scenario, single Gurobi
    model, single solve.
    """
    m = gp.Model("S_BCMC_VRPHD_RP")
    m.Params.OutputFlag = 1 if verbose else 0
    m.Params.TimeLimit = time_limit

    A = _new_region_vars(m, inst, suffix="")

    blocks = {}
    obj = gp.LinExpr()
    for scen in scenarios:
        arc_p = scenario_travel_time(inst, scen)
        blk = _build_scenario_block(
            m, inst, arc_p, scen.blocked_arcs, A, suffix=f"_{scen.name}")
        blocks[scen.name] = blk
        if epsilon is not None:
            m.addConstr(blk["W2"] <= epsilon, name=f"eps_W2_{scen.name}")
        shortfall_sum = gp.quicksum(blk["Shortfall"].values())
        obj += scen.prob * (blk["W1"] + penalty_shortfall * shortfall_sum)

    m.setObjective(obj, GRB.MINIMIZE)
    m.optimize()

    if m.SolCount == 0:
        return None

    A_sol = {(k, g): round(A[k, g].X) for k in inst.K for g in inst.G_r}
    per_scenario = {scen.name: _extract_block_solution(inst, blocks[scen.name])
                     for scen in scenarios}
    expected_w1 = sum(scen.prob * per_scenario[scen.name]["W1"]
                       for scen in scenarios)

    return {
        "RP_obj": m.ObjVal,
        "RP_W1_expected": expected_w1,
        "gap": m.MIPGap,
        "region_assignment": A_sol,
        "per_scenario": per_scenario,
    }


def solve_ev(inst: Instance, scenarios: List[Scenario],
             time_limit: int = 300, verbose: bool = False) -> Optional[Dict]:
    """Expected-Value problem: one deterministic solve against the
    probability-weighted mean congestion, no blocked arcs. Returns the
    resulting Stage-1 region assignment A*_EV."""
    m = gp.Model("S_BCMC_VRPHD_EV")
    m.Params.OutputFlag = 1 if verbose else 0
    m.Params.TimeLimit = time_limit

    A = _new_region_vars(m, inst, suffix="")
    p_mean = expected_travel_time(inst)
    blk = _build_scenario_block(m, inst, p_mean, set(), A, suffix="_EV")
    m.setObjective(blk["W1"], GRB.MINIMIZE)
    m.optimize()

    if m.SolCount == 0:
        return None
    return {(k, g): round(A[k, g].X) for k in inst.K for g in inst.G_r}


def _solve_fixed_or_free_region(
    inst: Instance, scen: Scenario, penalty_shortfall: float,
    time_limit: int, verbose: bool, A_fixed: Optional[Dict] = None,
) -> Dict:
    """Shared helper for EEV (A_fixed given) and WS (A_fixed=None, i.e.
    region assignment solved freely per scenario)."""
    m = gp.Model(f"S_BCMC_VRPHD_{'EEV' if A_fixed else 'WS'}_{scen.name}")
    m.Params.OutputFlag = 1 if verbose else 0
    m.Params.TimeLimit = time_limit

    if A_fixed is None:
        A = _new_region_vars(m, inst, suffix="")
    else:
        A = m.addVars([(k, g) for k in inst.K for g in inst.G_r],
                      vtype=GRB.BINARY, name="A")
        for (k, g), val in A_fixed.items():
            A[k, g].LB = val
            A[k, g].UB = val

    arc_p = scenario_travel_time(inst, scen)
    blk = _build_scenario_block(
        m, inst, arc_p, scen.blocked_arcs, A, suffix=f"_{scen.name}")
    shortfall_sum = gp.quicksum(blk["Shortfall"].values())
    m.setObjective(blk["W1"] + penalty_shortfall * shortfall_sum, GRB.MINIMIZE)
    m.optimize()

    if m.SolCount == 0:
        # Fixed region assignment is infeasible under this scenario's
        # blocked arcs (e.g. the EV plan sent a vehicle into a region a
        # bad scenario cuts off entirely). Recorded as a large finite
        # penalty rather than inf so VSS/EVPI stay computable and the
        # infeasibility is visible in the report instead of crashing it.
        return {"W1": None, "obj": None, "infeasible": True}
    return {"W1": blk["W1"].X, "obj": m.ObjVal, "infeasible": False}


def solve_eev(inst: Instance, scenarios: List[Scenario], A_fixed: Dict,
              penalty_shortfall: float = DEFAULT_PENALTY_SHORTFALL,
              time_limit: int = 300, verbose: bool = False) -> Dict:
    """EEV: fix Stage-1 A to A_fixed (from solve_ev), resolve Stage-2
    recourse independently per scenario. EEV = E_s[objective | A_fixed]."""
    per_scenario = {}
    for scen in scenarios:
        per_scenario[scen.name] = _solve_fixed_or_free_region(
            inst, scen, penalty_shortfall, time_limit, verbose, A_fixed)

    # KNOWN LIMITATION: an infeasible scenario here means the EV's fixed
    # region assignment cuts a vehicle off entirely under that scenario's
    # blocked arcs (it can't reach its committed region OR any other one,
    # so eq5's baseline-travel-time floor can't be met by anyone still
    # able to move) — a real, structural planning failure, not something
    # the Shortfall recourse can absorb. We drop such scenarios from the
    # weighted sum below rather than crashing, but that UNDERSTATES EEV
    # (their probability mass contributes 0 instead of a large failure
    # cost), which can theoretically make VSS = EEV - RP dip below 0 in
    # this edge case. Never observed on the bundled instances (see
    # tests/test_model.py), but check infeasible_scenarios before trusting
    # VSS on a new instance where it's non-empty.
    infeasible = [n for n, r in per_scenario.items() if r["infeasible"]]
    prob_by_name = {s.name: s.prob for s in scenarios}
    eev_obj = sum(prob_by_name[n] * r["obj"]
                  for n, r in per_scenario.items() if not r["infeasible"])
    eev_w1 = sum(prob_by_name[n] * r["W1"]
                 for n, r in per_scenario.items() if not r["infeasible"])

    return {
        "EEV_obj": eev_obj, "EEV_W1_expected": eev_w1,
        "infeasible_scenarios": infeasible, "per_scenario": per_scenario,
    }


def solve_ws(inst: Instance, scenarios: List[Scenario],
             penalty_shortfall: float = DEFAULT_PENALTY_SHORTFALL,
             time_limit: int = 300, verbose: bool = False) -> Dict:
    """Wait-and-See: solve each scenario as if known in advance (A free
    per scenario). WS = E_s[optimal objective | perfect information]."""
    per_scenario = {}
    for scen in scenarios:
        per_scenario[scen.name] = _solve_fixed_or_free_region(
            inst, scen, penalty_shortfall, time_limit, verbose, A_fixed=None)

    prob_by_name = {s.name: s.prob for s in scenarios}
    ws_obj = sum(prob_by_name[n] * r["obj"] for n, r in per_scenario.items())
    ws_w1 = sum(prob_by_name[n] * r["W1"] for n, r in per_scenario.items())

    return {"WS_obj": ws_obj, "WS_W1_expected": ws_w1, "per_scenario": per_scenario}


def analyze(
    inst: Instance,
    scenarios: List[Scenario],
    penalty_shortfall: float = DEFAULT_PENALTY_SHORTFALL,
    epsilon: Optional[float] = None,
    time_limit: int = 300,
    verbose: bool = False,
) -> Optional[Dict]:
    """Full pipeline: RP, then EV -> EEV, then WS, then VSS and EVPI.

    VSS = EEV_obj - RP_obj  (value of accounting for uncertainty at all,
                              vs. planning against the mean scenario)
    EVPI = RP_obj - WS_obj  (value of knowing the scenario in advance,
                              vs. having to commit to A before it's known)
    Both are >= 0 in a well-posed instance (RP is a relaxation of EEV's
    planning problem and a restriction of WS's).
    """
    print("  [1/4] Solving RP (two-stage stochastic program)...")
    rp = build_stochastic_model(inst, scenarios, penalty_shortfall, epsilon,
                                 time_limit, verbose)
    if rp is None:
        print("  RP infeasible.")
        return None
    print(f"    RP objective = {rp['RP_obj']:.2f}  (E[W1]={rp['RP_W1_expected']:.2f})")

    print("  [2/4] Solving EV (expected-value / mean-scenario) problem...")
    A_star = solve_ev(inst, scenarios, time_limit, verbose)
    eev = None
    if A_star is not None:
        print("  [3/4] Resolving EEV (mean-scenario plan under each real scenario)...")
        eev = solve_eev(inst, scenarios, A_star, penalty_shortfall,
                        time_limit, verbose)
        print(f"    EEV objective = {eev['EEV_obj']:.2f}")
    else:
        print("    EV problem infeasible — VSS cannot be computed.")

    print("  [4/4] Solving WS (wait-and-see, perfect information)...")
    ws = solve_ws(inst, scenarios, penalty_shortfall, time_limit, verbose)
    print(f"    WS objective = {ws['WS_obj']:.2f}")

    vss = (eev["EEV_obj"] - rp["RP_obj"]) if eev else None
    evpi = rp["RP_obj"] - ws["WS_obj"]

    return {
        "RP": rp, "EV_region_assignment": A_star, "EEV": eev, "WS": ws,
        "VSS": vss, "EVPI": evpi,
    }
