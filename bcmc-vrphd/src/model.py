"""
BCMC-VRPHD Solver
==================
Bi-Objective Capacitated Military Convoy VRP with Heterogeneous Demand.
T^{k,d}_i: class-specific service time to prevent phantom MCNF demand.
"""
import pulp
from typing import Dict, List, Optional, Tuple
from src.loader import Instance


def solve_single(inst, epsilon=None, time_limit=300, verbose=False):
    V, V0, K, D = inst.V, inst.V0, inst.K, inst.D
    E = inst.E
    prob = pulp.LpProblem("BCMC_VRPHD", pulp.LpMinimize)

    x = pulp.LpVariable.dicts("x", [(i,j,k) for (i,j) in E for k in K], cat="Binary")
    A = pulp.LpVariable.dicts("A", [(k,g) for k in K for g in inst.G_r], cat="Binary")

    f = {}
    for (i,j) in E:
        for k in K:
            for d in D:
                if k in inst.K_d.get(d, []):
                    f[(i,j,k,d)] = pulp.LpVariable(f"f_{i}_{j}_{k}_{d}", lowBound=0)

    T = {}
    for k in K:
        for d in D:
            if k in inst.K_d.get(d, []):
                for i in V0:
                    T[(k,d,i)] = pulp.LpVariable(f"T_{k}_{d}_{i}", lowBound=0)

    L = pulp.LpVariable.dicts("L", K, lowBound=0)
    W1 = pulp.LpVariable("W1", lowBound=0)
    W2 = pulp.LpVariable("W2", lowBound=0)

    prob += W1
    for k in K:
        prob += W1 >= L[k], f"eq3_{k}"

    for k in K:
        travel = pulp.lpSum(inst.p.get((i,j,k),0)/inst.s[k]*x[(i,j,k)] for (i,j) in E if j!=0)
        service = pulp.lpSum(T[(k,d,i)] for d in D for i in V0 if (k,d,i) in T)
        prob += L[k] == travel + service, f"eq4_{k}"

    for k in K:
        prob += L[k] >= inst.L_bar[k], f"eq5_{k}"

    for k in K:
        prob += W2 >= (L[k] - inst.L_bar[k]) / inst.L_bar[k], f"eq6_{k}"

    if epsilon is not None:
        prob += W2 <= epsilon, "eps_W2"

    for d in D:
        for i in inst.V_d.get(d, []):
            qi = inst.q.get((i,d), 0)
            if qi <= 0: continue
            prob += (pulp.lpSum(inst.r.get((k,d),0)/qi * T[(k,d,i)]
                     for k in inst.K_d.get(d,[]) if (k,d,i) in T) >= 1, f"eq7_{d}_{i}")

    for k in K:
        fl = [f[(0,j,k,d)] for d in D for j in V0 if (0,j,k,d) in f]
        if fl: prob += pulp.lpSum(fl) <= inst.C[k], f"eq8_{k}"

    for k in K:
        prob += pulp.lpSum(x[(0,j,k)] for j in V0 if (0,j,k) in x) <= 1, f"eq9_{k}"

    for k in K:
        for j in V:
            prob += (pulp.lpSum(x[(i,j,k)] for i in V if i!=j and (i,j,k) in x) ==
                     pulp.lpSum(x[(j,i,k)] for i in V if i!=j and (j,i,k) in x), f"eq10_{k}_{j}")

    for k in K:
        for d in D:
            if k not in inst.K_d.get(d,[]): continue
            depot_out = pulp.lpSum(f[(0,j,k,d)] for j in V0 if (0,j,k,d) in f)
            total_del = pulp.lpSum(inst.r.get((k,d),0)*T[(k,d,i)] for i in V0 if (k,d,i) in T)
            prob += depot_out == total_del, f"eq11_{k}_{d}"

    for k in K:
        for d in D:
            if k not in inst.K_d.get(d,[]): continue
            for i in V0:
                inf_d = pulp.lpSum(f[(j,i,k,d)] for j in V if j!=i and (j,i,k,d) in f)
                outf_d = pulp.lpSum(f[(i,j,k,d)] for j in V if j!=i and (i,j,k,d) in f)
                tval = T.get((k,d,i), 0)
                if isinstance(tval, (int,float)):
                    prob += inf_d == outf_d, f"eq12_{k}_{d}_{i}"
                else:
                    prob += inf_d - outf_d == inst.r.get((k,d),0)*tval, f"eq12_{k}_{d}_{i}"

    for k in K:
        for d in D:
            if k not in inst.K_d.get(d,[]): continue
            for (i,j) in E:
                if (i,j,k,d) in f:
                    prob += f[(i,j,k,d)] <= inst.C[k]*x[(i,j,k)], f"eq13_{i}_{j}_{k}_{d}"

    for k in K:
        for d in D:
            if k not in inst.K_d.get(d,[]): continue
            for j in inst.V_d.get(d, []):
                qi = inst.q.get((j,d),0)
                rd = inst.r.get((k,d),0)
                if qi<=0 or rd<=0 or (k,d,j) not in T: continue
                visits = pulp.lpSum(x[(i,j,k)]*qi/rd for i in V if i!=j and (i,j,k) in x)
                prob += visits >= T[(k,d,j)], f"eq14_{k}_{d}_{j}"

    for k in K:
        prob += pulp.lpSum(A[(k,g)] for g in inst.G_r) <= 1, f"eq15_{k}"

    for k in K:
        for g in inst.G_r:
            for n_g in inst.V_g.get(g, []):
                if n_g == 0: continue
                prob += (pulp.lpSum(x[(i,n_g,k)] for i in V if i!=n_g and (i,n_g,k) in x)
                         <= A[(k,g)], f"eq16_{k}_{g}_{n_g}")

    solver = pulp.PULP_CBC_CMD(timeLimit=time_limit, msg=1 if verbose else 0)
    prob.solve(solver)
    status = pulp.LpStatus[prob.status]
    if status not in ("Optimal", "Feasible"):
        return None

    sol_W1 = pulp.value(W1)
    sol_W2 = pulp.value(W2)
    sol_L = {k: pulp.value(L[k]) for k in K}
    sol_T = {}
    for k in K:
        for i in V0:
            sol_T[(k,i)] = sum(pulp.value(T[(k,d,i)]) or 0 for d in D if (k,d,i) in T)

    routes = {}
    for k in K:
        arcs = [(i,j) for (i,j) in E if (i,j,k) in x and (pulp.value(x[(i,j,k)]) or 0) > 0.5]
        if arcs:
            routes[k] = _build_route(arcs)
    return {"W1": sol_W1, "W2": sol_W2, "status": status, "routes": routes, "L": sol_L, "T": sol_T}


