"""Compare rabbeting parameters between expected output and actual Test 2 results."""
import csv
from pathlib import Path

expected_path = Path(r'c:\Users\james.derrod\VM Fusion Extension\testing_suite\expected_output\3X82 Stile inputs & outputs v15 macro_enabled 2026_02_26(ValidationOutputs)(1).csv')
actual_dir = Path(r'c:\Users\james.derrod\VM Fusion Extension\testing_suite\stile_validation_tests\Test 2')

# Load expected
with open(expected_path, 'r') as f:
    reader = csv.reader(f)
    header = next(reader)
    expected_rows = {row[0]: dict(zip(header, row)) for row in reader}

scenario_map = {
    'S1': '3X82_SV_0010',
    'S2': '3X82_SV_0011',
    'S3': '3X82_SV_0016',
    'S4': '3X82_SV_0017',
    'S5': '3X82_SV_0018',
    'S6': '3X82_SV_0020',
    'S7': '3X82_SV_0022',
    'S8': '3X82_SV_0049',
}

rabbet_params = [
    'left_side_door', 'LD_hinging_right', 'LD_swinging_out', 'LD_height', 'LD_floor_clearance',
    'left_interior_rabbeting', 'left_exterior_rabbeting', 'left_rabbeting_activation_offset',
    'LD_full_rabbeting_top', 'LD_full_rabbeting_bottom',
    'left_rabbeting_top', 'left_rabbeting_bottom', 'left_rabbeting_length',
    'right_side_door', 'RD_hinging_right', 'RD_swinging_out', 'RD_height', 'RD_floor_clearance',
    'right_interior_rabbeting', 'right_exterior_rabbeting', 'right_rabbeting_activation_offset',
    'RD_full_rabbeting_top', 'RD_full_rabbeting_bottom',
    'right_rabbeting_top', 'right_rabbeting_bottom', 'right_rabbeting_length',
    'through_rabbeting_threshold', 'component_height', 'component_net_height',
]

for comp_id, scenario_id in scenario_map.items():
    actual_file = actual_dir / f'{comp_id}_all_parameters.csv'
    if not actual_file.exists():
        print(f'{comp_id} ({scenario_id}): MISSING actual file')
        continue

    actual_params = {}
    with open(actual_file, 'r') as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if len(row) >= 3:
                actual_params[row[1]] = row[2]

    exp = expected_rows.get(scenario_id, {})
    if not exp:
        print(f'{comp_id} ({scenario_id}): MISSING in expected CSV')
        continue

    print(f'\n{"="*60}')
    print(f' {comp_id} ({scenario_id})')
    print(f'{"="*60}')

    # Print key info
    ch = actual_params.get('component_height', '?')
    nh = actual_params.get('component_net_height', '?')
    thr = actual_params.get('through_rabbeting_threshold', '?')
    print(f'  Height={ch}, NetHeight={nh}, Threshold={thr}')
    print()

    for side in ['left', 'right']:
        prefix = 'LD' if side == 'left' else 'RD'
        door = actual_params.get(f'{side}_side_door', '0')
        swing = actual_params.get(f'{prefix}_swinging_out', '?')
        hinge = actual_params.get(f'{prefix}_hinging_right', '?')
        height = actual_params.get(f'{prefix}_height', '?')
        fc = actual_params.get(f'{prefix}_floor_clearance', '?')
        int_rab = actual_params.get(f'{side}_interior_rabbeting', '0')
        ext_rab = actual_params.get(f'{side}_exterior_rabbeting', '0')
        offset = actual_params.get(f'{side}_rabbeting_activation_offset', '?')
        full_top = actual_params.get(f'{prefix}_full_rabbeting_top', '?')
        full_bot = actual_params.get(f'{prefix}_full_rabbeting_bottom', '?')
        rab_top = actual_params.get(f'{side}_rabbeting_top', '?')
        rab_bot = actual_params.get(f'{side}_rabbeting_bottom', '?')
        rab_len = actual_params.get(f'{side}_rabbeting_length', '?')

        # Expected values
        exp_full_top = exp.get(f'{prefix}_full_rabbeting_top', '')
        exp_full_bot = exp.get(f'{prefix}_full_rabbeting_bottom', '')
        exp_int_rab = exp.get(f'{side}_interior_rabbeting', '')
        exp_ext_rab = exp.get(f'{side}_exterior_rabbeting', '')
        exp_offset = exp.get(f'{side}_rabbeting_activation_offset', '')

        ft_match = ''
        try:
            if exp_full_top and abs(float(exp_full_top) - float(full_top)) > 0.001:
                ft_match = ' ** MISMATCH **'
        except:
            pass
        fb_match = ''
        try:
            if exp_full_bot and abs(float(exp_full_bot) - float(full_bot)) > 0.001:
                fb_match = ' ** MISMATCH **'
        except:
            pass

        print(f'  {side.upper()} SIDE:')
        print(f'    door={door}, swing_out={swing}, hinge_right={hinge}')
        print(f'    door_height={height}, floor_clearance={fc}')
        print(f'    interior_rab={int_rab} (exp={exp_int_rab}), exterior_rab={ext_rab} (exp={exp_ext_rab})')
        print(f'    activation_offset={offset} (exp={exp_offset})')
        print(f'    full_rabbeting_top={full_top} (exp={exp_full_top}){ft_match}')
        print(f'    full_rabbeting_bottom={full_bot} (exp={exp_full_bot}){fb_match}')
        print(f'    rabbeting_top={rab_top}, rabbeting_bottom={rab_bot}')
        print(f'    rabbeting_length={rab_len}')
        print()
