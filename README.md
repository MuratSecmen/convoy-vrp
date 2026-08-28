# convoy-vrp

**Bi-Objective Capacitated Military Convoy Vehicle Routing Problem with Heterogeneous Demand**
*(Deterministic & Two-Stage Stochastic Formulations)*

> A research implementation developed in the context of ISAF/Afghanistan ground supply chain operations (2001–2014), extending Yakıcı & Karasakal (2013).

---

## Overview

This repository contains two complementary mathematical programming models for military convoy routing under NATO supply chain constraints:

| Model | Class | Description |
|---|---|---|
| **BCMC-VRPHD** | Deterministic bi-objective MILP | Minimizes worst-case convoy travel time (W1) and worst-case plan deviation (W2) |
| **S-BCMC-VRPHD** | Two-stage stochastic MILP (TSSMOLP) | Extends BCMC-VRPHD with six ISAF-calibrated disruption scenarios |

Both models share the following structural features:

- **Open-tour routing** — vehicles do not return to the depot
- **Heterogeneous demand** — six NATO supply classes (I / II / III-W / IV / VIII / IX)
- **Heterogeneous vehicle fleet** — two-tier observability; class-specific cargo capacities
- **Hard time windows** — early arrival prohibition enforced
- **AO region separation** — vehicles assigned to non-overlapping operational areas
- **Subtour elimination** — Multi-Commodity Network Flow (MCNF) constraints replacing MTZ
- **Bi-objective solution** — ε-constraint method generating the Pareto frontier

---

## Repository Structure

```
convoy-vrp/
├── bcmc-vrphd/                  # Deterministic model
│   ├── src/
│   │   ├── model.py
│   │   ├── loader.py
│   │   └── export.py
│   ├── data/
│   │   ├── generate_instances.py
│   │   └── instances/
│   ├── tests/
│   ├── main.py
│   └── requirements.txt
├── s-bcmc-vrphd/                # Two-stage stochastic extension
│   ├── src/
│   │   ├── loader.py            # same Instance schema as bcmc-vrphd
│   │   ├── scenarios.py         # six ISAF-calibrated disruption scenarios
│   │   ├── model.py             # RP / EV / EEV / WS, VSS + EVPI
│   │   └── export.py
│   ├── tests/
│   ├── main.py
│   └── requirements.txt
├── .gitignore
└── requirements.txt
```

---

## Models

### BCMC-VRPHD (Deterministic)

Minimizes two conflicting objectives via the ε-constraint method (Haimes et al., 1971):

- **W1** — worst-case convoy travel time across all routes
- **W2** — worst-case deviation from the CJ4 briefing baseline plan

Key constraints: vehicle capacity per supply class, MCNF-based subtour elimination, hard time windows (early arrival prohibition), AO region feasibility, and single-server vs. split-delivery rules per supply class.

### S-BCMC-VRPHD (Two-Stage Stochastic)

Lives in `s-bcmc-vrphd/`, a separate CLI tool that reuses `bcmc-vrphd`'s
instance schema and constraint set. Classified as a **Two-Stage
Stochastic Multi-Objective Linear Program (TSSMOLP)** following Gutjahr
& Pichler (2016).

- **Stage 1 (here-and-now):** the AO **region assignment** `A[k,g]` —
  which operational area each convoy is committed to — is fixed before
  the disruption scenario is known (non-anticipativity).
- **Stage 2 (recourse):** everything downstream of "which roads are open
  today" — the actual route `x`, deliveries `f`/`T`, `L`, `W1`, `W2` — is
  re-optimized per scenario, but a vehicle can never route outside the
  AO region it was committed to in Stage 1. Demand a scenario makes
  physically unreachable is absorbed by a penalized `Shortfall` slack
  rather than making the model infeasible.

**Six disruption scenarios**, S0 (baseline, no disruption) through S5
(severe route collapse), each defined by a blocked-arc fraction and a
travel-time congestion multiplier, with probability decreasing as
severity increases. These are **illustrative, not fitted to a published
per-route probability table** — no such tactical-level dataset is
public. The scenario *shape* (a common low-severity mode, a thin
high-severity tail) is grounded in documented trends from the campaign
(IED incidents up ~75% 2009→2010, device power increasing over time,
convoys routinely detouring around suspect road damage rather than
outright losing the road) — see `s-bcmc-vrphd/src/scenarios.py` for the
exact numbers, the sourcing, and how to replace them with real data.

