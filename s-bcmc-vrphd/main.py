"""
main.py — S-BCMC-VRPHD Runner
=================================
Usage:
    python main.py --instance ../bcmc-vrphd/data/instances/small_n5_k3.xlsx
"""

import argparse
from src.loader import load_instance
from src.scenarios import generate_scenarios
from src.model import analyze, DEFAULT_PENALTY_SHORTFALL
from src.export import export_results


def main():
    parser = argparse.ArgumentParser(
        description="S-BCMC-VRPHD Two-Stage Stochastic Military Convoy VRP Solver")
    parser.add_argument("--instance", type=str, required=True,
                        help="Path to .xlsx base instance file "
                             "(same schema as bcmc-vrphd, e.g. "
                             "../bcmc-vrphd/data/instances/small_n5_k3.xlsx)")
    parser.add_argument("--epsilon", type=float, default=None,
                        help="Upper bound on W2 (plan deviation), enforced "
                             "in every scenario. Default: unconstrained.")
    parser.add_argument("--penalty_shortfall", type=float,
                        default=DEFAULT_PENALTY_SHORTFALL,
                        help="Shadow cost per unit of undeliverable demand "
                             "under a disruption scenario "
                             f"(default {DEFAULT_PENALTY_SHORTFALL}).")
    parser.add_argument("--time_limit", type=int, default=300,
                        help="Per-solve MIP time limit in seconds "
                             "(RP, EV, and each EEV/WS scenario solve).")
    parser.add_argument("--verbose", action="store_true",
                        help="Show solver output")
    args = parser.parse_args()

    print("=" * 65)
    print("  S-BCMC-VRPHD  --  Two-Stage Stochastic Convoy Routing")
    print("=" * 65)

    inst = load_instance(args.instance)
    scenarios = generate_scenarios(inst)

    print(f"  Instance: {inst.name}")
    print(f"  Nodes: {len(inst.V0)}, Vehicles: {len(inst.K)}, "
          f"Regions: {inst.G_r}")
    print(f"  Scenarios: {[s.name for s in scenarios]}")
    print(f"  Epsilon (W2 bound): {args.epsilon}")
    print(f"  Shortfall penalty: {args.penalty_shortfall}")

    result = analyze(
        inst, scenarios,
        penalty_shortfall=args.penalty_shortfall,
        epsilon=args.epsilon,
        time_limit=args.time_limit,
        verbose=args.verbose,
    )

    if result is None:
        print("\n  No feasible solution found (RP infeasible).")
        return

    print(f"\n  RP objective : {result['RP']['RP_obj']:,.2f}")
    if result["VSS"] is not None:
        print(f"  VSS          : {result['VSS']:,.2f}")
    print(f"  EVPI         : {result['EVPI']:,.2f}")

    export_results(result, scenarios, inst.name)
    print("\n  Done.\n")


if __name__ == "__main__":
    main()
