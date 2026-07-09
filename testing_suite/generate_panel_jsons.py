import csv
import json
import os

# Path configuration
csv_path = r"c:\Users\james.derrod\VM Fusion Extension\testing_suite\Panel inputs & outputs v20 macro_enabled 2026_03_30(ValidationScenarios vFin).csv"
output_dir = r"c:\Users\james.derrod\VM Fusion Extension\testing_suite\panel_validation_tests"

# Ensure output directory exists
os.makedirs(output_dir, exist_ok=True)

# Read CSV and generate JSON files
with open(csv_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# CSV structure:
#   Row 1-2: header info (skip)
#   Row 3 (index 2): column names
#   Row 4+ (index 3+): data
#
# Columns (0-indexed):
#   0: Scenario
#   1: Drawing required?
#   2: panel_section           (string: TOP / BOTTOM)
#   3: panel_abuts_stile_front (bool: 0/1)
#   4: panel_front_stile_floor_to_ceiling (bool: 0/1, may be empty)
#   5: panel_abuts_stile_back  (bool: 0/1)
#   6: panel_back_stile_floor_to_ceiling  (bool: 0/1, may be empty)
#   7: stile_in_the_back_width (float, may be empty)
#   8: cutout_A                (string, may be empty)
#   9: cutout_B                (string, may be empty)
#  10: component_height        (float)
#  11: component_width         (float)
#  12: component_floor_clearance (float)
#  13: _component_ceiling_clearance (float)

data_lines = lines[3:]  # Skip first 3 lines (2 header + 1 column names)

count = 0
all_panels = []  # For the combined JSON


def parse_bool(val):
    """Parse a boolean value from CSV. Returns bool or None if empty."""
    val = val.strip()
    if val == '':
        return None
    return val == '1'


def parse_float(val):
    """Parse a float value from CSV. Returns float or None if empty."""
    val = val.strip()
    if val == '':
        return None
    return float(val)


def parse_string(val):
    """Parse a string value from CSV. Returns string or None if empty."""
    val = val.strip()
    if val == '':
        return None
    return val


for i, line in enumerate(data_lines):
    line = line.strip()
    if not line:
        continue
    
    parts = line.split(',')
    if len(parts) < 14:
        continue
    
    scenario = parts[0].strip()
    if not scenario.startswith('XX8X_PV_'):
        continue
    
    ibus_id = scenario
    
    # Parse values
    try:
        panel_section = parse_string(parts[2])
        panel_abuts_inline_stile_front = parse_bool(parts[3])
        panel_front_inline_stile_floor_to_ceiling = parse_bool(parts[4])
        panel_abuts_inline_stile_back = parse_bool(parts[5])
        panel_back_inline_stile_floor_to_ceiling = parse_bool(parts[6])
        stile_in_the_back_width = parse_float(parts[7])
        cutout_a = parse_string(parts[8])
        cutout_b = parse_string(parts[9])
        component_height = parse_float(parts[10])
        component_width = parse_float(parts[11])
        component_floor_clearance = parse_float(parts[12])
        component_ceiling_clearance = parse_float(parts[13])
    except (ValueError, IndexError) as e:
        print(f"Skipping {scenario}: {e}")
        continue
    
    # Build cutout string: combine cutout_A and cutout_B with " & " separator
    # This matches the production JSON format expected by _apply_cutout_parameters()
    cutout_parts = [p for p in [cutout_a, cutout_b] if p]
    cutout_value = ' & '.join(cutout_parts) if cutout_parts else None
    
    # Build parameters dict
    parameters = {
        "series_id": ["3082G.67P", "string", "series ID of the component"],
        "panel_section": [panel_section, "string", "section of the panel (TOP or BOTTOM)"],
        "panel_abuts_inline_stile_front": [panel_abuts_inline_stile_front, "bool", "indicates whether the panel's front edge abuts a stile"],
        "panel_abuts_inline_stile_back": [panel_abuts_inline_stile_back, "bool", "indicates whether the panel's back edge abuts a stile"],
        "component_height": [component_height, "float", "height of the component in inches"],
        "component_width": [component_width, "float", "width of the component in inches"],
        "component_floor_clearance": [component_floor_clearance, "float", "floor clearance of the component in inches"],
        "component_ceiling_clearance": [component_ceiling_clearance, "float", "ceiling clearance of the component in inches"],
    }
    
    # Only include optional parameters when they have values
    if panel_front_inline_stile_floor_to_ceiling is not None:
        parameters["panel_front_inline_stile_floor_to_ceiling"] = [panel_front_inline_stile_floor_to_ceiling, "bool", "indicates whether the front stile is floor to ceiling"]
    
    if panel_back_inline_stile_floor_to_ceiling is not None:
        parameters["panel_back_inline_stile_floor_to_ceiling"] = [panel_back_inline_stile_floor_to_ceiling, "bool", "indicates whether the back stile is floor to ceiling"]
    
    if stile_in_the_back_width is not None:
        parameters["stile_in_the_back_width"] = [stile_in_the_back_width, "float", "width of the stile in the back in inches"]
    
    if cutout_value is not None:
        parameters["cutout"] = [cutout_value, "string", "cutout specification (e.g. B-386 or B-354 + B-386)"]
    
    # Create JSON structure matching the panel format from production orders
    json_data = {
        "order_id": [ibus_id, "string", "identifier for the order"],
        "panels": [{
            "id": ["P1", "string", "panel ID"],
            "parameters": parameters
        }]
    }
    
    # Write individual JSON file using scenario as filename
    output_path = os.path.join(output_dir, f"{scenario}.json")
    with open(output_path, 'w', encoding='utf-8') as out_f:
        json.dump(json_data, out_f, indent=4)
    
    # Add to combined list
    all_panels.append({
        "scenario": scenario,
        "order_id": ibus_id,
        "panel": json_data["panels"][0]
    })
    
    count += 1

# Write combined JSON with all panels
combined_path = os.path.join(output_dir, "all_panel_combinations.json")
combined_data = {
    "description": "All XX8X panel validation scenarios",
    "total_scenarios": count,
    "scenarios": all_panels
}
with open(combined_path, 'w', encoding='utf-8') as out_f:
    json.dump(combined_data, out_f, indent=4)

print(f"Generated {count} individual JSON files in {output_dir}")
print(f"Generated combined JSON: {combined_path}")
