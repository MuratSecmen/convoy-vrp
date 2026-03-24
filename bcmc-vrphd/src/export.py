"""
src/export.py — Pareto frontier exporter
==========================================
Writes results to Excel (knee-point highlighted) and JSON.
"""

import json
import pandas as pd
from pathlib import Path
from typing import Dict, List


def export_results(
    frontier: List[Dict],
    instance_name: str,
    output_dir: str = "results",
):
    """Export Pareto frontier to Excel and JSON."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for idx, sol in enumerate(frontier):
        row = {
            "point": idx + 1,
            "W1": round(sol["W1"], 2),
            "W2": round(sol["W2"], 6),
            "status": sol["status"],
            "knee": sol.get("knee", False),
        }
        for k, lk in sol.get("L", {}).items():
            row[f"L_{k}"] = round(lk, 2) if lk is not None else None
        rows.append(row)

    df = pd.DataFrame(rows)

    route_rows = []
    for idx, sol in enumerate(frontier):
        for k, route in sol.get("routes", {}).items():
            route_rows.append({
                "point": idx + 1,
                "vehicle": k,
                "route": " -> ".join(str(n) for n in route),
                "L_k": round(sol["L"].get(k, 0), 2),
            })
    df_routes = pd.DataFrame(route_rows) if route_rows else pd.DataFrame()

    xlsx_path = out / f"{instance_name}_pareto.xlsx"
    with pd.ExcelWriter(str(xlsx_path), engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Frontier", index=False)
        if not df_routes.empty:
            df_routes.to_excel(writer, sheet_name="Routes", index=False)

    # Highlight knee row
    try:
        from openpyxl import load_workbook
        from openpyxl.styles import PatternFill
        wb = load_workbook(str(xlsx_path))
        ws = wb["Frontier"]
        knee_fill = PatternFill("solid", fgColor="FFC000")
        for row_idx in range(2, len(rows) + 2):
            if rows[row_idx - 2].get("knee"):
                for col in range(1, ws.max_column + 1):
                    ws.cell(row=row_idx, column=col).fill = knee_fill
        wb.save(str(xlsx_path))
    except Exception:
        pass

    json_path = out / f"{instance_name}_pareto.json"
    with open(str(json_path), "w") as jf:
        json.dump(rows, jf, indent=2, default=str)

    print(f"  Results: {xlsx_path}")
    print(f"  JSON:    {json_path}")
