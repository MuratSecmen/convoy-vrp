"""
BCMC-VRPHD Test Suite
======================
Tests instance generation, loading, and solver correctness.
"""

import pytest
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.generate_instances import generate_instance
from src.loader import load_instance, Instance
from src.model import solve_single


@pytest.fixture(scope="module")
def small_instance_path(tmp_path_factory):
    """Generate and save a small test instance."""
    import pandas as pd
    tmp = tmp_path_factory.mktemp("data")
    sheets = generate_instance(n_nodes=5, n_vehicles=3, seed=42)
    path = str(tmp / "test_small.xlsx")
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, sheet_name=name, index=False)
    return path


@pytest.fixture(scope="module")
def inst(small_instance_path):
    """Load the small test instance."""
    return load_instance(small_instance_path)


class TestInstanceGeneration:
    def test_sheets_present(self):
        sheets = generate_instance(n_nodes=5, n_vehicles=3, seed=42)
        expected = {"Nodes", "Vehicles", "TravelTime", "Demand",
                    "ServiceRate", "Baseline", "Regions"}
        assert set(sheets.keys()) == expected

    def test_node_count(self):
        sheets = generate_instance(n_nodes=5, n_vehicles=3, seed=42)
        assert len(sheets["Nodes"]) == 6  # 5 delivery + 1 depot

    def test_vehicle_count(self):
        sheets = generate_instance(n_nodes=5, n_vehicles=3, seed=42)
        assert len(sheets["Vehicles"]) == 3

    def test_depot_is_node_zero(self):
        sheets = generate_instance(n_nodes=5, n_vehicles=3, seed=42)
        depot = sheets["Nodes"][sheets["Nodes"]["node_id"] == 0]
        assert len(depot) == 1
        assert depot.iloc[0]["type"] == "depot"


class TestLoader:
    def test_sets(self, inst):
        assert 0 in inst.V
        assert 0 not in inst.V0
        assert len(inst.V0) == 5
        assert len(inst.K) == 3

    def test_partition(self, inst):
        assert set(inst.K_obs + inst.K_unobs) == set(inst.K)
        assert len(set(inst.K_obs) & set(inst.K_unobs)) == 0

    def test_travel_times_positive(self, inst):
        for key, val in inst.p.items():
            assert val > 0, f"Non-positive travel time at {key}"

    def test_demand_nodes_in_V0(self, inst):
        for d, nodes in inst.V_d.items():
            for n in nodes:
                assert n in inst.V0, f"Demand node {n} not in V0"

    def test_baseline_all_vehicles(self, inst):
        for k in inst.K:
            assert k in inst.L_bar, f"Baseline missing for vehicle {k}"
            assert inst.L_bar[k] > 0


class TestSolver:
    def test_feasible(self, inst):
        """Test that the small instance is feasible."""
        sol = solve_single(inst, epsilon=None, time_limit=120)
        assert sol is not None, "Solver returned None (infeasible)"
        assert sol["status"] in ("Optimal", "Feasible")

    def test_W1_positive(self, inst):
        sol = solve_single(inst, epsilon=None, time_limit=120)
        if sol is not None:
            assert sol["W1"] > 0

    def test_W2_nonnegative(self, inst):
        sol = solve_single(inst, epsilon=None, time_limit=120)
        if sol is not None:
            assert sol["W2"] >= -1e-6  # allow tiny numerical noise

    def test_early_arrival_respected(self, inst):
        """L_k ≥ L_bar_k for all vehicles (eq 5)."""
        sol = solve_single(inst, epsilon=None, time_limit=120)
        if sol is not None:
            for k in inst.K:
                lk = sol["L"].get(k, 0) or 0
                assert lk >= inst.L_bar[k] - 1e-4, \
                    f"Vehicle {k}: L={lk} < L_bar={inst.L_bar[k]}"

    def test_epsilon_tightens(self, inst):
        """Tighter ε should yield larger or equal W1."""
        sol_free = solve_single(inst, epsilon=None, time_limit=120)
        if sol_free is None:
            pytest.skip("Base problem infeasible")
        eps = sol_free["W2"] * 0.5
        sol_tight = solve_single(inst, epsilon=eps, time_limit=120)
        if sol_tight is not None:
            # Tighter W2 bound → W1 should not improve
            assert sol_tight["W1"] >= sol_free["W1"] - 1e-4

    def test_routes_start_from_depot(self, inst):
        """All routes should start from vertex 0."""
        sol = solve_single(inst, epsilon=None, time_limit=120)
        if sol is not None:
            for k, route in sol.get("routes", {}).items():
                assert route[0] == 0, \
                    f"Vehicle {k} route doesn't start from depot: {route}"
