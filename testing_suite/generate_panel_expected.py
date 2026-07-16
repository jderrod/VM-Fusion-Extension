"""
generate_panel_expected.py — compute expected panel outputs by evaluating the
'Panel Calculated Values' formulas against every scenario in
'ValidationScenarios vFin'.

This replaces reliance on the static 'ValidationOutputs' sheet: expected
values are derived from the live model formulas in the workbook, so they
stay in sync with the calculation logic.

KNOWN WORKBOOK BUG (v22): the cutout_B_* formulas in 'Panel Calculated
Values' (G35:G38) are copy-paste errors — they test cutout_A instead of
cutout_B, and the x/y coordinate formulas are swapped/wrong. By default this
script uses CORRECTED logic (the cutout_A formulas with cutout_A replaced by
cutout_B). Set FIX_CUTOUT_B_BUG = False to replicate the sheet literally.

Outputs:
  expected_output/Panel inputs & outputs v22 2026_07_09(CalculatedExpected).csv
  expected_output/calculated_vs_validationoutputs_report.txt  (staleness check)
"""

import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import xlsm_reader
from excel_formula_eval import Evaluator

workbook_path = os.path.join(HERE, "Panel inputs & outputs v22 macro_enabled 2026_07_09.xlsm")
output_csv = os.path.join(HERE, "expected_output", "Panel inputs & outputs v22 2026_07_09(CalculatedExpected).csv")
report_path = os.path.join(HERE, "expected_output", "calculated_vs_validationoutputs_report.txt")

CALC_SHEET = "Panel Calculated Values"
SCENARIO_SHEET = "ValidationScenarios vFin"
OUTPUTS_SHEET = "ValidationOutputs"
SCENARIO_PREFIX = "XX8X_PV_"
FIX_CUTOUT_B_BUG = True

INPUT_COLUMNS = [
    "component_height", "component_width", "component_floor_clearance",
    "component_ceiling_clearance", "panel_section",
    "panel_abuts_inline_stile_front", "panel_front_inline_stile_floor_to_ceiling",
    "panel_abuts_inline_stile_back", "panel_back_inline_stile_floor_to_ceiling",
    "stile_in_the_back_width", "cutout_A", "cutout_B",
]

OUTPUT_COLUMNS = [
    "component_thickness", "notching_x_dist", "bottom_notching_standard_y_dist",
    "bottom_notching_actual_y_dist", "top_notching_y_dist", "shoe_height",
    "shoe_top_notch_gap", "notching_front_edge_bottom", "notching_back_edge_bottom",
    "notching_front_edge_top", "notching_back_edge_top",
    "front_notching_activation_offset", "back_notching_activation_offset",
    "cutout_A_width", "cutout_A_height", "cutout_A_x_coordinate", "cutout_A_y_coordinate",
    "cutout_B_width", "cutout_B_height", "cutout_B_x_coordinate", "cutout_B_y_coordinate",
]


# ─── Load the calculation model from the workbook ────────────────────────────

def load_model():
    """
    Build {name_lower: ('formula', text) | ('value', v)} from the calc sheet.
    Names include both the Variable column and workbook defined names.
    """
    rows = xlsm_reader.load_sheet(workbook_path, CALC_SHEET)
    formulas = xlsm_reader.load_sheet_formulas(workbook_path, CALC_SHEET)
    dnames = xlsm_reader.defined_names(workbook_path)

    model = {}
    row_to_names = {}

    # Defined names that point at G cells of the calc sheet
    ref_re = re.compile(r"'?Panel Calculated Values'?!\$G\$(\d+)$")
    for name, ref in dnames.items():
        if name.startswith("_xl"):
            continue
        m = ref_re.match(ref)
        if m:
            row_to_names.setdefault(int(m.group(1)) - 1, []).append(name)

    for i, row in enumerate(rows):
        if i == 0 or not row or not row[0]:
            continue
        dep = row[2] if len(row) > 2 else None
        if not dep:
            continue  # section label rows like 'Notching'
        var = str(row[0]).strip()
        value = row[6] if len(row) > 6 else None
        formula = formulas.get((i, 6))
        entry = ("formula", formula) if formula else ("value", value)
        names = set(n.lower() for n in row_to_names.get(i, []))
        names.add(var.lower())
        for n in names:
            model[n] = entry
    return model


def apply_cutout_b_fix(model):
    """Replace the buggy cutout_B_* formulas with corrected logic derived from
    the cutout_A_* formulas (cutout_A -> cutout_B, keeping constants)."""
    fixed = []
    word_re = re.compile(r"\bcutout_A\b")
    for suffix in ("width", "height", "x_coordinate", "y_coordinate"):
        a_key = f"cutout_a_{suffix}"
        b_key = f"cutout_b_{suffix}"
        kind, a_formula = model[a_key]
        assert kind == "formula", f"{a_key} has no formula"
        corrected = word_re.sub("cutout_B", a_formula)
        if model[b_key] != ("formula", corrected):
            model[b_key] = ("formula", corrected)
            fixed.append(b_key)
    return fixed


# ─── Per-scenario evaluation ─────────────────────────────────────────────────

