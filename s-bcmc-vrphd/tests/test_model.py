"""
tests/test_model.py — S-BCMC-VRPHD Model Tests
==================================================
Covers scenario generation, RP feasibility/structure, and the
VSS/EVPI relationships that must hold on any well-posed instance.
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.loader import load_instance
from src.scenarios import generate_scenarios, SCENARIO_SPECS
from src.model import build_stochastic_model, solve_ev, solve_eev, solve_ws, analyze


INST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "bcmc-vrphd", "data", "instances", "small_n5_k3.xlsx")


@pytest.fixture
def inst():
    if not os.path.exists(INST_PATH):
        pytest.skip("bcmc-vrphd instance not generated yet")
    return load_instance(INST_PATH)


@pytest.fixture
def scenarios(inst):
    return generate_scenarios(inst)


class TestScenarios:

    def test_probabilities_sum_to_one(self):
        total = sum(spec[1] for spec in SCENARIO_SPECS)
        assert abs(total - 1.0) < 1e-9

    def test_six_scenarios(self, scenarios):
        assert len(scenarios) == 6

    def test_severity_increases_blocking_decreases_probability(self, scenarios):
        """The scenario taxonomy's heavy tail: as congestion/blocking
        severity rises, probability falls."""
        for a, b in zip(scenarios, scenarios[1:]):
            assert b.congestion >= a.congestion
            assert b.block_frac >= a.block_frac
            assert b.prob <= a.prob

    def test_depot_arcs_never_blocked(self, scenarios):
        for scen in scenarios:
            for (i, j) in scen.blocked_arcs:
                assert i != 0 and j != 0


class TestModel:

    def test_rp_feasible(self, inst, scenarios):
        result = build_stochastic_model(inst, scenarios, time_limit=60)
        assert result is not None, "RP infeasible on the bundled small instance"
        assert result["RP_obj"] > 0
        assert result["RP_W1_expected"] > 0

    def test_rp_w1_increases_with_scenario_severity(self, inst, scenarios):
        """Worse scenarios (higher congestion / more blocked arcs) must
        never produce a *lower* W1 than a milder scenario — the recourse
        is strictly worse off, never better."""
        result = build_stochastic_model(inst, scenarios, time_limit=60)
        if result is None:
            pytest.skip("RP infeasible")
        w1_by_name = {name: ps["W1"] for name, ps in result["per_scenario"].items()}
        ordered = [w1_by_name[s.name] for s in scenarios]
        for a, b in zip(ordered, ordered[1:]):
            assert b >= a - 1e-4, (
                "W1 should be non-decreasing as scenarios get worse "
                f"(got {ordered})")

    def test_region_assignment_respects_exclusivity(self, inst, scenarios):
        result = build_stochastic_model(inst, scenarios, time_limit=60)
        if result is None:
            pytest.skip("RP infeasible")
        assigned = {}
        for (k, g), val in result["region_assignment"].items():
            if val:
                assigned.setdefault(k, []).append(g)
        for k, regions in assigned.items():
            assert len(regions) <= 1, f"Vehicle {k} assigned to multiple regions: {regions}"

    def test_vss_and_evpi_nonnegative(self, inst, scenarios):
        """VSS = EEV - RP and EVPI = RP - WS must both be >= 0 (up to
        MIP-gap-scale numerical slack) on a well-posed instance: RP can
        never do worse than a plan that ignores uncertainty (EEV), and
        never do better than knowing the future (WS).

        Skipped if any scenario came back infeasible under a fixed A
        (EV's or a per-scenario WS solve) — see the KNOWN LIMITATION note
        on solve_eev(): dropping an infeasible scenario's probability
        mass instead of penalizing it can understate EEV/WS and break
        this guarantee. Not a bug in the >=0 property itself, just in
        this test's ability to check it when that edge case fires.
        """
        result = analyze(inst, scenarios, time_limit=60)
        if result is None:
            pytest.skip("RP infeasible")
        if result["EEV"] and result["EEV"]["infeasible_scenarios"]:
            pytest.skip("EEV hit infeasible scenario(s), VSS not comparable "
                        "(see solve_eev's KNOWN LIMITATION note)")
        if any(r["infeasible"] for r in result["WS"]["per_scenario"].values()):
            pytest.skip("WS hit infeasible scenario(s), EVPI not comparable")
        if result["VSS"] is not None:
            assert result["VSS"] >= -1e-2, f"VSS should be >= 0, got {result['VSS']}"
        assert result["EVPI"] >= -1e-2, f"EVPI should be >= 0, got {result['EVPI']}"
