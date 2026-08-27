"""
src/model.py — BCMC-VRPHD Solver
==================================
Bi-Objective Capacitated Military Convoy VRP with Heterogeneous Demand.

Key design: T^{k,d}_i is class-specific service time (not shared across
classes) to prevent phantom demand in MCNF flow conservation.

Solver: Gurobi, via the native gurobipy API.
"""

import gurobipy as gp
from gurobipy import GRB
from typing import Dict, Optional
from src.loader import Instance


def solve_single(
    inst: Instance,
    epsilon: Optional[float] = None,
    time_limit: int = 300,
    verbose: bool = False,
) -> Optional[Dict]:
    """Solve a single epsilon-constraint iteration.

    Parameters
    ----------
    inst : Instance
    epsilon : float or None
        Upper bound on W2.  None = unconstrained (min W1 only).
    time_limit : int
        Solver time limit in seconds.
    verbose : bool

    Returns
    -------
    dict with keys W1, W2, status, routes, L, T, gap  — or None if infeasible.
    """

    V, V0, K, D = inst.V, inst.V0, inst.K, inst.D
    E = inst.E

    m = gp.Model("BCMC_VRPHD")
    m.Params.OutputFlag = 1 if verbose else 0
    m.Params.TimeLimit = time_limit

    # ── Decision variables ───────────────────────────────────

    # x[i,j,k] in {0,1}: vehicle k traverses arc (i,j)
    x = m.addVars(
        [(i, j, k) for (i, j) in E for k in K], vtype=GRB.BINARY, name="x")

    # A[k,g] in {0,1}: vehicle k assigned to region g
    A = m.addVars(
        [(k, g) for k in K for g in inst.G_r], vtype=GRB.BINARY, name="A")

    # f[i,j,k,d] >= 0: MCNF flow of class d by vehicle k on arc (i,j)
    f_keys = [
        (i, j, k, d)
        for (i, j) in E for k in K for d in D
        if k in inst.K_d.get(d, [])]
    f = m.addVars(f_keys, lb=0.0, vtype=GRB.CONTINUOUS, name="f")

    # T[k,d,i] >= 0: class-specific service time
    # CRITICAL FIX: T is indexed by (k, d, i) not (k, i)
    # This prevents phantom demand when vehicle k visits node i
    # for class d1 but node i does not need class d2.
    T_keys = [
        (k, d, i)
        for k in K for d in D if k in inst.K_d.get(d, [])
        for i in V0]
    T = m.addVars(T_keys, lb=0.0, vtype=GRB.CONTINUOUS, name="T")

    # L[k] >= 0: actual travel time of vehicle k
    L = m.addVars(K, lb=0.0, vtype=GRB.CONTINUOUS, name="L")

    # W1, W2 >= 0: min-max auxiliary objectives
    W1 = m.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name="W1")
    W2 = m.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name="W2")

    # ── Objective (eq1): min W1 ──────────────────────────────
    m.setObjective(W1, GRB.MINIMIZE)

    # ── eq3: W1 >= L_k ───────────────────────────────────────
    for k in K:
        m.addConstr(W1 >= L[k], name=f"eq3_{k}")

    # ── eq4: L_k definition (open-tour: j != 0 excludes return)
    for k in K:
        travel_sum = gp.quicksum(
            inst.p.get((i, j, k), 0) / inst.s[k] * x[i, j, k]
            for (i, j) in E if j != 0
            if (i, j, k) in x)
        # Sum T over ALL classes and ALL nodes for this vehicle
        service_sum = gp.quicksum(
            T[k, d, i]
            for d in D for i in V0
            if (k, d, i) in T)
        m.addConstr(L[k] == travel_sum + service_sum, name=f"eq4_{k}")

    # ── eq5: early arrival prohibition ───────────────────────
    for k in K:
        m.addConstr(L[k] >= inst.L_bar[k], name=f"eq5_{k}")

    # ── eq6: W2 >= (L_k - L_bar_k) / L_bar_k ────────────────
    # inst.L_bar[k] is validated > 0 by the loader, so this scalar
    # division is safe.
    for k in K:
        m.addConstr(
            W2 >= (L[k] - inst.L_bar[k]) / inst.L_bar[k],
            name=f"eq6_{k}")

    # ── epsilon-constraint on W2 ─────────────────────────────
    if epsilon is not None:
        m.addConstr(W2 <= epsilon, name="eps_W2")

    # ── eq7: demand satisfaction (split delivery) ────────────
    for d in D:
        for i in inst.V_d.get(d, []):
            qi = inst.q.get((i, d), 0)
            if qi <= 0:
                continue
            capable = inst.K_d.get(d, [])
            m.addConstr(
                gp.quicksum(
                    inst.r.get((k, d), 0) / qi * T[k, d, i]
                    for k in capable if (k, d, i) in T
                ) >= 1,
                name=f"eq7_{d}_{i}")

    # ── eq8: MCNF depot capacity ─────────────────────────────
    for k in K:
        flow_from_depot = [
            f[0, j, k, d]
            for d in D for j in V0
            if (0, j, k, d) in f]
        if flow_from_depot:
            m.addConstr(
                gp.quicksum(flow_from_depot) <= inst.C[k], name=f"eq8_{k}")

    # ── eq9: single departure ────────────────────────────────
    for k in K:
        m.addConstr(
            gp.quicksum(x[0, j, k] for j in V0 if (0, j, k) in x) <= 1,
            name=f"eq9_{k}")

    # ── eq10: flow conservation ──────────────────────────────
    for k in K:
        for j in V:
            inflow = gp.quicksum(
                x[i, j, k] for i in V if i != j and (i, j, k) in x)
            outflow = gp.quicksum(
                x[j, i, k] for i in V if i != j and (j, i, k) in x)
            m.addConstr(inflow == outflow, name=f"eq10_{k}_{j}")

    # ── eq11: MCNF depot source balance ──────────────────────
    for k in K:
        for d in D:
            if k not in inst.K_d.get(d, []):
                continue
            depot_out = gp.quicksum(
                f[0, j, k, d] for j in V0 if (0, j, k, d) in f)
            total_delivered = gp.quicksum(
                inst.r.get((k, d), 0) * T[k, d, i]
                for i in V0 if (k, d, i) in T)
            m.addConstr(depot_out == total_delivered, name=f"eq11_{k}_{d}")

    # ── eq12: MCNF node flow conservation ────────────────────
    for k in K:
        for d in D:
            if k not in inst.K_d.get(d, []):
                continue
            for i in V0:
                inflow_d = gp.quicksum(
                    f[j, i, k, d] for j in V if j != i
                    and (j, i, k, d) in f)
                outflow_d = gp.quicksum(
                    f[i, j, k, d] for j in V if j != i
                    and (i, j, k, d) in f)
                delivered = inst.r.get((k, d), 0) * T[k, d, i]
                m.addConstr(
                    inflow_d - outflow_d == delivered,
                    name=f"eq12_{k}_{d}_{i}")

    # ── eq13: MCNF flow-routing coupling ─────────────────────
    for k in K:
        for d in D:
            if k not in inst.K_d.get(d, []):
                continue
            for (i, j) in E:
                key = (i, j, k, d)
                if key in f:
                    m.addConstr(
                        f[key] <= inst.C[k] * x[i, j, k],
                        name=f"eq13_{i}_{j}_{k}_{d}")

    # ── eq14: route-service link ─────────────────────────────
    # Only for (k, d, j) where node j demands class d from vehicle k
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
                    x[i, j, k]
                    for i in V if i != j and (i, j, k) in x)
                m.addConstr(
                    T[k, d, j] <= (qi / rd) * visits,
                    name=f"eq14_{k}_{d}_{j}")

    # ── eq15: region exclusivity ─────────────────────────────
    for k in K:
        m.addConstr(
            gp.quicksum(A[k, g] for g in inst.G_r) <= 1,
            name=f"eq15_{k}")

    # ── eq16: AO arc restriction ─────────────────────────────
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
                    name=f"eq16_{k}_{g}_{n_g}")

    # ── Solve ────────────────────────────────────────────────
    m.optimize()

    if m.SolCount == 0:
        return None

    # ── Extract solution ─────────────────────────────────────
    sol_W1 = W1.X
    sol_W2 = W2.X
    sol_L = {k: L[k].X for k in K}

    # Aggregate T per vehicle per node (sum over classes)
    sol_T = {}
    for k in K:
        for i in V0:
            total_t = sum(
                T[k, d, i].X
                for d in D if (k, d, i) in T)
            sol_T[(k, i)] = total_t

    routes = {}
    for k in K:
        arcs = [(i, j) for (i, j) in E
                if (i, j, k) in x and x[i, j, k].X > 0.5]
        if arcs:
            routes[k] = _build_route(arcs, depot=0)

    status = "Optimal" if m.Status == GRB.OPTIMAL else "Feasible"
    gap = m.MIPGap

    return {
        "W1": sol_W1, "W2": sol_W2, "status": status,
        "routes": routes, "L": sol_L, "T": sol_T,
        "gap": gap,
    }


