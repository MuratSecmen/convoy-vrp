# BCMC-VRPHD

**Bi-Objective Capacitated Military Convoy Vehicle Routing Problem with Heterogeneous Demand**

Deterministic MIP formulation for ISAF/IJC CJ4 Surface Movement Operations (Afghanistan, 2001–2014).

## Model

| Objective | Formula | Meaning |
|-----------|---------|---------|
| f₁ = W₁  | min max_k L_k | Minimize worst-case convoy travel time |
| f₂ = W₂  | min max_k (L_k − L̄_k)/L̄_k | Minimize worst-case plan deviation |

**Key features:**
- Min-max bi-objective structure (Yakıcı & Karasakal, 2013)
- MCNF subtour elimination (replaces MTZ; tighter LP relaxation)
- NATO supply classes I/II/III-W/IV/VIII/IX
- Two-tier vehicle observability (LOGFAS-EVE / CORSOM EWMA)
- Open-tour routing (no return-arc cost)
- AO region-exclusivity (ISAF Regional Commands)
- ε-constraint Pareto frontier with knee-point detection

## Project Structure

```
bcmc-vrphd/
├── src/
│   ├── model.py          # BCMC-VRPHD solver (PuLP/CBC)
│   ├── loader.py         # Excel instance loader
│   └── export.py         # Pareto → Excel/JSON exporter
├── data/
│   ├── generate_instances.py
│   └── instances/
│       ├── small_n5_k3.xlsx
│       ├── medium_n10_k5.xlsx
│       └── large_n15_k7.xlsx
├── tests/
│   └── test_model.py     # 15 tests
├── results/
├── main.py
├── requirements.txt
└── README.md
```

## Installation

```bash
pip install -r requirements.txt
```

Requires Python 3.9+.

## Usage

```bash
# Generate benchmark instances
python data/generate_instances.py

# Run single instance
python main.py --instance data/instances/small_n5_k3.xlsx --n_points 5

# Run all instances
python main.py --all --n_points 10 --time_limit 300

# Run tests
python -m pytest tests/ -v
```

## Input Format (Excel)

| Sheet | Columns |
|-------|---------|
| Nodes | node_id, type, x_km, y_km, ao_region |
| Vehicles | vehicle_id, platform, capacity, speed_factor, observable, capable_classes |
| TravelTime | from, to, vehicle_id, time_min |
| Demand | node_id, class, quantity |
| ServiceRate | vehicle_id, class, rate_units_per_min |
| Baseline | vehicle_id, baseline_min |
| Regions | node_id, ao_region |

## References

- Yakıcı, E. & Karasakal, O. (2013). A min-max vehicle routing problem with split delivery and heterogeneous demand. *Optimization Letters*, 7(7), 1611–1625.
- Bektaş, T. & Gouveia, L. (2014). Requiem for the MTZ subtour elimination constraints? *EJOR*, 236(3), 820–832.
- Haimes, Y.Y. et al. (1971). On a bicriterion formulation. *IEEE Trans. SMC*, SMC-1(3), 296–297.
- Wolsey, L.A. (1998). *Integer Programming*. Wiley.
