"""tests/test_stochastic.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from data.generate_stoch_instances import generate
from src.loader_stoch import load_instance

TMP = "/tmp/test_stoch.xlsx"

@pytest.fixture(scope="module")
def inst():
    wb = generate(5, 3, 42, "test")
    wb.save(TMP)
    return load_instance(TMP)

def test_loads(inst):
    assert inst.depot == 0
    assert len(inst.scenarios) == 6
    assert len(inst.vehicles) == 3

def test_probabilities_sum_to_one(inst):
    total = sum(s.probability for s in inst.scenarios)
    assert abs(total - 1.0) < 1e-2, f"Sum={total}"

def test_scenario_labels(inst):
    labels = [s.label for s in inst.scenarios]
    assert "Nominal" in labels

def test_baseline_positive(inst):
    for k, bl in inst.baseline_time.items():
        assert bl > 0

def test_kappa_range(inst):
    for s in inst.scenarios:
        assert 0.0 <= s.kappa <= 1.0

def test_delta_ge_one(inst):
    for s in inst.scenarios:
        assert s.delta >= 1.0

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
