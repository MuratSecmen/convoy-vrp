"""
main.py — BCMC-VRPHD / S-BCMC-VRPHD Unified Runner
====================================================
Deterministik ve stokastik modelleri tek noktadan çalıştırır.

Kullanım:
    # Deterministik
    python main.py --mode det --instance data/instances/small_n5_k3.xlsx

    # Stokastik
    python main.py --mode stoch --instance data/instances/small_stoch_n5_k3.xlsx

    # Tüm deterministik instancelar
    python main.py --mode det --all

    # Tüm stokastik instancelar
    python main.py --mode stoch --all
"""

import argparse
import os
import sys
import json


def run_deterministic(instance_path, n_points=10,
                      time_limit=300, verbose=False):
    from src.loader_det import load_instance
    from src.deterministic_model import BCMCVRPHDSolver
    from src.export import export_results

    print(f"\n{'='*65}")
    print(f"  BCMC-VRPHD  |  Deterministik  |  {instance_path}")
    print(f"{'='*65}")

    inst     = load_instance(instance_path)
    solver   = BCMCVRPHDSolver(inst, time_limit=time_limit,
                                verbose=verbose)
    print(f"\n  Pareto cephesi izleniyor ({n_points} nokta)...\n")
    frontier = solver.pareto_frontier(n_points=n_points)
    feasible = [s for s in frontier if s.feasible]
    print(f"\n  {len(feasible)} uygun Pareto noktası bulundu.")

    os.makedirs("results", exist_ok=True)
    out = f"results/{inst.name}_det_pareto.xlsx"
    export_results(feasible, out_path=out)
    print(f"\n  Sonuç: {out}")
    print(f"{'='*65}\n")


def run_stochastic(instance_path, n_points=8,
                   time_limit=600, verbose=False):
    from src.loader_stoch import load_instance
    from src.stochastic_model import SBCMCVRPHDSolver

    print(f"\n{'='*65}")
    print(f"  S-BCMC-VRPHD  |  Stokastik  |  {instance_path}")
    print(f"{'='*65}")

    inst   = load_instance(instance_path)
    print(f"  Düğüm: {len(inst.nodes)}  "
          f"Araç: {len(inst.vehicles)}  "
          f"Senaryo: {len(inst.scenarios)}")

    solver   = SBCMCVRPHDSolver(inst, time_limit=time_limit,
                                  verbose=verbose)
    print(f"\n  Pareto cephesi izleniyor ({n_points} nokta)...\n")
    frontier = solver.pareto_frontier(n_points=n_points)
    feasible = [s for s in frontier if s.feasible]
    print(f"\n  {len(feasible)} uygun Pareto noktası bulundu.")

    os.makedirs("results", exist_ok=True)
    out = f"results/{inst.name}_stoch_pareto.json"
    data = [{"W1": s.W1, "W2": s.W2, "epsilon": s.epsilon,
             "status": s.status, "solve_time": s.solve_time}
            for s in feasible]
    with open(out, "w") as f:
        json.dump(data, f, indent=2)

    vss = solver.compute_vss()
    print(f"  VSS = {vss:.4f}")
    print(f"  Sonuç: {out}")
    print(f"{'='*65}\n")


def main():
    p = argparse.ArgumentParser(
        description="BCMC-VRPHD / S-BCMC-VRPHD Solver")
    p.add_argument("--mode", choices=["det", "stoch"],
                   default="det",
                   help="det = deterministik, stoch = stokastik")
    p.add_argument("--instance",
                   default="data/instances/small_n5_k3.xlsx")
    p.add_argument("--n_points",   type=int, default=10)
    p.add_argument("--time_limit", type=int, default=300)
    p.add_argument("--verbose",    action="store_true")
    p.add_argument("--all",        action="store_true",
                   help="Klasördeki tüm uygun instanceları çalıştır")
    args = p.parse_args()

    folder = "data/instances"

    if args.all:
        if args.mode == "det":
            files = [f for f in os.listdir(folder)
                     if f.endswith(".xlsx") and "stoch" not in f]
        else:
            files = [f for f in os.listdir(folder)
                     if f.endswith(".xlsx") and "stoch" in f]

        for fname in sorted(files):
            path = os.path.join(folder, fname)
            if args.mode == "det":
                run_deterministic(path, args.n_points,
                                  args.time_limit, args.verbose)
            else:
                run_stochastic(path, args.n_points,
                               args.time_limit, args.verbose)
    else:
        if args.mode == "det":
            run_deterministic(args.instance, args.n_points,
                              args.time_limit, args.verbose)
        else:
            run_stochastic(args.instance, args.n_points,
                           args.time_limit, args.verbose)


if __name__ == "__main__":
    main()
