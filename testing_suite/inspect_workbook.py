"""Dump structure of the v22 panel workbook so scripts can be updated to match."""
import os
from xlsm_reader import sheet_names, load_sheet

HERE = os.path.dirname(os.path.abspath(__file__))
WB = os.path.join(HERE, "Panel inputs & outputs v22 macro_enabled 2026_07_09.xlsm")
OUT = os.path.join(HERE, "workbook_dump.txt")


def fmt(v):
    if v is None:
        return ""
    return str(v)


def main():
    lines = []
    names = sheet_names(WB)
    lines.append(f"WORKBOOK: {WB}")
    lines.append(f"SHEETS ({len(names)}): {names}")
    lines.append("")

    for name in names:
        try:
            rows = load_sheet(WB, name)
        except Exception as e:
            lines.append(f"=== SHEET: {name} === ERROR: {e}")
            continue
        n_rows = len(rows)
        n_cols = max((len(r) for r in rows), default=0)
        lines.append(f"=== SHEET: {name} === ({n_rows} rows x {n_cols} cols)")
        # First 6 rows in full
        for i, row in enumerate(rows[:6]):
            lines.append(f"  row{i}: " + " | ".join(fmt(v) for v in row))
        # A middle and last data row for shape reference
        if n_rows > 8:
            mid = n_rows // 2
            lines.append(f"  row{mid}: " + " | ".join(fmt(v) for v in rows[mid]))
            lines.append(f"  row{n_rows-1}: " + " | ".join(fmt(v) for v in rows[-1]))
        lines.append("")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
