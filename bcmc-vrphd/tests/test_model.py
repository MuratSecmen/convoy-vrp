"""
tests/test_model.py — BCMC-VRPHD Model Tests
===============================================
6 tests covering feasibility, constraint validity, and Pareto structure.
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.loader import load_instance
from src.model import solve_single, solve_pareto


INST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "data", "instances")


@pytest.fixture
def inst():
    """Load small instance for testing."""
    path = os.path.join(INST_DIR, "small_n5_k3.xlsx")
    if not os.path.exists(path):
        pytest.skip("Instance not generated yet")
    return load_instance(path)


class TestSolveSingle:

    def test_feasibility(self, inst):
        """Unconstrained problem should be feasible."""
        sol = solve_single(inst, epsilon=None, time_limit=120)
        assert sol is not None, "Base problem is infeasible"
        assert sol["W1"] > 0
        assert sol["W2"] >= 0

    def test_w1_dominates_lk(self, inst):
        """W1 >= max L_k."""
        sol = solve_single(inst, epsilon=None, time_limit=120)
        if sol is None:
            pytest.skip("Infeasible")
        for k in inst.K:
            lk = sol["L"].get(k, 0) or 0
            assert sol["W1"] >= lk - 1e-4, \
                f"W1={sol['W1']} < L_{k}={lk}"

    def test_early_arrival(self, inst):
        """L_k >= L_bar_k (eq5)."""
        sol = solve_single(inst, epsilon=None, time_limit=120)
        if sol is None:
            pytest.skip("Infeasible")
        for k in inst.K:
            lk = sol["L"].get(k, 0) or 0
            assert lk >= inst.L_bar[k] - 1e-4, \
                f"Vehicle {k}: L={lk} < L_bar={inst.L_bar[k]}"

    def test_epsilon_tightens(self, inst):
        """Tighter epsilon -> W1 should not improve."""
        sol_free = solve_single(inst, epsilon=None, time_limit=120)
        if sol_free is None:
            pytest.skip("Base infeasible")
        eps = sol_free["W2"] * 0.5
        sol_tight = solve_single(inst, epsilon=eps, time_limit=120)
        if sol_tight is not None:
            assert sol_tight["W1"] >= sol_free["W1"] - 1e-4

    def test_routes_start_from_depot(self, inst):
        """All routes should start from depot (node 0)."""
        sol = solve_single(inst, epsilon=None, time_limit=120)
        if sol is None:
            pytest.skip("Infeasible")
        for k, route in sol.get("routes", {}).items():
            assert route[0] == 0, \
                f"Vehicle {k} route doesn't start from depot: {route}"

    def test_pareto_ordering(self, inst):
        """Pareto frontier should be sorted by W1."""
        frontier = solve_pareto(inst, n_points=3, time_limit=60)
        if len(frontier) < 2:
            pytest.skip("Too few Pareto points")
        w1_vals = [s["W1"] for s in frontier]
        for i in range(len(w1_vals) - 1):
            assert w1_vals[i] <= w1_vals[i + 1] + 1e-4
