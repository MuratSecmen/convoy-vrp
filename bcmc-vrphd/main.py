"""
main.py — BCMC-VRPHD Runner
==============================
Usage:
    python main.py --instance data/instances/small_n5_k3.xlsx
    python main.py --all --n_points 10 --time_limit 300
"""

import argparse
import os
import glob
from src.loader import load_instance
from src.model import solve_pareto
from src.export import export_results


def run_instance(path, n_points, time_limit, verbose):
    """Run a single instance."""
    print(f"\n{'='*65}")
    inst = load_instance(path)
    print(f"  Instance: {inst.name}")
    print(f"{'='*65}")
    print(f"  Nodes: {len(inst.V0)}, Vehicles: {len(inst.K)}")
    print(f"  Supply classes: {inst.D}")
    print(f"  AO regions: {inst.G_r}")
    print(f"  Observable: {inst.K_obs}, Unobservable: {inst.K_unobs}")

    frontier = solve_pareto(
        inst, n_points=n_points,
        time_limit=time_limit, verbose=verbose)

    if frontier:
        print(f"\n  {len(frontier)} Pareto points found.")
        export_results(frontier, inst.name)
        knee = [s for s in frontier if s.get("knee")]
        if knee:
            k = knee[0]
            print(f"  Knee point: W1={k['W1']:.2f}, W2={k['W2']:.4f}")
    else:
        print("\n  No feasible solution found.")


def main():
    parser = argparse.ArgumentParser(
        description="BCMC-VRPHD Bi-Objective Military Convoy VRP Solver")
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
        paths = sorted(glob.glob("data/instances/*.xlsx"))
        if not paths:
            print("No instances found. Run: python data/generate_instances.py")
            return
        for p in paths:
            run_instance(p, args.n_points, args.time_limit, args.verbose)
    elif args.instance:
        run_instance(args.instance, args.n_points, args.time_limit, args.verbose)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
