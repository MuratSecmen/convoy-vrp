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
├── bcmc-vrphd/
│   ├── src/
│   │   ├── model.py
│   │   ├── loader.py
│   │   └── export.py
│   ├── data/
│   │   ├── generate_instances.py
│   │   └── instances/
│   ├── tests/
│   ├── main.py
│   ├── requirements.txt
│   └── README.md
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

Classified as a **Two-Stage Stochastic Multi-Objective Linear Program (TSSMOLP)** following Gutjahr & Pichler (2016).

- **Stage 1 (here-and-now):** Routing decisions before scenario realization; non-anticipativity constraints enforced
- **Stage 2 (recourse):** Per-scenario delivery adjustments under arc blockages and congestion

Performance metrics: **VSS** and **EVPI**, adapted for the min-max bi-objective context.

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

```bash
cd bcmc-vrphd

# Generate instances
python data/generate_instances.py

# Run solver
python main.py --instance data/instances/small_n5_k3.xlsx
python main.py --instance data/instances/medium_n10_k5.xlsx --time_limit 600
```

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
