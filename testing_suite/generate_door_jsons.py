import csv
import json
import os

# Path configuration
csv_path = r"c:\Users\james.derrod\VM Fusion Extension\testing_suite\3X8X Door inputs & outputs v10 macro_enabled 2026_02_12(ValidationScenarios vFin ).csv"
output_dir = r"c:\Users\james.derrod\VM Fusion Extension\testing_suite\door_validation_tests"

# Ensure output directory exists
os.makedirs(output_dir, exist_ok=True)

# Read CSV and generate JSON files
with open(csv_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Data starts at line 9 (index 8), skip header rows
data_lines = lines[8:]  # Skip first 8 lines (header)

count = 0
all_doors = []  # For the combined JSON

for i, line in enumerate(data_lines):
    line = line.strip()
    if not line:
        continue
    
    parts = line.split(',')
    if len(parts) < 13:
        continue
    
    scenario = parts[0].strip()
    if not scenario.startswith('3X8X_DV_'):
        continue
    
    # Extract the number from scenario for IBUS ID
    ibus_id = scenario
    
    # Parse values
    try:
        component_height = float(parts[2])
        component_width = float(parts[3])
        component_floor_clearance = float(parts[4])
        component_ceiling_clearance = float(parts[5])
        floor_to_ceiling = parts[6].strip() == '1'
        door_hinging_right = parts[7].strip() == '1'
        door_swinging_out = parts[8].strip() == '1'
        door_wall_post_hinging = parts[9].strip() == '1'
        door_wall_post_latching = parts[10].strip() == '1'
        door_wall_keep_latching = parts[11].strip() == '1'
        door_perp_stile_keeper = parts[12].strip() == '1'
    except (ValueError, IndexError) as e:
        print(f"Skipping {scenario}: {e}")
        continue
    
    # Create JSON structure
    json_data = {
        "order_id": [ibus_id, "string", "identifier for the order"],
        "doors": [{
            "id": ["D1", "string", "door ID"],
            "parameters": {
                "series_id": ["3082G.67P", "string", "series ID of the component"],
                "component_height": [component_height, "float", "height of the component in inches"],
                "component_width": [component_width, "float", "width of the component in inches"],
                "component_floor_clearance": [component_floor_clearance, "float", "floor clearance of the component in inches"],
                "component_ceiling_clearance": [component_ceiling_clearance, "float", "ceiling clearance of the component in inches."],
                "door_hinging_right": [door_hinging_right, "bool", "indicates whether the door is hinged on the right side when viewed from outside the stall"],
                "door_swinging_out": [door_swinging_out, "bool", "indicates whether the door swings outward into the bathroom"],
                "door_wall_post_hinging": [door_wall_post_hinging, "bool", "indicates whether the door is hinged on a wall post"],
                "door_wall_post_latching": [door_wall_post_latching, "bool", "indicates whether the door latches to a wall post"],
                "door_wall_keep_latching": [door_wall_keep_latching, "bool", "indicates whether the door latches to a wall keep"],
                "door_perp_stile_keeper": [door_perp_stile_keeper, "bool", "indicates whether the door latches on a perpendicular stile"],
                "floor_to_ceiling": [floor_to_ceiling, "bool", "indicates whether the stall is floor to ceiling or not"]
            }
        }]
    }
    
    # Write individual JSON file using scenario as filename
    output_path = os.path.join(output_dir, f"{scenario}.json")
    with open(output_path, 'w', encoding='utf-8') as out_f:
        json.dump(json_data, out_f, indent=4)
    
    # Add to combined list
    all_doors.append({
        "scenario": scenario,
        "order_id": ibus_id,
        "door": json_data["doors"][0]
    })
    
    count += 1

# Write combined JSON with all doors
combined_path = os.path.join(output_dir, "all_door_combinations.json")
combined_data = {
    "description": "All 3X8X door validation scenarios",
    "total_scenarios": count,
    "scenarios": all_doors
}
with open(combined_path, 'w', encoding='utf-8') as out_f:
    json.dump(combined_data, out_f, indent=4)

print(f"Generated {count} individual JSON files")
print(f"Generated combined JSON: {combined_path}")
