"""Dump Panel Calculated Values variables/formulas and workbook defined names."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import xlsm_reader

WB = os.path.join(HERE, "Panel inputs & outputs v22 macro_enabled 2026_07_09.xlsm")
OUT = os.path.join(HERE, "_claude_formulas_dump.txt")

lines = []

# Defined names
names = xlsm_reader.defined_names(WB)
lines.append(f"DEFINED NAMES ({len(names)}):")
for k in sorted(names):
    lines.append(f"  {k} = {names[k]}")
lines.append("")

# Panel Calculated Values sheet
sheet = "Panel Calculated Values"
rows = xlsm_reader.load_sheet(WB, sheet)
formulas = xlsm_reader.load_sheet_formulas(WB, sheet)

lines.append(f"SHEET '{sheet}': {len(rows)} rows")
header = rows[0]
lines.append("HEADER: " + " | ".join(str(v) for v in header))
lines.append("")

for i, row in enumerate(rows[1:], start=1):
    var = row[0] if len(row) > 0 else None
    if not var:
        continue
    order = row[1] if len(row) > 1 else None
    dep = row[2] if len(row) > 2 else None
    rel = row[3] if len(row) > 3 else None
    val = row[6] if len(row) > 6 else None
    cell_formula = formulas.get((i, 6))  # actual formula in the Value column
    expr_text = row[7] if len(row) > 7 else None
    lines.append(f"--- row {i}: {var}")
    lines.append(f"    order={order} dep={dep} rel={rel}")
    lines.append(f"    cached_value={val!r}")
    lines.append(f"    cell_formula={cell_formula!r}")
    if expr_text and (not cell_formula or str(expr_text).strip().lstrip('=') != str(cell_formula).strip()):
        lines.append(f"    expression_text={expr_text!r}")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"Wrote {OUT} ({len(lines)} lines)")
