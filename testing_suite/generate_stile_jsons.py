import csv
import json
import os

# Path configuration
csv_path = r"c:\Users\james.derrod\VM Fusion Extension\testing_suite\3X82 Stile inputs & outputs v15 macro_enabled 2026_02_26(ValidationScenarios vFin)(3).csv"
output_dir = r"c:\Users\james.derrod\VM Fusion Extension\testing_suite\stile_validation_tests"

# Ensure output directory exists
os.makedirs(output_dir, exist_ok=True)

# Read CSV and generate JSON files
with open(csv_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# CSV header (row 2, index 1):
# Count, Scenario, Drawing required?, component_height, component_width,
# LD_height, LD_floor_clearance, RD_height, RD_floor_clearance,
# left_side_door, LD_hinging_right, LD_swinging_out,
# right_side_door, RD_hinging_right, RD_swinging_out, ...

# Data starts at line 3 (index 2)
data_lines = lines[2:]

count = 0
all_stiles = []  # For the combined JSON

for i, line in enumerate(data_lines):
    line = line.strip()
    if not line:
        continue
    
    parts = line.split(',')
    if len(parts) < 15:
        continue
    
    scenario = parts[1].strip()
    if not scenario.startswith('3X82_SV_'):
        continue
    
    ibus_id = scenario
    
    # Parse values
    try:
        component_height = float(parts[3])
        component_width = float(parts[4])
        
        # Left door parameters (may be empty if no left door)
        ld_height = float(parts[5]) if parts[5].strip() else None
        ld_floor_clearance = float(parts[6]) if parts[6].strip() else None
        
        # Right door parameters (may be empty if no right door)
        rd_height = float(parts[7]) if parts[7].strip() else None
        rd_floor_clearance = float(parts[8]) if parts[8].strip() else None
        
        # Boolean flags
        left_side_door = parts[9].strip() == '1'
        ld_hinging_right = parts[10].strip() == '1' if parts[10].strip() else None
        ld_swinging_out = parts[11].strip() == '1' if parts[11].strip() else None
        
        right_side_door = parts[12].strip() == '1'
        rd_hinging_right = parts[13].strip() == '1' if parts[13].strip() else None
        rd_swinging_out = parts[14].strip() == '1' if parts[14].strip() else None
        
    except (ValueError, IndexError) as e:
        print(f"Skipping {scenario}: {e}")
        continue
    
    # When no door on a side, set dependent params to null
    if not left_side_door:
        ld_height = None
        ld_floor_clearance = None
        ld_hinging_right = None
        ld_swinging_out = None
    
    if not right_side_door:
        rd_height = None
        rd_floor_clearance = None
        rd_hinging_right = None
        rd_swinging_out = None
    
    # Create JSON structure matching the stile format from production orders
    json_data = {
        "order_id": [ibus_id, "string", "identifier for the order"],
        "stiles": [{
            "id": ["S1", "string", "stile ID"],
            "parameters": {
                "series_id": ["3082G.67P", "string", "series ID of the component"],
                "component_height": [component_height, "float", "height of the component in inches"],
                "component_width": [component_width, "float", "width of the component in inches"],
                "left_side_door": [left_side_door, "bool", "indicates whether there is a door on the stile's left side when viewed from the room"],
                "LD_hinging_right": [ld_hinging_right, "bool", "indicates whether the left side of the stile serves as the hinge stile for the adjacent door, rather than the keep stile"],
                "LD_height": [ld_height, "float", "height of the door on the left side of the stile"],
                "LD_floor_clearance": [ld_floor_clearance, "float", "floor clearance of the door on the left side of the stile"],
                "LD_swinging_out": [ld_swinging_out, "bool", "indicates whether the door on the left side of the stile swings outward into the bathroom"],
                "right_side_door": [right_side_door, "bool", "indicates whether there is a door on the stile's right side when viewed from the room"],
                "RD_hinging_right": [rd_hinging_right, "bool", "indicates whether the right side of the stile serves as the hinge stile for the adjacent door, rather than the keep stile"],
                "RD_height": [rd_height, "float", "height of the door on the right side of the stile"],
                "RD_floor_clearance": [rd_floor_clearance, "float", "floor clearance of the door on the right side of the stile"],
                "RD_swinging_out": [rd_swinging_out, "bool", "indicates whether the door on the right side of the stile swings outward into the bathroom"]
            }
        }]
    }
    
    # Write individual JSON file using scenario as filename
    output_path = os.path.join(output_dir, f"{scenario}.json")
    with open(output_path, 'w', encoding='utf-8') as out_f:
        json.dump(json_data, out_f, indent=4)
    
    # Add to combined list
    all_stiles.append({
        "scenario": scenario,
        "order_id": ibus_id,
        "stile": json_data["stiles"][0]
    })
    
    count += 1

# Write combined JSON with all stiles
combined_path = os.path.join(output_dir, "all_stile_combinations.json")
combined_data = {
    "description": "All 3X82 stile validation scenarios",
    "total_scenarios": count,
    "scenarios": all_stiles
}
with open(combined_path, 'w', encoding='utf-8') as out_f:
    json.dump(combined_data, out_f, indent=4)

print(f"Generated {count} individual JSON files in {output_dir}")
print(f"Generated combined JSON: {combined_path}")