def _build_route(arcs, depot=0):
    """Build ordered route from arc list."""
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


def solve_pareto(inst, n_points=10, time_limit=300, verbose=False):
    """Generate Pareto frontier via epsilon-constraint on W2."""

    print(f"  [1/{n_points+1}] Solving min W1 (unconstrained)...")
    sol_ub = solve_single(inst, epsilon=None, time_limit=time_limit,
                          verbose=verbose)
    if sol_ub is None:
        print("  ✗ Infeasible.")
        return []

    W2_max = sol_ub["W2"]
    print(f"    W1*={sol_ub['W1']:.2f}, W2={W2_max:.4f}")

    # Find W2_min via binary search
    W2_min = 0.0
    sol_lb = solve_single(inst, epsilon=0.0, time_limit=time_limit,
                          verbose=verbose)
    if sol_lb is not None:
        W2_min = 0.0
    else:
        lo, hi = 0.0, W2_max
        for _ in range(12):
            mid = (lo + hi) / 2
            sol_test = solve_single(inst, epsilon=mid,
                                    time_limit=max(30, time_limit // 3))
            if sol_test is not None:
                hi = mid
            else:
                lo = mid
        W2_min = hi

    print(f"    W2 range: [{W2_min:.4f}, {W2_max:.4f}]")

    frontier = [sol_ub]
    if n_points > 1 and W2_max > W2_min + 1e-6:
        epsilons = [
            W2_max - i * (W2_max - W2_min) / (n_points - 1)
            for i in range(1, n_points)]
        for idx, eps in enumerate(epsilons):
            print(f"  [{idx+2}/{n_points+1}] eps={eps:.4f}...")
            sol = solve_single(inst, epsilon=eps, time_limit=time_limit,
                               verbose=verbose)
            if sol is not None:
                frontier.append(sol)
                print(f"    W1={sol['W1']:.2f}, W2={sol['W2']:.4f}")

    frontier.sort(key=lambda s: s["W1"])
    if len(frontier) >= 3:
        _mark_knee(frontier)
    return frontier


def _mark_knee(frontier):
    """Mark knee point via max perpendicular distance."""
    pts = [(s["W1"], s["W2"]) for s in frontier]
    x1, y1 = pts[0]
    x2, y2 = pts[-1]
    max_dist, knee_idx = -1, 0
    for idx, (px, py) in enumerate(pts):
        num = abs((y2 - y1) * px - (x2 - x1) * py + x2 * y1 - y2 * x1)
        den = ((y2 - y1)**2 + (x2 - x1)**2)**0.5
        if den > 0:
            dist = num / den
            if dist > max_dist:
                max_dist = dist
                knee_idx = idx
    for i, sol in enumerate(frontier):
        sol["knee"] = (i == knee_idx)
