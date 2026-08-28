"""
src/export.py — S-BCMC-VRPHD results exporter
=================================================
Writes the analyze() pipeline output (RP, EEV, WS, VSS, EVPI) to Excel.
"""

import json
from pathlib import Path
from typing import Dict, List
import pandas as pd
from src.scenarios import Scenario


def export_results(result: Dict, scenarios: List[Scenario], instance_name: str,
                    output_dir: str = "results"):
    """Export the full analyze() result to a single workbook."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    xlsx_path = out / f"{instance_name}_stochastic.xlsx"

    prob_by_name = {s.name: s.prob for s in scenarios}
    block_by_name = {s.name: s.block_frac for s in scenarios}
    cong_by_name = {s.name: s.congestion for s in scenarios}

    rp = result["RP"]

    with pd.ExcelWriter(str(xlsx_path), engine="openpyxl") as writer:

        # Sheet 1: Summary — RP / EEV / WS / VSS / EVPI
        eev = result.get("EEV")
        ws = result.get("WS")
        summary_rows = [
            {"Metric": "RP objective (E[W1] + penalty*E[shortfall])",
             "Value": round(rp["RP_obj"], 2)},
            {"Metric": "RP E[W1] (expected worst-case travel time)",
             "Value": round(rp["RP_W1_expected"], 2)},
            {"Metric": "RP MIP gap", "Value": f"{rp['gap']*100:.4f}%"},
            {"Metric": "EEV objective (mean-scenario plan under real scenarios)",
             "Value": round(eev["EEV_obj"], 2) if eev else "N/A (EV infeasible)"},
            {"Metric": "WS objective (perfect information)",
             "Value": round(ws["WS_obj"], 2)},
            {"Metric": "VSS = EEV - RP (value of modeling uncertainty)",
             "Value": round(result["VSS"], 2) if result["VSS"] is not None else "N/A"},
            {"Metric": "EVPI = RP - WS (value of perfect information)",
             "Value": round(result["EVPI"], 2)},
        ]
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary", index=False)

        # Sheet 2: Scenario definitions
        rows = [{
            "Scenario": s.name, "Probability": s.prob,
            "Blocked_arc_fraction": s.block_frac,
            "Congestion_multiplier": s.congestion,
            "Blocked_arcs_count": len(s.blocked_arcs),
        } for s in scenarios]
        pd.DataFrame(rows).to_excel(writer, sheet_name="Scenarios", index=False)

        # Sheet 3: Stage-1 region assignment (RP)
        rows = [{"Vehicle": k, "Region": g}
                for (k, g), val in rp["region_assignment"].items() if val]
        pd.DataFrame(rows).to_excel(writer, sheet_name="Stage1_RegionAssignment",
                                    index=False)

        # Sheet 4: Per-scenario RP results (W1, W2, shortfall)
        rows = []
        for s in scenarios:
            ps = rp["per_scenario"][s.name]
            total_shortfall = sum(ps["shortfall"].values())
            rows.append({
                "Scenario": s.name, "Probability": prob_by_name[s.name],
                "W1": round(ps["W1"], 2), "W2": round(ps["W2"], 4),
                "Total_shortfall": round(total_shortfall, 2),
                "N_shortfall_nodes": len(ps["shortfall"]),
            })
        pd.DataFrame(rows).to_excel(writer, sheet_name="RP_by_Scenario", index=False)

        # Sheet 5: RP routes per scenario per vehicle
        rows = []
        for s in scenarios:
            ps = rp["per_scenario"][s.name]
            for k, route in ps["routes"].items():
                rows.append({
                    "Scenario": s.name, "Vehicle": k,
                    "Route": " -> ".join(str(n) for n in route),
                })
        pd.DataFrame(rows).to_excel(writer, sheet_name="RP_Routes", index=False)

        # Sheet 6: EEV vs WS vs RP comparison per scenario
        rows = []
        for s in scenarios:
            row = {"Scenario": s.name, "Probability": prob_by_name[s.name],
                   "RP_W1": round(rp["per_scenario"][s.name]["W1"], 2)}
            if eev:
                e = eev["per_scenario"][s.name]
                row["EEV_W1"] = ("infeasible" if e["infeasible"]
                                 else round(e["W1"], 2))
            if ws:
                w = ws["per_scenario"][s.name]
                row["WS_W1"] = ("infeasible" if w["infeasible"]
                                else round(w["W1"], 2))
            rows.append(row)
        pd.DataFrame(rows).to_excel(writer, sheet_name="RP_vs_EEV_vs_WS", index=False)

    print(f"  [INFO] Results exported -> {xlsx_path}")
    return xlsx_path