def _build_route(arcs, depot=0):
    adj = {i: j for (i, j) in arcs}
    route, current, visited = [depot], depot, {depot}
    while current in adj:
        nxt = adj[current]
        if nxt in visited: break
        route.append(nxt)
        visited.add(nxt)
        current = nxt
    return route


def solve_pareto(inst, n_points=10, time_limit=300, verbose=False):
    print(f"  [1/{n_points+1}] Solving min W1 (unconstrained)...")
    sol_ub = solve_single(inst, epsilon=None, time_limit=time_limit, verbose=verbose)
    if sol_ub is None:
        print("  X Infeasible."); return []
    W2_max = sol_ub["W2"]
    print(f"    W1*={sol_ub['W1']:.2f}, W2={W2_max:.4f}")

    W2_min = 0.0
    if solve_single(inst, epsilon=0.0, time_limit=max(30, time_limit//3)) is None:
        lo, hi = 0.0, W2_max
        for _ in range(12):
            mid = (lo+hi)/2
            if solve_single(inst, epsilon=mid, time_limit=max(30, time_limit//3)):
                hi = mid
            else: lo = mid
        W2_min = hi
    print(f"    W2 range: [{W2_min:.4f}, {W2_max:.4f}]")

    frontier = [sol_ub]
    if n_points > 1 and W2_max > W2_min + 1e-6:
        for idx in range(1, n_points):
            eps = W2_max - idx*(W2_max - W2_min)/(n_points - 1)
            print(f"  [{idx+1}/{n_points+1}] eps={eps:.4f}...")
            sol = solve_single(inst, epsilon=eps, time_limit=time_limit, verbose=verbose)
            if sol:
                frontier.append(sol)
                print(f"    W1={sol['W1']:.2f}, W2={sol['W2']:.4f}")
    frontier.sort(key=lambda s: s["W1"])
    if len(frontier) >= 3: _mark_knee(frontier)
    return frontier


def _mark_knee(frontier):
    pts = [(s["W1"], s["W2"]) for s in frontier]
    x1,y1 = pts[0]; x2,y2 = pts[-1]
    max_dist, knee_idx = -1, 0
    for idx, (px,py) in enumerate(pts):
        den = ((y2-y1)**2+(x2-x1)**2)**0.5
        if den > 0:
            dist = abs((y2-y1)*px-(x2-x1)*py+x2*y1-y2*x1)/den
            if dist > max_dist: max_dist, knee_idx = dist, idx
    for i, sol in enumerate(frontier):
        sol["knee"] = (i == knee_idx)
