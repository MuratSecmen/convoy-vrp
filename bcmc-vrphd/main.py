"""
BCMC-VRPHD Main Runner
=======================
Usage:
    python main.py --instance data/instances/small_n5_k3.xlsx --n_points 10
    python main.py --all --n_points 10 --time_limit 300
"""

import argparse
from pathlib import Path
from src.loader import load_instance
from src.model import solve_pareto
from src.export import export_results


def run_instance(filepath: str, n_points: int, time_limit: int,
                 verbose: bool):
    name = Path(filepath).stem
    print(f"\n{'='*60}")
    print(f"  Instance: {name}")
    print(f"{'='*60}")

    inst = load_instance(filepath)
    print(f"  Nodes: {inst.n_nodes}, Vehicles: {inst.n_vehicles}")
    print(f"  Supply classes: {inst.D}")
    print(f"  AO regions: {inst.G_r}")
    print(f"  Observable: {inst.K_obs}, Unobservable: {inst.K_unobs}")

    frontier = solve_pareto(inst, n_points=n_points,
                            time_limit=time_limit, verbose=verbose)

    if frontier:
        export_results(frontier, name)
        print(f"\n  Pareto frontier: {len(frontier)} points")
        for sol in frontier:
            knee = " ★" if sol.get("knee") else ""
            print(f"    W1={sol['W1']:.2f}  W2={sol['W2']:.4f}"
                  f"  [{sol['status']}]{knee}")
    else:
        print("  ✗ No feasible solution found.")


def main():
    parser = argparse.ArgumentParser(
        description="BCMC-VRPHD: Bi-Objective Capacitated Military "
                    "Convoy VRP with Heterogeneous Demand")
    parser.add_argument("--instance", type=str,
                        help="Path to .xlsx instance file")
    parser.add_argument("--all", action="store_true",
                        help="Run all instances in data/instances/")
    parser.add_argument("--n_points", type=int, default=10,
                        help="Number of Pareto frontier points")
    parser.add_argument("--time_limit", type=int, default=300,
                        help="MIP solver time limit per point (seconds)")
    parser.add_argument("--verbose", action="store_true",
                        help="Show CBC solver output")
    args = parser.parse_args()

    if args.all:
        inst_dir = Path("data/instances")
        files = sorted(inst_dir.glob("*.xlsx"))
        if not files:
            print("No instances found. Run: python data/generate_instances.py")
            return
        for fp in files:
            run_instance(str(fp), args.n_points, args.time_limit,
                         args.verbose)
    elif args.instance:
        run_instance(args.instance, args.n_points, args.time_limit,
                     args.verbose)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
