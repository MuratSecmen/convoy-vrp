"""
src/scenarios.py — S-BCMC-VRPHD disruption scenarios
=======================================================
Six ISAF-calibrated disruption scenarios for the two-stage stochastic
extension of BCMC-VRPHD.

IMPORTANT — what "calibrated" means here
------------------------------------------
No published dataset gives per-route IED/ambush probabilities for ISAF
ground supply convoys (this is tactical-level data that was never public).
What IS publicly documented, and what this taxonomy is grounded in:

  - IED incidents in Afghanistan rose sharply over the campaign (civilian
    IED deaths up ~75% from 2009 to 2010) and show strong seasonality,
    spiking in spring/summer alongside increased ISAF operational tempo.
  - Convoys routinely took off-road detours or stopped to investigate
    suspicious road damage rather than proceeding — i.e. route segments
    going temporarily unusable/delayed, not permanently destroyed.
  - Device power increased over the campaign (from ~20 lb charges to
    barrel-sized charges), i.e. the *severity* of a disruption, when one
    occurred, grew heavier-tailed over time.
    Sources: NATO logistics in the Afghan War (Wikipedia); "Roadside
    Bombs: An Iraqi Tactic on the Upsurge in Afghanistan" (TIME);
    "Counter-IED Strategy in Modern War" (Military Review, 2012).

So the six scenarios below encode that SHAPE (a common low-severity mode,
a long thin high-severity tail) as an ILLUSTRATIVE, not fitted,
probability distribution. Replace SCENARIO_SPECS with real command data
if/when it becomes available — the model and every downstream VSS/EVPI
computation is agnostic to where these numbers come from.

Each scenario perturbs the deterministic instance two ways:
  - block_frac : fraction of non-depot arcs (i,j), i,j != 0, blocked
    outright (removed from the feasible arc set for that scenario).
  - congestion : multiplier applied to travel time on all SURVIVING
    arcs (detours, checkpoints, dismounted clearance stops).
Depot arcs (i=0 or j=0) are never blocked — a convoy can always leave
or return to base, only the road network in between degrades.
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple


@dataclass
class Scenario:
    name: str
    prob: float
    block_frac: float
    congestion: float
    blocked_arcs: Set[Tuple[int, int]] = field(default_factory=set)


# name, probability, blocked-arc fraction, congestion multiplier.
# Probabilities sum to 1.0. Severity increases, probability decreases —
# the heavy-tailed shape described above.
SCENARIO_SPECS = [
    ("S0_Baseline",         0.30, 0.00, 1.00),
    ("S1_Minor_IED",        0.25, 0.05, 1.15),
    ("S2_Checkpoint_Delay", 0.20, 0.10, 1.35),
    ("S3_Ambush_Risk",      0.12, 0.15, 1.60),
    ("S4_Major_IED",        0.08, 0.25, 2.00),
    ("S5_Route_Collapse",   0.05, 0.35, 2.50),
]

SCENARIO_SEED = 100  # distinct from the base instance's generator seed (42)


def generate_scenarios(inst, seed: int = SCENARIO_SEED) -> List[Scenario]:
    """Materialize the six scenarios' blocked-arc sets for this instance.

    Each scenario independently samples block_frac of the non-depot arcs
    to block. Same seed -> same blocked-arc sets for a given instance,
    for reproducibility across RP / EV / EEV / WS solves.
    """
    total = sum(spec[1] for spec in SCENARIO_SPECS)
    if abs(total - 1.0) > 1e-9:
        raise ValueError(
            f"SCENARIO_SPECS probabilities must sum to 1.0, got {total}")

    non_depot_arcs = [(i, j) for (i, j) in inst.E if i != 0 and j != 0]

    rng = random.Random(seed)
    scenarios = []
    for name, prob, block_frac, congestion in SCENARIO_SPECS:
        n_block = round(block_frac * len(non_depot_arcs))
        blocked = set(rng.sample(non_depot_arcs, n_block)) if n_block else set()
        scenarios.append(Scenario(
            name=name, prob=prob, block_frac=block_frac,
            congestion=congestion, blocked_arcs=blocked))
    return scenarios


def scenario_travel_time(inst, scenario: Scenario) -> Dict[Tuple[int, int, int], float]:
    """p[i,j,k] perturbed by this scenario's congestion multiplier.

    Blocked arcs are NOT removed from this dict (build_scenario_block
    removes them from the variable domain instead) — this dict only
    carries the surviving-arc congestion effect.
    """
    return {key: val * scenario.congestion for key, val in inst.p.items()}


def expected_travel_time(inst) -> Dict[Tuple[int, int, int], float]:
    """Probability-weighted average congestion multiplier, no blocking.

    Used for the EV (expected-value) problem: the classical stochastic-
    programming baseline that ignores uncertainty by planning against
    the mean scenario.
    """
    mean_congestion = sum(spec[1] * spec[3] for spec in SCENARIO_SPECS)
    return {key: val * mean_congestion for key, val in inst.p.items()}
