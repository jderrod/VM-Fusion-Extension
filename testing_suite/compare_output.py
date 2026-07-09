import csv
import json
import os
import sys

# Configuration
EXPECTED_CSV_PATH = r"c:\Users\james.derrod\VM Fusion Extension\testing_suite\expected_output\expected_output.csv"
ACTUAL_OUTPUT_DIR = r"c:\Users\james.derrod\VM Fusion Extension\testing_suite\actual_output"
COMPARISON_OUTPUT_PATH = r"c:\Users\james.derrod\VM Fusion Extension\testing_suite\comparison_results.csv"

# Parameters to compare (columns from expected_output.csv, excluding 'Scenario')
PARAMETERS_TO_COMPARE = [
    "component_height", "component_width", "component_thickness", "component_floor_clearance",
    "ceiling_clearance", "floor_to_ceiling", "door_hinging_right", "door_swinging_out",
    "door_wall_post_hinging", "door_wall_post_latching", "door_wall_keep_latching", "door_perp_stile_keeper",
    "hinge_hole_x_dist", "hinge_hole_radius", "hinge_hole_depth", "bottom_notching_y_dist",
    "top_notching_y_dist", "notching_x_dist", "door_bottom_margin", "door_top_margin",
    "shoe_height", "shoe_door_top_notch_gap", "hinge_hole_space", "inter_hinge_gap",
    "mid_top_hinge_offset", "mid_bottom_hinge_offset", "rabbeting_width", "rabbeting_depth",
    "left_interior_drilling", "left_exterior_drilling", "right_interior_drilling", "right_exterior_drilling",
    "left_interior_rabbeting", "left_exterior_rabbeting", "right_interior_rabbeting", "right_exterior_rabbeting",
    "bottom_left_notching", "bottom_right_notching", "top_left_notching", "top_right_notching",
    "top_hinge_hole_1_y_value", "top_hinge_hole_2_y_value", "mid_top_hinge_hole_1_y_value",
    "mid_top_hinge_hole_2_y_value", "mid_bottom_hinge_hole_1_y_value", "mid_bottom_hinge_hole_2_y_value",
    "bottom_hinge_hole_1_y_value", "bottom_hinge_hole_2_y_value"
]

# Mapping from expected CSV column names to actual JSON parameter names (if different)
PARAM_NAME_MAPPING = {
    "ceiling_clearance": "component_ceiling_clearance"
}

def load_expected_data(csv_path):
    """Load expected values from CSV into a dict keyed by scenario."""
    expected = {}
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            scenario = row.get('Scenario', '').strip()
            if scenario:
                expected[scenario] = row
    return expected

def load_actual_data(json_path):
    """Load actual values from the JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Extract values from user_parameters
    actual = {}
    user_params = data.get('user_parameters', {})
    for param_name, param_data in user_params.items():
        if isinstance(param_data, dict) and 'value' in param_data:
            actual[param_name] = param_data['value']
    
    return actual

def compare_values(expected_val, actual_val, tolerance=0.0001):
    """Compare two values, handling numeric comparisons with tolerance."""
    try:
        exp_float = float(expected_val)
        act_float = float(actual_val)
        if abs(exp_float - act_float) < tolerance:
            return "correct"
        else:
            return "incorrect"
    except (ValueError, TypeError):
        # String comparison
        if str(expected_val).strip() == str(actual_val).strip():
            return "correct"
        else:
            return "incorrect"

def compare_scenario(scenario_name, expected_data, actual_output_dir):
    """Compare a single scenario and return list of comparison rows."""
    results = []
    
    # Get expected row for this scenario
    expected_row = expected_data.get(scenario_name)
    if not expected_row:
        print(f"Warning: No expected data found for {scenario_name}")
        return results
    
    # Load actual JSON
    actual_json_path = os.path.join(actual_output_dir, scenario_name, "D1_all_parameters.json")
    if not os.path.exists(actual_json_path):
        print(f"Warning: No actual output found for {scenario_name}")
        return results
    
    actual_data = load_actual_data(actual_json_path)
    
    # Compare each parameter
    for param in PARAMETERS_TO_COMPARE:
        expected_val = expected_row.get(param, "N/A")
        
        # Map parameter name if needed
        actual_param_name = PARAM_NAME_MAPPING.get(param, param)
        actual_val = actual_data.get(actual_param_name, "N/A")
        
        comparison = compare_values(expected_val, actual_val)
        
        results.append({
            "Scenario": scenario_name,
            "Parameter": param,
            "Expected": expected_val,
            "Actual": actual_val,
            "Result": comparison
        })
    
    return results

def main(scenarios_to_run=None):
    """Main function to run comparison."""
    # Load expected data
    print(f"Loading expected data from {EXPECTED_CSV_PATH}")
    expected_data = load_expected_data(EXPECTED_CSV_PATH)
    print(f"Loaded {len(expected_data)} expected scenarios")
    
    # Determine which scenarios to run
    if scenarios_to_run is None:
        # Default to first scenario only
        scenarios_to_run = ["3X8X_DV_0001"]
    
    all_results = []
    
    for scenario in scenarios_to_run:
        print(f"Comparing {scenario}...")
        results = compare_scenario(scenario, expected_data, ACTUAL_OUTPUT_DIR)
        all_results.extend(results)
    
    # Write results to CSV
    print(f"Writing results to {COMPARISON_OUTPUT_PATH}")
    with open(COMPARISON_OUTPUT_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["Scenario", "Parameter", "Expected", "Actual", "Result"])
        writer.writeheader()
        writer.writerows(all_results)
    
    # Summary
    correct_count = sum(1 for r in all_results if r["Result"] == "correct")
    incorrect_count = sum(1 for r in all_results if r["Result"] == "incorrect")
    print(f"\nSummary:")
    print(f"  Total parameters compared: {len(all_results)}")
    print(f"  Correct: {correct_count}")
    print(f"  Incorrect: {incorrect_count}")
    
    return all_results

if __name__ == "__main__":
    # Auto-detect all available scenario folders
    import os
    scenarios = sorted([
        d for d in os.listdir(ACTUAL_OUTPUT_DIR)
        if os.path.isdir(os.path.join(ACTUAL_OUTPUT_DIR, d)) and d.startswith("3X8X_DV_")
    ])
    print(f"Found {len(scenarios)} scenario folders")
    main(scenarios)
