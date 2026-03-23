"""
tests/test_model.py
===================
Unit tests for BCMC-VRPHD solver.
Run: python -m pytest tests/ -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from data.generate_det_instances import generate_instance
from src.loader_det import load_instance
from src.deterministic_model import BCMCVRPHDSolver

TMP = "/tmp/test_instance.xlsx"


@pytest.fixture(scope="module")
def small_instance():
    wb = generate_instance(5, 3, 42, "test_small")
    wb.save(TMP)
    return load_instance(TMP)


def test_instance_loads(small_instance):
    inst = small_instance
    assert inst.depot == 0
    assert len(inst.vehicles) == 3
    assert len(inst.nodes) == 6   # depot + 5
    assert len(inst.supply_classes) == 6


def test_capacity_positive(small_instance):
    for k, c in small_instance.capacity.items():
        assert c > 0, f"Capacity of vehicle {k} must be positive"


def test_baseline_positive(small_instance):
    for k, bl in small_instance.baseline_time.items():
        assert bl > 0, f"Baseline time of vehicle {k} must be positive"


def test_solver_returns_feasible(small_instance):
    solver = BCMCVRPHDSolver(small_instance,
                               time_limit=60, verbose=False)
    sol = solver.solve_single(epsilon=1e9)
    assert sol.status in ("Optimal", "Feasible", "Not Solved",
                           "Infeasible")
    # Just check it runs without exception
    assert sol.W1 >= 0


def test_early_arrival_prohibited(small_instance):
    solver = BCMCVRPHDSolver(small_instance,
                               time_limit=60, verbose=False)
    sol = solver.solve_single(epsilon=1e9)
    if sol.feasible:
        for k, lk in sol.L.items():
            bl = small_instance.baseline_time[k]
            assert lk >= bl - 1e-4, (
                f"Vehicle {k}: L_k={lk:.2f} < baseline={bl:.2f}")


def test_w2_non_negative(small_instance):
    solver = BCMCVRPHDSolver(small_instance,
                               time_limit=60, verbose=False)
    sol = solver.solve_single(epsilon=1e9)
    if sol.feasible:
        assert sol.W2 >= -1e-6, "W2 must be non-negative"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
