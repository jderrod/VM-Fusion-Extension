"""
generate_panel_jsons.py — build panel test-order JSONs from the panel
scenario workbook (or a CSV export of it).

Reads the 'ValidationScenarios vFin' sheet directly from the macro-enabled
workbook (no manual CSV export needed) and writes one input JSON per
XX8X_PV_* scenario, plus a combined JSON.

It also exports the 'ValidationOutputs' sheet to expected_output/ so the
test viewer can compare actual pipeline outputs against expected values.

Column lookup is header-based, so column reordering in future workbook
versions won't break generation.
"""

import csv
import json
import os
import sys

# Paths are script-relative so the suite works from any checkout location.
# (test_viewer may rewrite the csv_path line with an absolute path — that's fine.)
try:
    TESTING_SUITE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:  # executed via test_viewer's exec() wrapper
    TESTING_SUITE_DIR = os.getcwd()

# csv_path may be a .xlsm, .xlsx, or .csv — the loader handles all
csv_path = os.path.join(TESTING_SUITE_DIR, "Panel inputs & outputs v22 macro_enabled 2026_07_09.xlsm")
output_dir = os.path.join(TESTING_SUITE_DIR, "panel_validation_tests")
expected_csv_export = os.path.join(TESTING_SUITE_DIR, "expected_output", "Panel inputs & outputs v22 2026_07_09(ValidationOutputs).csv")

SCENARIO_SHEET = "ValidationScenarios vFin"
OUTPUTS_SHEET = "ValidationOutputs"
SCENARIO_PREFIX = "XX8X_PV_"
SERIES_ID = "3082G.67P"


# ─── Value coercion (handles typed xlsm cells AND csv strings) ───────────────

def as_str(val):
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def as_bool(val):
    """0/1, '0'/'1', TRUE/FALSE, bool -> bool; empty -> None."""
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    s = str(val).strip().lower()
    if s == "":
        return None
    if s in ("1", "true", "yes"):
        return True
    if s in ("0", "false", "no"):
        return False
    return None


def as_float(val):
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return float(val)
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    return float(s)


# ─── Sheet loading ───────────────────────────────────────────────────────────

def _import_xlsm_reader():
    """Import xlsm_reader regardless of how this script is executed."""
    for candidate in (
        os.path.dirname(os.path.abspath(csv_path)),
        TESTING_SUITE_DIR,
        os.getcwd(),
    ):
        if candidate and candidate not in sys.path:
            sys.path.insert(0, candidate)
    import xlsm_reader
    return xlsm_reader


def load_rows(path, sheet_name):
    """Return list-of-lists rows from a workbook sheet or a CSV file."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsm", ".xlsx", ".xltx", ".xltm"):
        reader = _import_xlsm_reader()
        return reader.load_sheet(path, sheet_name)
    # CSV fallback (a manual export of the sheet)
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.reader(f)]


def find_header(rows, key="Scenario"):
    """Locate the header row (first row whose first cell is `key`).
    Returns (header_index, {normalized_col_name: col_index})."""
    for i, row in enumerate(rows):
        if row and as_str(row[0]) == key:
            cols = {}
            for j, name in enumerate(row):
                name = as_str(name)
                if name:
                    cols[name.lstrip("_")] = j  # tolerate '_component_...' variants
            return i, cols
    raise ValueError(f"Header row starting with '{key}' not found")


def cell(row, cols, name):
    idx = cols.get(name)
    if idx is None or idx >= len(row):
        return None
    return row[idx]


# ─── Scenario JSON generation ────────────────────────────────────────────────

def build_panel_json(scenario, row, cols):
    panel_section = as_str(cell(row, cols, "panel_section"))
    abuts_front = as_bool(cell(row, cols, "panel_abuts_inline_stile_front"))
    front_ftc = as_bool(cell(row, cols, "panel_front_inline_stile_floor_to_ceiling"))
    abuts_back = as_bool(cell(row, cols, "panel_abuts_inline_stile_back"))
    back_ftc = as_bool(cell(row, cols, "panel_back_inline_stile_floor_to_ceiling"))
    stile_back_width = as_float(cell(row, cols, "stile_in_the_back_width"))
    cutout_a = as_str(cell(row, cols, "cutout_A"))
    cutout_b = as_str(cell(row, cols, "cutout_B"))
    height = as_float(cell(row, cols, "component_height"))
    width = as_float(cell(row, cols, "component_width"))
    floor_clr = as_float(cell(row, cols, "component_floor_clearance"))
    ceiling_clr = as_float(cell(row, cols, "component_ceiling_clearance"))

    # Combine cutout_A / cutout_B into the production 'cutout' string
    # (order_processor._apply_cutout_parameters splits on '&' or '+')
    cutout_parts = [p for p in (cutout_a, cutout_b) if p]
    cutout_value = " & ".join(cutout_parts) if cutout_parts else None

    parameters = {
        "series_id": [SERIES_ID, "string", "series ID of the component"],
        "panel_section": [panel_section, "string", "section of the panel (TOP, BOTTOM, or WHOLE)"],
        "panel_abuts_inline_stile_front": [abuts_front, "bool", "indicates whether the panel's front edge abuts a stile"],
        "panel_abuts_inline_stile_back": [abuts_back, "bool", "indicates whether the panel's back edge abuts a stile"],
        "component_height": [height, "float", "height of the component in inches"],
        "component_width": [width, "float", "width of the component in inches"],
        "component_floor_clearance": [floor_clr, "float", "floor clearance of the component in inches"],
        "component_ceiling_clearance": [ceiling_clr, "float", "ceiling clearance of the component in inches"],
    }

    # Optional parameters: only included when they carry a value
    if front_ftc is not None:
        parameters["panel_front_inline_stile_floor_to_ceiling"] = [front_ftc, "bool", "indicates whether the front stile is floor to ceiling"]
    if back_ftc is not None:
        parameters["panel_back_inline_stile_floor_to_ceiling"] = [back_ftc, "bool", "indicates whether the back stile is floor to ceiling"]
    if stile_back_width is not None:
        parameters["stile_in_the_back_width"] = [stile_back_width, "float", "width of the stile in the back in inches"]
    if cutout_value is not None:
        parameters["cutout"] = [cutout_value, "string", "cutout specification (e.g. B-386 or B-354 & B-386)"]

    return {
        "order_id": [scenario, "string", "identifier for the order"],
        "panels": [{
            "id": ["P1", "string", "panel ID"],
            "parameters": parameters,
        }],
    }


def clean_output_dir(directory):
    """Remove previously generated scenario JSONs so stale scenarios don't linger."""
    removed = 0
    if not os.path.isdir(directory):
        return removed
    for fname in os.listdir(directory):
        if fname.endswith(".json") and (
            fname.startswith(SCENARIO_PREFIX) or fname == "all_panel_combinations.json"
        ):
            try:
                os.remove(os.path.join(directory, fname))
                removed += 1
            except OSError:
                pass
    return removed


