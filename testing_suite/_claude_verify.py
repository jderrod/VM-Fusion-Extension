"""Headless verification of the updated testing-suite tooling."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

results = []

# 1. Syntax-check the edited files
import py_compile
for fname in ("xlsm_reader.py", "generate_panel_jsons.py", "test_viewer.py"):
    py_compile.compile(os.path.join(HERE, fname), doraise=True)
    results.append(f"PASS  py_compile {fname}")

# 2. Import test_viewer (no UI at import) and check the panel suite config
import test_viewer

suite = test_viewer.TEST_SUITES.get("Panel XX8X (XX8X_PV)")
assert suite is not None, "Panel suite missing from TEST_SUITES"
assert suite["expected_csv"].exists(), f"expected_csv missing: {suite['expected_csv']}"
results.append(f"PASS  panel suite registered, expected_csv exists ({suite['expected_csv'].name})")

# 3. Load expected data through the viewer's own loader
expected = test_viewer.load_expected(suite["expected_csv"])
assert len(expected) == 1485, f"expected 1485 scenarios, got {len(expected)}"
row = expected["XX8X_PV_0002"]
assert row["bottom_notching_actual_y_dist"] == "2.4375", row
assert row["stile_in_the_back_width"] == "12", row
results.append(f"PASS  load_expected: {len(expected)} scenarios, spot values correct")

# 4. Run the viewer comparison for the panel suite (statuses only)
scen = test_viewer.run_comparison(suite)
statuses = {}
for name, info in scen.items():
    statuses[info["status"]] = statuses.get(info["status"], 0) + 1
results.append(f"PASS  run_comparison executed: {statuses}")

# 5. Validate generated JSONs against the workbook inputs
import xlsm_reader
wb = os.path.join(HERE, "Panel inputs & outputs v22 macro_enabled 2026_07_09.xlsm")
rows = xlsm_reader.load_sheet(wb, "ValidationScenarios vFin")
hdr = rows[2]
data = {r[0]: r for r in rows[3:] if r and r[0] and str(r[0]).startswith("XX8X_PV_")}
json_dir = os.path.join(HERE, "panel_validation_tests")
json_files = [f for f in os.listdir(json_dir) if f.startswith("XX8X_PV_") and f.endswith(".json")]
assert len(json_files) == len(data), f"{len(json_files)} JSONs vs {len(data)} scenarios"

import random
random.seed(0)
for fname in random.sample(json_files, 25):
    scenario = fname[:-5]
    with open(os.path.join(json_dir, fname), encoding="utf-8") as f:
        j = json.load(f)
    p = j["panels"][0]["parameters"]
    r = data[scenario]
    assert j["order_id"][0] == scenario
    assert p["panel_section"][0] == r[2], (scenario, "panel_section")
    assert float(p["component_height"][0]) == float(r[10]), (scenario, "height")
    assert float(p["component_width"][0]) == float(r[11]), (scenario, "width")
    cutouts = [c for c in (r[8], r[9]) if c]
    if cutouts:
        assert p["cutout"][0] == " & ".join(str(c) for c in cutouts), (scenario, "cutout")
    else:
        assert "cutout" not in p, (scenario, "cutout should be absent")
results.append("PASS  25 random JSONs match workbook inputs (section/height/width/cutout)")

with open(os.path.join(HERE, "_claude_verify_log.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(results) + "\nALL CHECKS PASSED\n")
print("\n".join(results))