Performance metrics: **VSS** (value of the stochastic solution vs. the
expected-value/mean-scenario plan) and **EVPI** (value of perfect
information vs. having to commit to a region assignment in advance),
both computed by solving the same recourse problem under a fixed vs. a
free first-stage decision — see `s-bcmc-vrphd/src/model.py`.

IED/ambush threats are modeled as **exogenous stochastic parameters**, not as rational adversaries — deliberately distinguishing this work from Network Interdiction / Stackelberg game models (Wood, 1993; Israeli & Wood, 2002).

---

## Relationship to the Literature

| Feature | Yakıcı & Karasakal (2013) | This Work |
|---|---|---|
| Objective | Single (min travel time) | Bi-objective (W1, W2) via ε-constraint |
| Vehicle capacity | — | Per-class cargo capacity constraints |
| Time windows | Soft | Hard lower bound (early arrival prohibition) |
| Service time | Homogeneous | Class-specific T^{k,d}_i |
| Plan stability | — | W2 objective (Silav et al., 2021 adaptation) |
| Subtour elimination | MTZ | MCNF (Bektaş & Gouveia, 2014) |
| Uncertainty | Deterministic | Two-stage stochastic (6 ISAF scenarios) |

---

## Installation

```bash
git clone https://github.com/MuratSecmen/convoy-vrp.git
cd convoy-vrp/bcmc-vrphd
pip install -r requirements.txt
```

**Solver:** Gurobi, via the native `gurobipy` API — academic or commercial license required.

---

## Usage

### Deterministic (BCMC-VRPHD)

```bash
cd bcmc-vrphd

# Generate instances
python data/generate_instances.py

# Run solver
python main.py --instance data/instances/small_n5_k3.xlsx
python main.py --instance data/instances/medium_n10_k5.xlsx --time_limit 600
```

### Two-Stage Stochastic (S-BCMC-VRPHD)

Reuses `bcmc-vrphd`'s generated instances directly (same Excel schema):

```bash
cd s-bcmc-vrphd
pip install -r requirements.txt

python main.py --instance ../bcmc-vrphd/data/instances/small_n5_k3.xlsx
```

Solves RP (the full two-stage stochastic program), then EV → EEV and WS,
and reports VSS and EVPI. Note: the RP model builds all six scenarios'
worth of variables into **one** Gurobi model at once, so it is
substantially larger than the deterministic model on the same instance —
`medium_n10_k5` and `large_n15_k7` need a full (non size-limited) Gurobi
license.

---

## References

- Yakıcı, E., & Karasakal, O. (2013). A min-max vehicle routing problem with split delivery goods and heterogeneous demand. *Optimization Letters*, 7(7), 1611–1625.
- Gutjahr, W. J., & Pichler, A. (2016). Stochastic multi-objective optimization: a survey on non-scalarizing methods. *Annals of Operations Research*, 236(2), 475–499.
- Silav, A., Karasakal, E., & Karasakal, O. (2021). Bi-objective dynamic weapon-target assignment problem with stability measure. *Annals of Operations Research*, 296, 677–695.
- Bektaş, T., & Gouveia, L. (2014). Requiem for the Miller–Tucker–Zemlin subtour elimination constraints? *European Journal of Operational Research*, 236(3), 820–832.
- Haimes, Y. Y., Lasdon, L. S., & Wismer, D. A. (1971). On a bicriterion formulation of the problems of integrated system identification and system optimization. *IEEE Transactions on Systems, Man, and Cybernetics*, 1(3), 296–297.
- Wood, R. K. (1993). Deterministic network interdiction. *Mathematical and Computer Modelling*, 17(2), 1–18.

---

## Citation

```bibtex
@misc{secmen2026convoyvrp,
  author       = {Secmen, Murat},
  title        = {convoy-vrp: Bi-Objective Military Convoy Routing},
  year         = {2026},
  howpublished = {\url{https://github.com/MuratSecmen/convoy-vrp}},
  note         = {MSc thesis research, ISAF/Afghanistan ground supply chain context}
}
```

---

## License

This repository is made available for academic review purposes. For any other use, please contact the author.