class ScenarioEvaluator:
    def __init__(self, model):
        self.model = model
        self.evaluator = Evaluator(self.resolve)

    def set_inputs(self, inputs):
        self.inputs = {k.lower(): v for k, v in inputs.items()}
        self.cache = {}
        self.resolving = set()

    def resolve(self, name):
        name = name.lower()
        if name in self.inputs:
            return self.inputs[name]
        if name in self.cache:
            return self.cache[name]
        if name not in self.model:
            raise KeyError(f"Unknown name: {name}")
        if name in self.resolving:
            raise ValueError(f"Circular reference at {name}")
        self.resolving.add(name)
        kind, payload = self.model[name]
        try:
            if kind == "formula":
                val = self.evaluator.eval(payload)
            else:
                val = payload
        finally:
            self.resolving.discard(name)
        self.cache[name] = val
        return val


def fmt(v):
    """Format a computed value for CSV (match Excel-style output)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        if v == int(v):
            return str(int(v))
        return repr(round(v, 10))
    return str(v)


def main():
    model = load_model()
    print(f"Loaded {len(model)} named values/formulas from '{CALC_SHEET}'")

    if FIX_CUTOUT_B_BUG:
        fixed = apply_cutout_b_fix(model)
        if fixed:
            print(f"WARNING: corrected buggy workbook formulas for: {', '.join(fixed)}")
            print("         (fix cells G35:G38 of 'Panel Calculated Values' in Excel;")
            print("          set FIX_CUTOUT_B_BUG = False to replicate the sheet as-is)")

    # Load scenarios
    rows = xlsm_reader.load_sheet(workbook_path, SCENARIO_SHEET)
    header_idx = next(i for i, r in enumerate(rows) if r and r[0] == "Scenario")
    cols = {str(c).strip().lstrip("_"): j for j, c in enumerate(rows[header_idx]) if c}

    sev = ScenarioEvaluator(model)
    out_rows = []
    errors = []

    for row in rows[header_idx + 1:]:
        scenario = row[0] if row else None
        if not scenario or not str(scenario).startswith(SCENARIO_PREFIX):
            continue

        inputs = {}
        for name in INPUT_COLUMNS:
            j = cols.get(name.lstrip("_"))
            v = row[j] if j is not None and j < len(row) else None
            if v == "":
                v = None
            inputs[name] = v
        sev.set_inputs(inputs)

        record = {"Scenario": scenario}
        for name in INPUT_COLUMNS:
            record[name] = fmt(inputs[name])
        try:
            for name in OUTPUT_COLUMNS:
                record[name] = fmt(sev.resolve(name))
        except Exception as e:
            errors.append((scenario, str(e)))
            continue
        out_rows.append(record)

    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    fieldnames = ["Scenario"] + INPUT_COLUMNS + OUTPUT_COLUMNS
    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"Wrote {len(out_rows)} calculated expected rows -> {output_csv}")
    for scenario, err in errors[:10]:
        print(f"  ERROR {scenario}: {err}")
    if len(errors) > 10:
        print(f"  ... and {len(errors) - 10} more errors")

    # ── Cross-check against the static ValidationOutputs sheet ──────────────
    try:
        v_rows = xlsm_reader.load_sheet(workbook_path, OUTPUTS_SHEET)
    except KeyError:
        print(f"'{OUTPUTS_SHEET}' sheet not found; skipping staleness check")
        return

    v_header = [str(c).strip() if c else "" for c in v_rows[0]]
    v_data = {}
    for r in v_rows[1:]:
        if r and r[0] and str(r[0]).startswith(SCENARIO_PREFIX):
            v_data[str(r[0])] = {v_header[j]: r[j] if j < len(r) else None
                                 for j in range(len(v_header))}

    def close(a, b):
        a = "" if a is None else str(a).strip()
        b = "" if b is None else str(b).strip()
        if a == b:
            return True
        try:
            return abs(float(a) - float(b)) < 1e-4
        except ValueError:
            return False

    diff_counts = {}
    diff_examples = {}
    checked = 0
    for rec in out_rows:
        v = v_data.get(rec["Scenario"])
        if not v:
            continue
        checked += 1
        for col in OUTPUT_COLUMNS:
            if col not in v:
                continue
            if not close(rec[col], v[col]):
                diff_counts[col] = diff_counts.get(col, 0) + 1
                diff_examples.setdefault(col, []).append(
                    (rec["Scenario"], v[col], rec[col]))

    lines = [
        "Cross-check: calculated expected values vs static 'ValidationOutputs' sheet",
        f"Scenarios compared: {checked}",
        "",
    ]
    if not diff_counts:
        lines.append("PERFECT MATCH — the ValidationOutputs sheet agrees with the live formulas.")
    else:
        lines.append(f"Columns with differences ({len(diff_counts)}):")
        for col, n in sorted(diff_counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {col}: {n} scenario(s) differ")
            for scen, v_old, v_new in diff_examples[col][:3]:
                lines.append(f"      e.g. {scen}: ValidationOutputs={v_old!r} calculated={v_new!r}")
    report = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print()
    print(report)
    print(f"\nReport saved -> {report_path}")


if __name__ == "__main__":
    main()
