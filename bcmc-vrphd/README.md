# BCMC-VRPHD

**Bi-Objective Capacitated Military Convoy VRP with Heterogeneous Demand**

| Objective | Description |
|-----------|-------------|
| f₁ = W₁  | min max_k L_k — worst-case convoy travel time |
| f₂ = W₂  | min max_k (L_k − L̄_k) / L̄_k — worst-case plan deviation |

## Features

- Min-max bi-objective structure (ε-constraint Pareto frontier)
- Open-tour routing (return arc excluded from cost)
- MCNF subtour elimination (tighter LP relaxation than MTZ)
- NATO supply classes: I, II, III-W, IV, VIII, IX
- Two-tier vehicle observability (LOGFAS-EVE / CORSOM EWMA)
- Early arrival prohibition (eq5)
- AO region exclusivity (ISAF Regional Commands)
- Knee-point detection on Pareto frontier
- Class-specific service time T^{k,d}_i (prevents phantom MCNF demand)

## Installation

```bash
pip install -r requirements.txt
```

Requires Python 3.9+.

## Usage

```bash
# Generate benchmark instances
python data/generate_instances.py

# Run a single instance
python main.py --instance data/instances/small_n5_k3.xlsx --n_points 10

# Run all instances
python main.py --all --n_points 10 --time_limit 300

# Run tests
python -m pytest tests/ -v
```

## Project Structure

```
bcmc-vrphd/
├── src/
│   ├── model.py          # Solver (PuLP/CBC, ε-constraint)
│   ├── loader.py         # Excel instance loader
│   └── export.py         # Pareto → Excel + JSON
├── data/
│   ├── generate_instances.py
│   └── instances/
│       ├── small_n5_k3.xlsx
│       ├── medium_n10_k5.xlsx
│       └── large_n15_k7.xlsx
├── tests/
│   └── test_model.py     # 6 tests
├── results/
├── main.py
├── requirements.txt
└── README.md
```

## References

- Yakıcı, E. & Karasakal, O. (2013). *Optimization Letters*, 7(7), 1611–1625.
- Gutjahr, W.J. & Pichler, A. (2016). *EJOR*, 252(2), 351–366.
- Bektaş, T. & Gouveia, L. (2014). *EJOR*, 236(3), 820–832.
- McCormick, G.P. (1976). *Mathematical Programming*, 10, 147–175.
