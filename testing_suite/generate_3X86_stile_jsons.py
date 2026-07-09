import csv
import json
import os

# Path configuration
csv_path = r"c:\Users\james.derrod\VM Fusion Extension\testing_suite\3X86 Stile inputs & outputs v08 macro_enabled 2026_03_12(ValidationScenario vFin).csv"
output_dir = r"c:\Users\james.derrod\VM Fusion Extension\testing_suite\stile_validation_tests"

# Ensure output directory exists
os.makedirs(output_dir, exist_ok=True)

# Read CSV and generate JSON files
with open(csv_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# CSV header (row 3, index 2):
# Count, Scenario, Drawing required?, component_height, component_width,
# LD_height, LD_floor_clearance, LD_ceiling_clearance,
# RD_height, RD_floor_clearance, RD_ceiling_clearance,
# left_side_door, LD_hinging_right, LD_swinging_out,
# right_side_door, RD_hinging_right, RD_swinging_out, ...
#
# Col indices (0-based):
#  0: Count
#  1: Scenario
#  2: Drawing required?
#  3: component_height
#  4: component_width
#  5: LD_height
#  6: LD_floor_clearance
#  7: LD_ceiling_clearance
#  8: RD_height
#  9: RD_floor_clearance
# 10: RD_ceiling_clearance
# 11: left_side_door
# 12: LD_hinging_right
# 13: LD_swinging_out
# 14: right_side_door
# 15: RD_hinging_right
# 16: RD_swinging_out

# Data starts at line 4 (index 3)
data_lines = lines[3:]

count = 0
all_stiles = []  # For the combined JSON

for i, line in enumerate(data_lines):
    line = line.strip()
    if not line:
        continue
    
    parts = line.split(',')
    if len(parts) < 17:
        continue
    
    scenario = parts[1].strip()
    if not scenario.startswith('3X86_SV_'):
        continue
    
    ibus_id = scenario
    
    # Parse values
    try:
        component_height = float(parts[3])
        component_width = float(parts[4])
        
        # Left door parameters (may be empty if no left door)
        ld_height = float(parts[5]) if parts[5].strip() else None
        ld_floor_clearance = float(parts[6]) if parts[6].strip() else None
        ld_ceiling_clearance = float(parts[7]) if parts[7].strip() else None
        
        # Right door parameters (may be empty if no right door)
        rd_height = float(parts[8]) if parts[8].strip() else None
        rd_floor_clearance = float(parts[9]) if parts[9].strip() else None
        rd_ceiling_clearance = float(parts[10]) if parts[10].strip() else None
        
        # Boolean flags
        left_side_door = parts[11].strip() == '1'
        ld_hinging_right = parts[12].strip() == '1' if parts[12].strip() else None
        ld_swinging_out = parts[13].strip() == '1' if parts[13].strip() else None
        
        right_side_door = parts[14].strip() == '1'
        rd_hinging_right = parts[15].strip() == '1' if parts[15].strip() else None
        rd_swinging_out = parts[16].strip() == '1' if parts[16].strip() else None
        
    except (ValueError, IndexError) as e:
        print(f"Skipping {scenario}: {e}")
        continue
    
    # When no door on a side, set dependent params to null
    if not left_side_door:
        ld_height = None
        ld_floor_clearance = None
        ld_ceiling_clearance = None
        ld_hinging_right = None
        ld_swinging_out = None
    
    if not right_side_door:
        rd_height = None
        rd_floor_clearance = None
        rd_ceiling_clearance = None
        rd_hinging_right = None
        rd_swinging_out = None
    
    # Create JSON structure matching the stile format with 3X86-specific ceiling clearance fields
    json_data = {
        "order_id": [ibus_id, "string", "identifier for the order"],
        "stiles": [{
            "id": ["S1", "string", "stile ID"],
            "parameters": {
                "series_id": ["3086G.67P", "string", "series ID of the component"],
                "component_height": [component_height, "float", "height of the component in inches"],
                "component_width": [component_width, "float", "width of the component in inches"],
                "left_side_door": [left_side_door, "bool", "indicates whether there is a door on the stile's left side when viewed from the room"],
                "LD_hinging_right": [ld_hinging_right, "bool", "indicates whether the left side of the stile serves as the hinge stile for the adjacent door, rather than the keep stile"],
                "LD_height": [ld_height, "float", "height of the door on the left side of the stile"],
                "LD_floor_clearance": [ld_floor_clearance, "float", "floor clearance of the door on the left side of the stile"],
                "LD_ceiling_clearance": [ld_ceiling_clearance, "float", "ceiling clearance of the door on the left side of the stile"],
                "LD_swinging_out": [ld_swinging_out, "bool", "indicates whether the door on the left side of the stile swings outward into the bathroom"],
                "right_side_door": [right_side_door, "bool", "indicates whether there is a door on the stile's right side when viewed from the room"],
                "RD_hinging_right": [rd_hinging_right, "bool", "indicates whether the right side of the stile serves as the hinge stile for the adjacent door, rather than the keep stile"],
                "RD_height": [rd_height, "float", "height of the door on the right side of the stile"],
                "RD_floor_clearance": [rd_floor_clearance, "float", "floor clearance of the door on the right side of the stile"],
                "RD_ceiling_clearance": [rd_ceiling_clearance, "float", "ceiling clearance of the door on the right side of the stile"],
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

# Write combined JSON with all 3X86 stiles
combined_path = os.path.join(output_dir, "all_3X86_stile_combinations.json")
combined_data = {
    "description": "All 3X86 stile validation scenarios",
    "total_scenarios": count,
    "scenarios": all_stiles
}
with open(combined_path, 'w', encoding='utf-8') as out_f:
    json.dump(combined_data, out_f, indent=4)

print(f"Generated {count} individual JSON files in {output_dir}")
print(f"Generated combined JSON: {combined_path}")