def export_expected_outputs(path, dest_csv):
    """Export the ValidationOutputs sheet to a CSV for the test viewer comparison."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".xlsm", ".xlsx", ".xltx", ".xltm"):
        print("Source is a CSV; skipping expected-output export (workbook required).")
        return None
    reader = _import_xlsm_reader()
    try:
        rows = reader.load_sheet(path, OUTPUTS_SHEET)
    except KeyError as e:
        print(f"WARNING: could not export expected outputs: {e}")
        return None

    os.makedirs(os.path.dirname(dest_csv), exist_ok=True)
    with open(dest_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for row in rows:
            writer.writerow(["" if v is None else v for v in row])
    n_scenarios = sum(
        1 for row in rows[1:]
        if row and as_str(row[0]) and str(row[0]).startswith(SCENARIO_PREFIX)
    )
    print(f"Exported expected outputs: {dest_csv} ({n_scenarios} scenarios)")
    return n_scenarios


def main():
    os.makedirs(output_dir, exist_ok=True)

    print(f"Reading scenarios from: {csv_path}")
    rows = load_rows(csv_path, SCENARIO_SHEET)
    header_idx, cols = find_header(rows)

    missing = [c for c in (
        "panel_section", "panel_abuts_inline_stile_front", "panel_abuts_inline_stile_back",
        "component_height", "component_width", "component_floor_clearance",
        "component_ceiling_clearance",
    ) if c not in cols]
    if missing:
        raise ValueError(f"Scenario sheet is missing expected columns: {missing}")

    removed = clean_output_dir(output_dir)
    if removed:
        print(f"Removed {removed} previously generated JSON files")

    count = 0
    skipped = []
    all_panels = []
    scenario_ids = set()

    for row in rows[header_idx + 1:]:
        scenario = as_str(row[0]) if row else None
        if not scenario or not scenario.startswith(SCENARIO_PREFIX):
            continue
        try:
            json_data = build_panel_json(scenario, row, cols)
        except (ValueError, TypeError) as e:
            skipped.append((scenario, str(e)))
            continue

        with open(os.path.join(output_dir, f"{scenario}.json"), "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=4)

        all_panels.append({
            "scenario": scenario,
            "order_id": scenario,
            "panel": json_data["panels"][0],
        })
        scenario_ids.add(scenario)
        count += 1

    combined_path = os.path.join(output_dir, "all_panel_combinations.json")
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump({
            "description": "All XX8X panel validation scenarios",
            "source": os.path.basename(csv_path),
            "total_scenarios": count,
            "scenarios": all_panels,
        }, f, indent=4)

    print(f"Generated {count} individual JSON files in {output_dir}")
    print(f"Generated combined JSON: {combined_path}")
    for scenario, err in skipped:
        print(f"  Skipped {scenario}: {err}")

    # Compute formula-based expected outputs (from 'Panel Calculated Values')
    try:
        import generate_panel_expected
        print()
        generate_panel_expected.main()
    except Exception as e:
        print(f"WARNING: formula-based expected-output calculation failed: {e}")

    # Export the static ValidationOutputs sheet too (reference only) and
    # cross-check scenario coverage
    export_expected_outputs(csv_path, expected_csv_export)
    ext = os.path.splitext(csv_path)[1].lower()
    if ext in (".xlsm", ".xlsx", ".xltx", ".xltm"):
        try:
            reader = _import_xlsm_reader()
            out_rows = reader.load_sheet(csv_path, OUTPUTS_SHEET)
            out_ids = {
                as_str(r[0]) for r in out_rows[1:]
                if r and as_str(r[0]) and str(r[0]).startswith(SCENARIO_PREFIX)
            }
            only_in = sorted(scenario_ids - out_ids)
            only_out = sorted(out_ids - scenario_ids)
            if only_in:
                print(f"WARNING: {len(only_in)} scenarios have inputs but no expected outputs, e.g. {only_in[:5]}")
            if only_out:
                print(f"WARNING: {len(only_out)} scenarios have expected outputs but no inputs, e.g. {only_out[:5]}")
            if not only_in and not only_out:
                print(f"Scenario coverage check passed: {len(out_ids)} scenarios in both sheets")
        except KeyError:
            pass


if __name__ == "__main__":
    main()
