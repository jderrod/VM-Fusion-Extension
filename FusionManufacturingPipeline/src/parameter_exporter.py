"""
Parameter Exporter for Fusion 360 Manufacturing Pipeline
Exports all model parameters to CSV after parameter application
"""

import adsk.core
import adsk.fusion
import csv
import json
from typing import Tuple, List, Dict
from pathlib import Path


class ParameterExporter:
    """Exports model parameters to CSV files"""
    
    def __init__(self, app: adsk.core.Application, output_dir: str):
        """
        Initialize parameter exporter.
        
        Args:
            app: Fusion Application object
            output_dir: Base directory for exported CSV files
        """
        self.app = app
        self.ui = app.userInterface
        self.output_dir = Path(output_dir)
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def convert_to_display_units(self, value: float, unit: str) -> float:
        """
        Convert parameter value from Fusion's internal units (cm) to display units.
        
        Args:
            value: Parameter value in Fusion's internal units (centimeters)
            unit: Display unit string (e.g., 'in', 'mm', 'cm')
            
        Returns:
            Converted value in display units
        """
        # Fusion internally stores all length values in centimeters
        # Convert to the appropriate display unit
        if unit == 'in':
            # Convert cm to inches: 1 inch = 2.54 cm
            return value / 2.54
        elif unit == 'mm':
            # Convert cm to mm: 1 cm = 10 mm
            return value * 10
        elif unit == 'ft':
            # Convert cm to feet: 1 foot = 30.48 cm
            return value / 30.48
        elif unit == 'm':
            # Convert cm to meters: 1 m = 100 cm
            return value / 100
        else:
            # For cm or unknown units, return as-is
            return value
    
    def export_parameters(self, design: adsk.fusion.Design, component_id: str) -> Tuple[bool, str, str]:
        """
        Export all user parameters to CSV file.
        
        Args:
            design: Design object to export parameters from
            component_id: Component identifier for filename
            
        Returns:
            Tuple of (success: bool, message: str, file_path: str)
        """
        try:
            # Build output filename: component_id_parameters.csv
            output_filename = f"{component_id}_parameters.csv"
            output_path = self.output_dir / output_filename
            
            # Get all user parameters
            user_params = design.userParameters
            
            if user_params.count == 0:
                return False, "No user parameters found in design", ""
            
            # Collect parameter data
            param_data = []
            for param in user_params:
                # Try to get value, fall back to expression if not numeric
                try:
                    raw_value = param.value
                    unit = param.unit if hasattr(param, 'unit') else ''
                    # Convert from Fusion's internal units (cm) to display units
                    value = self.convert_to_display_units(raw_value, unit)
                except Exception:
                    value = param.expression
                    unit = param.unit if hasattr(param, 'unit') else ''
                
                param_info = {
                    'Parameter Name': param.name,
                    'Value': value,
                    'Unit': unit,
                    'Expression': param.expression,
                    'Comment': param.comment if param.comment else ''
                }
                param_data.append(param_info)
            
            # Write to CSV
            with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['Parameter Name', 'Value', 'Unit', 'Expression', 'Comment']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                # Write header
                writer.writeheader()
                
                # Write parameter rows
                for param in param_data:
                    writer.writerow(param)
            
            # Verify file was created
            if output_path.exists():
                param_count = len(param_data)
                file_size = output_path.stat().st_size
                return True, f"Exported {param_count} parameters to {output_filename} ({file_size} bytes)", str(output_path)
            else:
                return False, f"Export completed but file not found: {output_filename}", ""
            
        except Exception as e:
            return False, f"Parameter export failed: {str(e)}", ""
    
    def export_all_parameters(self, design: adsk.fusion.Design, component_id: str, metadata: Dict[str, any] = None) -> Tuple[bool, str, str]:
        """
        Export ALL parameters (user, model, and computed) to CSV file.
        
        Args:
            design: Design object to export parameters from
            component_id: Component identifier for filename
            metadata: Optional dictionary of additional metadata to include (e.g., series_id)
            
        Returns:
            Tuple of (success: bool, message: str, file_path: str)
        """
        try:
            # Build output filename: component_id_all_parameters.csv
            output_filename = f"{component_id}_all_parameters.csv"
            output_path = self.output_dir / output_filename
            
            # Collect all parameter types
            param_data = []
            
            # Add metadata as parameters if provided
            if metadata:
                for key, value in metadata.items():
                    param_info = {
                        'Type': 'Metadata',
                        'Parameter Name': key,
                        'Value': value,
                        'Unit': '',
                        'Expression': str(value),
                        'Comment': 'Input parameter (not in model)'
                    }
                    param_data.append(param_info)
            
            # User parameters
            for param in design.userParameters:
                # Try to get value, fall back to expression if not numeric
                try:
                    raw_value = param.value
                    unit = param.unit if hasattr(param, 'unit') else ''
                    # Convert from Fusion's internal units (cm) to display units
                    value = self.convert_to_display_units(raw_value, unit)
                except Exception:
                    value = param.expression
                    unit = param.unit if hasattr(param, 'unit') else ''
                
                param_info = {
                    'Type': 'User',
                    'Parameter Name': param.name,
                    'Value': value,
                    'Unit': unit,
                    'Expression': param.expression,
                    'Comment': param.comment if param.comment else ''
                }
                param_data.append(param_info)
            
            # Model parameters
            user_param_names = {p.name for p in design.userParameters}
            for param in design.allParameters:
                # Skip user parameters (already added)
                if param.name not in user_param_names:
                    # Try to get value, fall back to expression if not numeric
                    try:
                        raw_value = param.value
                        unit = param.unit if hasattr(param, 'unit') else ''
                        # Convert from Fusion's internal units (cm) to display units
                        value = self.convert_to_display_units(raw_value, unit)
                    except Exception:
                        value = param.expression
                        unit = param.unit if hasattr(param, 'unit') else ''
                    
                    param_info = {
                        'Type': 'Model',
                        'Parameter Name': param.name,
                        'Value': value,
                        'Unit': unit,
                        'Expression': param.expression,
                        'Comment': param.comment if param.comment else ''
                    }
                    param_data.append(param_info)
            
            if len(param_data) == 0:
                return False, "No parameters found in design", ""
            
            # Write to CSV
            with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['Type', 'Parameter Name', 'Value', 'Unit', 'Expression', 'Comment']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                # Write header
                writer.writeheader()
                
                # Write parameter rows
                for param in param_data:
                    writer.writerow(param)
            
            # Verify file was created
            if output_path.exists():
                param_count = len(param_data)
                file_size = output_path.stat().st_size
                return True, f"Exported {param_count} parameters to {output_filename} ({file_size} bytes)", str(output_path)
            else:
                return False, f"Export completed but file not found: {output_filename}", ""
            
        except Exception as e:
            return False, f"Parameter export failed: {str(e)}", ""
    
    def export_all_parameters_json(self, design: adsk.fusion.Design, component_id: str, metadata: Dict[str, any] = None) -> Tuple[bool, str, str]:
        """
        Export ALL parameters (user, model, and computed) to JSON file.
        
        Args:
            design: Design object to export parameters from
            component_id: Component identifier for filename
            metadata: Optional dictionary of additional metadata to include (e.g., series_id)
            
        Returns:
            Tuple of (success: bool, message: str, file_path: str)
        """
        try:
            # Build output filename: component_id_all_parameters.json
            output_filename = f"{component_id}_all_parameters.json"
            output_path = self.output_dir / output_filename
            
            # Collect all parameters
            params_dict = {
                'component_id': component_id,
                'metadata': metadata if metadata else {},
                'user_parameters': {},
                'model_parameters': {}
            }
            
            # User parameters
            for param in design.userParameters:
                try:
                    raw_value = param.value
                    unit = param.unit if hasattr(param, 'unit') else ''
                    # Convert from Fusion's internal units (cm) to display units
                    value = self.convert_to_display_units(raw_value, unit)
                except Exception as e:
                    logger = logging.getLogger('FusionManufacturingPipeline')
                    logger.error(f"Error getting value for parameter {param.name}: {str(e)}")
                    value = str(param.expression)
                    unit = ''
                
                params_dict['user_parameters'][param.name] = {
                    'value': value,
                    'unit': unit,
                    'expression': param.expression,
                    'comment': param.comment if param.comment else ''
                }
            
            # Model parameters (excluding user parameters)
            user_param_names = {p.name for p in design.userParameters}
            for param in design.allParameters:
                if param.name not in user_param_names:
                    try:
                        raw_value = param.value
                        unit = param.unit if hasattr(param, 'unit') else ''
                        # Convert from Fusion's internal units (cm) to display units
                        value = self.convert_to_display_units(raw_value, unit)
                    except Exception:
                        value = str(param.expression)
                        unit = ''
                    
                    params_dict['model_parameters'][param.name] = {
                        'value': value,
                        'unit': unit,
                        'expression': param.expression,
                        'comment': param.comment if param.comment else ''
                    }
            
            # Write to JSON
            with open(output_path, 'w', encoding='utf-8') as jsonfile:
                json.dump(params_dict, jsonfile, indent=2)
            
            # Verify file was created
            if output_path.exists():
                total_params = len(params_dict['user_parameters']) + len(params_dict['model_parameters'])
                file_size = output_path.stat().st_size
                return True, f"Exported {total_params} parameters to {output_filename} ({file_size} bytes)", str(output_path)
            else:
                return False, f"Export completed but file not found: {output_filename}", ""
            
        except Exception as e:
            return False, f"JSON parameter export failed: {str(e)}", ""
    
    def export_drilling_coordinates(self, design: adsk.fusion.Design, component_id: str, order_id: str, component_params: dict = None) -> Tuple[bool, str, str]:
        """
        Export drilling coordinates for hinge holes to a separate JSON file.
        Works for both doors and stiles.
        Includes the X-axis positions of hinge holes and Y-axis distance (hinge_hole_x_dist).
        Output is always in inches.
        
        For doors: Exports all standard hinge hole parameters + door_hinge_hole_y_dist
        For stiles: Conditionally exports left/right drilling based on left_side_door/right_side_door + stile_hinge_hole_y_dist
        
        Args:
            design: Design object to export parameters from
            component_id: Component identifier (e.g., D1, S1)
            order_id: Order identifier (e.g., IBUS366574)
            component_params: Optional dict of component parameters from input JSON
                              (used for stiles to determine which sides need drilling via left_side_door/right_side_door)
            
        Returns:
            Tuple of (success: bool, message: str, file_path: str)
        """
        try:
            # Ensure output directory exists
            self.output_dir.mkdir(parents=True, exist_ok=True)
            
            # Build output filename: 1-component_id-order_id-drilling.json
            output_filename = f"1-{component_id}-{order_id}-drilling.json"
            output_path = self.output_dir / output_filename
            
            # Log what we're searching for
            import logging
            logger = logging.getLogger('FusionManufacturingPipeline')
            logger.info(f'{component_id}: Searching for drilling parameters in design')
            logger.info(f'{component_id}: Output path: {output_path}')
            
            # Determine component type and build parameter list accordingly
            is_stile = component_id.upper().startswith('S')
            drilling_param_names = []
            
            if is_stile:
                # For stiles, use JSON input params (left_side_door/right_side_door) to determine
                # which sides need drilling. The model-computed flags (left_interior_drilling etc.)
                # are unreliable (often remain 0 after parameter update).
                logger.info(f'{component_id}: Stile component detected - checking drilling sides')
                
                capture_left = False
                capture_right = False
                
                if component_params:
                    # Use JSON input params to determine sides
                    left_side_data = component_params.get('left_side_door')
                    right_side_data = component_params.get('right_side_door')
                    
                    if left_side_data is not None:
                        left_val = left_side_data[0] if isinstance(left_side_data, list) else left_side_data
                        capture_left = bool(left_val)
                    if right_side_data is not None:
                        right_val = right_side_data[0] if isinstance(right_side_data, list) else right_side_data
                        capture_right = bool(right_val)
                    
                    logger.info(f'{component_id}: From JSON - left_side_door={capture_left}, right_side_door={capture_right}')
                else:
                    # Fallback: check model-computed boolean flags
                    all_params_dict = {p.name: p for p in list(design.userParameters) + list(design.allParameters)}
                    
                    left_interior = all_params_dict.get('left_interior_drilling')
                    left_exterior = all_params_dict.get('left_exterior_drilling')
                    right_interior = all_params_dict.get('right_interior_drilling')
                    right_exterior = all_params_dict.get('right_exterior_drilling')
                    
                    if left_interior and left_interior.value != 0:
                        capture_left = True
                    if left_exterior and left_exterior.value != 0:
                        capture_left = True
                    if right_interior and right_interior.value != 0:
                        capture_right = True
                    if right_exterior and right_exterior.value != 0:
                        capture_right = True
                    
                    logger.info(f'{component_id}: From model flags - capture_left={capture_left}, capture_right={capture_right}')
                
                # Build parameter list based on flags
                if capture_left:
                    logger.info(f'{component_id}: Capturing LEFT side drilling parameters')
                    drilling_param_names.extend([
                        'LD_stile_top_hinge_hole_1_y_value',
                        'LD_stile_top_hinge_hole_2_y_value',
                        'LD_stile_mid_top_hinge_hole_1_y_value',
                        'LD_stile_mid_top_hinge_hole_2_y_value',
                        'LD_stile_mid_bottom_hinge_hole_1_y_value',
                        'LD_stile_mid_bottom_hinge_hole_2_y_value',
                        'LD_stile_bottom_hinge_hole_1_y_value',
                        'LD_stile_bottom_hinge_hole_2_y_value'
                    ])
                
                if capture_right:
                    logger.info(f'{component_id}: Capturing RIGHT side drilling parameters')
                    drilling_param_names.extend([
                        'RD_stile_top_hinge_hole_1_y_value',
                        'RD_stile_top_hinge_hole_2_y_value',
                        'RD_stile_mid_top_hinge_hole_1_y_value',
                        'RD_stile_mid_top_hinge_hole_2_y_value',
                        'RD_stile_mid_bottom_hinge_hole_1_y_value',
                        'RD_stile_mid_bottom_hinge_hole_2_y_value',
                        'RD_stile_bottom_hinge_hole_1_y_value',
                        'RD_stile_bottom_hinge_hole_2_y_value'
                    ])
                
                if not capture_left and not capture_right:
                    logger.info(f'{component_id}: No drilling required (no door on either side)')
                    return False, f"No drilling required for {component_id} (no door on either side)", ""
            else:
                # For doors, use standard parameter names
                # Note: Parameters in model are named _y_value, but we output them as _x_value
                logger.info(f'{component_id}: Door component detected')
                drilling_param_names = [
                    'top_hinge_hole_1_y_value',
                    'top_hinge_hole_2_y_value',
                    'mid_top_hinge_hole_1_y_value',
                    'mid_top_hinge_hole_2_y_value',
                    'mid_bottom_hinge_hole_1_y_value',
                    'mid_bottom_hinge_hole_2_y_value',
                    'bottom_hinge_hole_1_y_value',
                    'bottom_hinge_hole_2_y_value'
                ]
            
            # Collect drilling parameters
            drilling_data = {
                'component_id': component_id,
                'order_id': order_id,
                'unit': 'in',
                'description': 'Hinge hole drilling coordinates (X and Y-axis positions)',
                'holes': {}
            }
            
            # Search through all parameters (user and model) — deduplicated
            user_param_names_set = {p.name for p in design.userParameters}
            all_params = list(design.userParameters) + [p for p in design.allParameters if p.name not in user_param_names_set]
            logger.info(f'{component_id}: Total parameters in design: {len(all_params)}')
            
            # First, look for the hinge_hole_x_dist parameter (renamed based on component type)
            for param in all_params:
                if param.name == 'hinge_hole_x_dist':
                    logger.info(f'{component_id}: Found hinge_hole_x_dist parameter')
                    try:
                        raw_value = param.value
                        value_in_inches = self.convert_to_display_units(raw_value, 'in')
                        value_in_inches = round(value_in_inches, 3)
                        
                        # Rename based on component type: _x_dist becomes _y_dist
                        if is_stile:
                            output_param_name = 'stile_hinge_hole_y_dist'
                        else:
                            output_param_name = 'door_hinge_hole_y_dist'
                        
                        logger.info(f'{component_id}: Added {output_param_name} = {value_in_inches} in')
                        
                        drilling_data['holes'][output_param_name] = {
                            'value': value_in_inches,
                            'unit': 'in',
                            'expression': param.expression,
                            'comment': param.comment if param.comment else ''
                        }
                    except Exception as e:
                        logger.warning(f'{component_id}: Error reading hinge_hole_x_dist: {str(e)}')
                    break
            
            # Now process the drilling hole parameters
            for param in all_params:
                if param.name in drilling_param_names:
                    logger.info(f'{component_id}: Found drilling parameter: {param.name}')
                    try:
                        # Get raw value from Fusion (in cm)
                        raw_value = param.value
                        # Convert to inches
                        value_in_inches = self.convert_to_display_units(raw_value, 'in')
                        
                        # Round to 3 decimal places for cleaner output
                        value_in_inches = round(value_in_inches, 3)
                        
                        # Rename from _y_value to _x_value in output
                        output_param_name = param.name.replace('_y_value', '_x_value')
                        
                        logger.info(f'{component_id}: Added {output_param_name} = {value_in_inches} in')
                        
                        drilling_data['holes'][output_param_name] = {
                            'value': value_in_inches,
                            'unit': 'in',
                            'expression': param.expression,
                            'comment': param.comment if param.comment else ''
                        }
                    except Exception as e:
                        # If we can't get the value, log it but continue
                        output_param_name = param.name.replace('_y_value', '_x_value')
                        drilling_data['holes'][output_param_name] = {
                            'value': 'ERROR',
                            'unit': 'in',
                            'expression': param.expression,
                            'error': str(e)
                        }
            
            # Check if we found any drilling parameters
            if len(drilling_data['holes']) == 0:
                logger.warning(f'{component_id}: No drilling parameters found! Searched for: {", ".join(drilling_param_names[:3])}...')
                return False, f"No drilling parameters found for {component_id}", ""
            
            # Write to JSON
            with open(output_path, 'w', encoding='utf-8') as jsonfile:
                json.dump(drilling_data, jsonfile, indent=2)
            
            # Verify file was created
            if output_path.exists():
                hole_count = len(drilling_data['holes'])
                file_size = output_path.stat().st_size
                return True, f"Exported {hole_count} drilling coordinates to {output_filename} ({file_size} bytes)", str(output_path)
            else:
                return False, f"Export completed but file not found: {output_filename}", ""
            
        except Exception as e:
            return False, f"Drilling coordinate export failed: {str(e)}", ""
    
    def export_drilling_coordinates_paired(self, design: adsk.fusion.Design, component_id: str, order_id: str, component_params: dict = None) -> Tuple[bool, str, str]:
        """
        Export drilling coordinates in paired X/Y format.
        Each hole is represented as a coordinate pair with additional machine fields.
        
        Args:
            design: Design object to export parameters from
            component_id: Component identifier (e.g., D1, S1)
            order_id: Order identifier (e.g., IBUS366574)
            component_params: Optional dict of component parameters from input JSON
                              (used to determine workstop based on door_hinging_right and door_swinging_out)
            
        Returns:
            Tuple of (success: bool, message: str, file_path: str)
        """
        try:
            from adsk.core import Application
            import json
            from pathlib import Path
            import logging
            import re as _re
            
            logger = logging.getLogger('FusionManufacturingPipeline')
            
            # No individual file output — data is returned for compiled order-level file
            
            # Determine component type
            is_stile = component_id.upper().startswith('S')
            
            # Get the Y-distance value first
            y_dist = None
            user_param_names_set = {p.name for p in design.userParameters}
            all_params = list(design.userParameters) + [p for p in design.allParameters if p.name not in user_param_names_set]
            
            for param in all_params:
                if param.name == 'hinge_hole_x_dist':
                    try:
                        raw_value = param.value
                        y_dist = round(self.convert_to_display_units(raw_value, 'in'), 3)
                        logger.info(f'{component_id}: Found hinge_hole_x_dist = {y_dist} in')
                        break
                    except Exception as e:
                        logger.warning(f'{component_id}: Error reading hinge_hole_x_dist: {str(e)}')
            
            if y_dist is None:
                return False, f"No hinge_hole_x_dist parameter found for {component_id}", ""
            
            # Collect hole coordinates
            hole_pairs = []
            
            # Helper to extract a JSON param value from [value, type, description] format
            def _extract_param(params, key):
                data = params.get(key)
                if data is None:
                    return None
                return data[0] if isinstance(data, list) else data
            
            # Define parameter search based on component type
            if is_stile:
                # For stiles, determine which sides need drilling:
                #   1. There must be a door on that side (left_side_door / right_side_door)
                #   2. The door must hinge ONTO the stile:
                #      - Left side: door must be RH hinging (LD_hinging_right=1)
                #        If LH hinging (LD_hinging_right=0), door hinges away -> no drilling
                #      - Right side: door must be LH hinging (RD_hinging_right=0)
                #        If RH hinging (RD_hinging_right=1), door hinges away -> no drilling
                capture_left = False
                capture_right = False
                
                if component_params:
                    # Check left side
                    left_side_data = component_params.get('left_side_door')
                    if left_side_data is not None:
                        left_has_door = bool(left_side_data[0] if isinstance(left_side_data, list) else left_side_data)
                    else:
                        left_has_door = False
                    
                    if left_has_door:
                        ld_hinging_right = bool(_extract_param(component_params, 'LD_hinging_right'))
                        if ld_hinging_right:
                            capture_left = True
                            logger.info(f'{component_id}: Left side - door present, RH hinging (hinges onto stile) -> drilling required')
                        else:
                            logger.info(f'{component_id}: Left side - door present, LH hinging (hinges away from stile) -> no drilling')
                    else:
                        logger.info(f'{component_id}: Left side - no door -> no drilling')
                    
                    # Check right side
                    right_side_data = component_params.get('right_side_door')
                    if right_side_data is not None:
                        right_has_door = bool(right_side_data[0] if isinstance(right_side_data, list) else right_side_data)
                    else:
                        right_has_door = False
                    
                    if right_has_door:
                        rd_hinging_right = bool(_extract_param(component_params, 'RD_hinging_right'))
                        if not rd_hinging_right:
                            capture_right = True
                            logger.info(f'{component_id}: Right side - door present, LH hinging (hinges onto stile) -> drilling required')
                        else:
                            logger.info(f'{component_id}: Right side - door present, RH hinging (hinges away from stile) -> no drilling')
                    else:
                        logger.info(f'{component_id}: Right side - no door -> no drilling')
                    
                    logger.info(f'{component_id}: Drilling sides - capture_left={capture_left}, capture_right={capture_right}')
                else:
                    # Fallback: check model-computed boolean flags
                    for param in all_params:
                        if param.name in ['left_interior_drilling', 'left_exterior_drilling']:
                            if hasattr(param, 'value') and param.value > 0:
                                capture_left = True
                        elif param.name in ['right_interior_drilling', 'right_exterior_drilling']:
                            if hasattr(param, 'value') and param.value > 0:
                                capture_right = True
                    logger.info(f'{component_id}: From model flags - capture_left={capture_left}, capture_right={capture_right}')
                
                if not capture_left and not capture_right:
                    return False, f"No drilling required for {component_id} (no door hinges onto stile)", ""
                
                # Build parameter list based on flags, grouped by side for per-side workstop
                # All stiles use the standard *_y_value params (measured from top).
                # 3086 stiles additionally receive a 1.4375" offset on the drill X position.
                early_series_id = str(_extract_param(component_params, 'series_id') or '') if component_params else ''
                # Normalize series code: 2nd digit is a generation indicator
                # (e.g. '3186' -> '3086', '3182' -> '3082')
                _series_match = _re.search(r'(3\d{3})', early_series_id)
                _normalized = (_series_match.group(1)[0] + '0' + _series_match.group(1)[2:]) if _series_match else ''
                is_3086 = _normalized == '3086'
                suffix = '_y_value'
                if is_3086:
                    logger.info(f'{component_id}: 3086 stile - applying 1.4375" drill X offset')
                
                left_drilling_params = []
                right_drilling_params = []
                if capture_left:
                    left_drilling_params = [
                        f'LD_stile_top_hinge_hole_1{suffix}',
                        f'LD_stile_top_hinge_hole_2{suffix}',
                        f'LD_stile_mid_top_hinge_hole_1{suffix}',
                        f'LD_stile_mid_top_hinge_hole_2{suffix}',
                        f'LD_stile_mid_bottom_hinge_hole_1{suffix}',
                        f'LD_stile_mid_bottom_hinge_hole_2{suffix}',
                        f'LD_stile_bottom_hinge_hole_1{suffix}',
                        f'LD_stile_bottom_hinge_hole_2{suffix}'
                    ]
                if capture_right:
                    right_drilling_params = [
                        f'RD_stile_top_hinge_hole_1{suffix}',
                        f'RD_stile_top_hinge_hole_2{suffix}',
                        f'RD_stile_mid_top_hinge_hole_1{suffix}',
                        f'RD_stile_mid_top_hinge_hole_2{suffix}',
                        f'RD_stile_mid_bottom_hinge_hole_1{suffix}',
                        f'RD_stile_mid_bottom_hinge_hole_2{suffix}',
                        f'RD_stile_bottom_hinge_hole_1{suffix}',
                        f'RD_stile_bottom_hinge_hole_2{suffix}'
                    ]
                drilling_param_names = left_drilling_params + right_drilling_params
            else:
                # Door parameters
                drilling_param_names = [
                    'top_hinge_hole_1_y_value',
                    'top_hinge_hole_2_y_value',
                    'mid_top_hinge_hole_1_y_value',
                    'mid_top_hinge_hole_2_y_value',
                    'mid_bottom_hinge_hole_1_y_value',
                    'mid_bottom_hinge_hole_2_y_value',
                    'bottom_hinge_hole_1_y_value',
                    'bottom_hinge_hole_2_y_value'
                ]
            
            # Determine workstop value and DrillName
            # Door workstop logic:
            #   LH + in swing (hinging_right=0, swinging_out=0) -> workstop=1
            #   RH + out swing (hinging_right=1, swinging_out=1) -> workstop=1
            #   RH + in swing (hinging_right=1, swinging_out=0) -> workstop=4
            #   LH + out swing (hinging_right=0, swinging_out=1) -> workstop=4
            # Stile workstop is INVERTED from the door workstop.
            
            def _compute_door_workstop(hinging_right, swinging_out):
                """Compute workstop for doors from hinging/swinging values."""
                if bool(hinging_right) == bool(swinging_out):
                    return 1
                else:
                    return 4
            
            def _compute_stile_workstop(hinging_right, swinging_out):
                """Compute workstop for 3082/3081 stiles (inverted from door)."""
                if bool(hinging_right) == bool(swinging_out):
                    return 4
                else:
                    return 1
            
            def _compute_3086_stile_workstop(hinging_right, swinging_out):
                """Compute workstop for 3086 stiles (same as door, opposite of 3082)."""
                if bool(hinging_right) == bool(swinging_out):
                    return 1
                else:
                    return 4
            
            # For stiles, compute per-side workstop/DrillName
            # For doors, compute a single workstop/DrillName
            workstop = 1
            drill_name = ''
            left_workstop = 1
            left_drill_name = ''
            right_workstop = 1
            right_drill_name = ''
            series_id = ''
            
            if component_params:
                series_id = str(_extract_param(component_params, 'series_id') or '')
                # Normalize series code: 2nd digit is a generation indicator
                # (e.g. '3186' -> '3086', '3182' -> '3082')
                _ws_match = _re.search(r'(3\d{3})', series_id)
                _ws_normalized = (_ws_match.group(1)[0] + '0' + _ws_match.group(1)[2:]) if _ws_match else ''
                
                # Use program_name from input JSON as DrillName if available
                json_program_name = str(_extract_param(component_params, 'program_name') or '').strip() if component_params else ''
                
                if is_stile:
                    # Per-side workstop for stiles
                    # 3086 stiles use OPPOSITE workstop selection from 3082/3081:
                    #   3082/3081: same==4, different==1 (inverted from door)
                    #   3086:      same==1, different==4 (same as door)
                    is_3086 = _ws_normalized == '3086'
                    stile_ws_func = _compute_3086_stile_workstop if is_3086 else _compute_stile_workstop
                    if is_3086:
                        logger.info(f'{component_id}: Using 3086 workstop logic (same as door)')
                    
                    # Left side workstop
                    left_side_data = component_params.get('left_side_door')
                    left_has_door = bool(left_side_data[0] if isinstance(left_side_data, list) else left_side_data) if left_side_data is not None else False
                    
                    if left_has_door and capture_left:
                        ld_hinging = bool(_extract_param(component_params, 'LD_hinging_right'))
                        ld_swinging = bool(_extract_param(component_params, 'LD_swinging_out'))
                        left_workstop = stile_ws_func(ld_hinging, ld_swinging)
                        logger.info(f'{component_id}: LEFT side - workstop={left_workstop}')
                    
                    # Right side workstop
                    right_side_data = component_params.get('right_side_door')
                    right_has_door = bool(right_side_data[0] if isinstance(right_side_data, list) else right_side_data) if right_side_data is not None else False
                    
                    if right_has_door and capture_right:
                        rd_hinging = bool(_extract_param(component_params, 'RD_hinging_right'))
                        rd_swinging = bool(_extract_param(component_params, 'RD_swinging_out'))
                        right_workstop = stile_ws_func(rd_hinging, rd_swinging)
                        logger.info(f'{component_id}: RIGHT side - workstop={right_workstop}')
                    
                    # DrillName: use program_name from JSON, fall back to computed name
                    if json_program_name:
                        left_drill_name = json_program_name
                        right_drill_name = json_program_name
                        logger.info(f'{component_id}: Stile DrillName from JSON program_name="{json_program_name}"')
                    else:
                        # Fallback: compute from hinging/swinging
                        left_segment = ''
                        right_segment = ''
                        if left_has_door:
                            ld_hinging = bool(_extract_param(component_params, 'LD_hinging_right'))
                            ld_swinging = bool(_extract_param(component_params, 'LD_swinging_out'))
                            hinge_code = 'RH' if ld_hinging else 'LH'
                            swing_code = 'O/S' if ld_swinging else 'I/S'
                            attach_code = 'HINGE' if capture_left else 'KEEPING'
                            left_segment = f'{hinge_code} {swing_code} {attach_code}'
                        if right_has_door:
                            rd_hinging = bool(_extract_param(component_params, 'RD_hinging_right'))
                            rd_swinging = bool(_extract_param(component_params, 'RD_swinging_out'))
                            hinge_code = 'RH' if rd_hinging else 'LH'
                            swing_code = 'O/S' if rd_swinging else 'I/S'
                            attach_code = 'HINGE' if capture_right else 'KEEPING'
                            right_segment = f'{hinge_code} {swing_code} {attach_code}'
                        drill_segments = [s for s in [left_segment, right_segment] if s]
                        combined_drill_name = f'{series_id} {" | ".join(drill_segments)}'
                        left_drill_name = combined_drill_name
                        right_drill_name = combined_drill_name
                        logger.info(f'{component_id}: Stile DrillName (computed)="{combined_drill_name}"')
                else:
                    # Door workstop
                    hinging_right = bool(_extract_param(component_params, 'door_hinging_right'))
                    swinging_out = bool(_extract_param(component_params, 'door_swinging_out'))
                    workstop = _compute_door_workstop(hinging_right, swinging_out)
                    
                    # DrillName: use program_name from JSON, fall back to computed name
                    if json_program_name:
                        drill_name = json_program_name
                        logger.info(f'{component_id}: Door DrillName from JSON program_name="{json_program_name}", workstop={workstop}')
                    else:
                        hinge_code = 'RH' if hinging_right else 'LH'
                        swing_code = 'O/S' if swinging_out else 'I/S'
                        drill_name = f'{series_id} {hinge_code} {swing_code} DOOR'
                        logger.info(f'{component_id}: Door DrillName (computed)="{drill_name}", workstop={workstop}')
            
            # Determine FlipRotate value
            # Doors: always 1 (rotate)
            # Stiles: read model flags left_interior_drilling, left_exterior_drilling,
            #         right_interior_drilling, right_exterior_drilling.
            #   Both exterior or both interior -> 1 (rotate) for all holes
            #   Mixed interior/exterior -> per-hole: 3 for exterior holes, 4 for interior holes
            #   Single side only -> 1 (rotate)
            #   Value 2 (flip) is no longer used.
            left_flip_rotate = 1
            right_flip_rotate = 1
            if is_stile:
                all_params_dict = {p.name: p for p in all_params}
                li = all_params_dict.get('left_interior_drilling')
                le = all_params_dict.get('left_exterior_drilling')
                ri = all_params_dict.get('right_interior_drilling')
                re = all_params_dict.get('right_exterior_drilling')
                li_val = 1 if (li and li.value != 0) else 0
                le_val = 1 if (le and le.value != 0) else 0
                ri_val = 1 if (ri and ri.value != 0) else 0
                re_val = 1 if (re and re.value != 0) else 0
                logger.info(f'{component_id}: Drilling flags - LI={li_val}, LE={le_val}, RI={ri_val}, RE={re_val}')
                
                # Determine if we have mixed interior/exterior across sides
                has_any_interior = li_val or ri_val
                has_any_exterior = le_val or re_val
                mixed = has_any_interior and has_any_exterior
                
                if mixed:
                    # Per-hole FlipRotate: 3 for exterior, 4 for interior
                    left_flip_rotate = 4 if li_val else 3  # left interior -> 4, left exterior -> 3
                    right_flip_rotate = 4 if ri_val else 3  # right interior -> 4, right exterior -> 3
                    logger.info(f'{component_id}: Mixed drilling - left FlipRotate={left_flip_rotate}, right FlipRotate={right_flip_rotate}')
                else:
                    # All same type (or single side) -> rotate (1)
                    left_flip_rotate = 1
                    right_flip_rotate = 1
                    logger.info(f'{component_id}: FlipRotate=1 (rotate)')
                
                flip_rotate = 1  # default for door-path / fallback
            else:
                flip_rotate = 1
                logger.info(f'{component_id}: FlipRotate=1 (rotate, door)')
            
            # Get current timestamp for when this piece is processed
            from datetime import datetime
            process_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Extract X values for each hole
            for param in all_params:
                if param.name in drilling_param_names:
                    try:
                        raw_value = param.value
                        x_value = round(self.convert_to_display_units(raw_value, 'in'), 3)
                        
                        # 3086 stiles require an additional 1.4375" offset on the
                        # drill X position (derived from the model _y_value).
                        if is_stile and is_3086:
                            x_value = round(x_value - 1.4375, 3)
                        
                        # Extract hole name (remove _y_value or _y_value_from_bottom suffix)
                        hole_name = param.name.replace('_y_value_from_bottom', '').replace('_y_value', '')
                        
                        # Determine per-side workstop/DrillName/FlipRotate for stiles
                        if is_stile and param.name in left_drilling_params:
                            hole_ws = left_workstop
                            hole_dn = left_drill_name
                            hole_fr = left_flip_rotate
                        elif is_stile and param.name in right_drilling_params:
                            hole_ws = right_workstop
                            hole_dn = right_drill_name
                            hole_fr = right_flip_rotate
                        else:
                            hole_ws = workstop
                            hole_dn = drill_name
                            hole_fr = flip_rotate
                        
                        hole_pairs.append({
                            'ProgramName': f'1-{component_id}-{order_id}',
                            'WorkStop': hole_ws,
                            'PositionX': x_value,
                            'PositionY': y_dist,
                            'PositionZ': None,
                            'Function': 4,
                            'ToolDM': 1,
                            'FlipRotate': hole_fr,
                            'SSMA_TimeStamp': None,
                            'Fusion_TimeStamp': process_timestamp,
                            'DrillName': hole_dn
                        })
                    except Exception as e:
                        logger.warning(f'{component_id}: Error reading {param.name}: {str(e)}')
            
            if len(hole_pairs) == 0:
                # No drilling required — emit air drilling entries at both workstops
                from datetime import datetime as _dt
                _ts = _dt.now().strftime('%Y-%m-%d %H:%M:%S')
                for ws in (1, 4):
                    hole_pairs.append({
                        'ProgramName': f'1-{component_id}-{order_id}',
                        'WorkStop': ws,
                        'PositionX': 121,
                        'PositionY': 0.197,
                        'PositionZ': None,
                        'Function': 4,
                        'ToolDM': 1,
                        'FlipRotate': 1,
                        'SSMA_TimeStamp': None,
                        'Fusion_TimeStamp': _ts,
                        'DrillName': 'NO DRILLING REQUIRED'
                    })
                logger.info(f'{component_id}: No drilling required — added air drilling entries at workstops 1 and 4')
            
            # Air drilling: if only one workstop is used, add an air drilling
            # entry on the opposite workstop at safe coordinates (121, 0.197).
            # This ensures the machine cycles both workstops even when real
            # drilling only exists on one side.
            # Skip air drilling when any hole has FlipRotate of 2 or 3
            # (mixed interior/exterior scenarios handle both sides already).
            AIR_DRILL_X = 121
            AIR_DRILL_Y = 0.197
            flip_rotate_values = set(h['FlipRotate'] for h in hole_pairs)
            skip_air_drill = bool(flip_rotate_values & {2, 3})
            if skip_air_drill:
                logger.info(f'{component_id}: Skipping air drilling — FlipRotate includes {flip_rotate_values & {2, 3}}')
            workstop_values = set(h['WorkStop'] for h in hole_pairs)
            if len(workstop_values) == 1 and not skip_air_drill:
                used_ws = workstop_values.pop()
                opposite_ws = 4 if used_ws == 1 else 1
                ref = hole_pairs[0]  # copy metadata from first hole
                hole_pairs.append({
                    'ProgramName': ref['ProgramName'],
                    'WorkStop': opposite_ws,
                    'PositionX': AIR_DRILL_X,
                    'PositionY': AIR_DRILL_Y,
                    'PositionZ': None,
                    'Function': ref['Function'],
                    'ToolDM': ref['ToolDM'],
                    'FlipRotate': ref['FlipRotate'],
                    'SSMA_TimeStamp': ref['SSMA_TimeStamp'],
                    'Fusion_TimeStamp': ref['Fusion_TimeStamp'],
                    'DrillName': 'NO DRILLING REQUIRED'
                })
                logger.info(f'{component_id}: Only workstop {used_ws} used, added air drilling entry on workstop {opposite_ws} at ({AIR_DRILL_X}, {AIR_DRILL_Y})')
            
            # Build output structure (returned for compiled order-level file)
            paired_data = {
                'component_id': component_id,
                'order_id': order_id,
                'unit': 'in',
                'description': 'Paired drilling coordinates (X, Y)',
                'coordinates': hole_pairs
            }
            
            hole_count = len(hole_pairs)
            return True, f"Computed {hole_count} paired coordinates for {component_id}", paired_data
            
        except Exception as e:
            return False, f"Paired drilling coordinate export failed: {str(e)}", ""
    
    def export_cutlist_csv(self, design: adsk.fusion.Design, component_id: str, order_id: str,
                           component_params: dict = None, component_type: str = None) -> Tuple[bool, str, str]:
        """
        Export cutlist data in gCutlist format to CSV file for voorwood/tenoner.
        Output format has two columns: Variable Name (A) and Value (B).
        
        Supports stiles and doors. Side mapping:
            Side1 = right edge (looking from outside)
            Side2 = left edge
            Side3 = top edge
            Side4 = bottom edge
        
        Args:
            design: Design object to export parameters from
            component_id: Component identifier (e.g., S1, D1)
            order_id: Order identifier (e.g., IBUS128913)
            component_params: Dict of component parameters from input JSON
            component_type: Type string ('stile' or 'door')
            
        Returns:
            Tuple of (success: bool, message: str, file_path: str)
        """
        try:
            import logging
            logger = logging.getLogger('FusionManufacturingPipeline')
            
            # Build output filename: 1-component_id-order_id.csv (e.g., 1-S1-3X82_SV_0967.csv)
            output_filename = f"1-{component_id}-{order_id}.csv"
            output_path = self.output_dir / output_filename
            
            logger.info(f'{component_id}: Exporting cutlist CSV to {output_path}')
            
            # Helper to extract a JSON param value from [value, type, description] format
            def _extract_param(key, default=None):
                if not component_params:
                    return default
                data = component_params.get(key)
                if data is None:
                    return default
                val = data[0] if isinstance(data, list) else data
                return val if val is not None else default
            
            # Get parameters from design
            all_params = {p.name: p for p in list(design.userParameters) + list(design.allParameters)}
            
            # Helper to read a model parameter value in inches
            def _get_model_param(name, default=0):
                param = all_params.get(name)
                if param:
                    try:
                        return round(self.convert_to_display_units(param.value, 'in'), 4)
                    except Exception as e:
                        logger.warning(f'{component_id}: Error reading {name}: {str(e)}')
                return default
            
            # Helper to read a model parameter raw value (for booleans stored as 0/1)
            def _get_model_bool(name, default=0):
                param = all_params.get(name)
                if param:
                    try:
                        return 1 if param.value != 0 else 0
                    except Exception:
                        pass
                return default
            
            is_stile = component_type == 'stile' if component_type else component_id.upper().startswith('S')
            
            # --- Width and Length ---
            width_param = all_params.get('component_width')
            width_value = round(self.convert_to_display_units(width_param.value, 'in'), 4) if width_param else 0
            
            height_param = all_params.get('component_height')
            length_value = round(self.convert_to_display_units(height_param.value, 'in'), 4) if height_param else 0
            
            logger.info(f'{component_id}: Width={width_value}, Length={length_value}')
            
            # --- Series ID ---
            series_id = str(_extract_param('series_id', ''))
            
            # --- Floor clearance ---
            if is_stile:
                # For stiles, FC could be LD or RD floor clearance; use whichever side has a door
                # Prefer the side that has a door, or the first available
                fc_value = ''
                ld_fc = _extract_param('LD_floor_clearance')
                rd_fc = _extract_param('RD_floor_clearance')
                left_has_door = bool(_extract_param('left_side_door', False))
                right_has_door = bool(_extract_param('right_side_door', False))
                if right_has_door and rd_fc is not None:
                    fc_value = str(rd_fc)
                elif left_has_door and ld_fc is not None:
                    fc_value = str(ld_fc)
                elif ld_fc is not None:
                    fc_value = str(ld_fc)
                elif rd_fc is not None:
                    fc_value = str(rd_fc)
            else:
                # Door: component_floor_clearance from JSON or model
                fc_val = _extract_param('component_floor_clearance')
                if fc_val is not None:
                    fc_value = str(fc_val)
                else:
                    fc_value = str(_get_model_param('component_floor_clearance', 0))
            
            # --- RoutingInformation (same pattern as DrillName in drilling export) ---
            if is_stile:
                # Build per-side routing info, combine if both sides present
                routing_parts = []
                if bool(_extract_param('left_side_door', False)):
                    ld_hinging = bool(_extract_param('LD_hinging_right', False))
                    ld_swinging = bool(_extract_param('LD_swinging_out', False))
                    hinge_code = 'RH' if ld_hinging else 'LH'
                    swing_code = 'OS' if ld_swinging else 'IS'
                    routing_parts.append(f'{series_id} {hinge_code} {swing_code}')
                if bool(_extract_param('right_side_door', False)):
                    rd_hinging = bool(_extract_param('RD_hinging_right', False))
                    rd_swinging = bool(_extract_param('RD_swinging_out', False))
                    hinge_code = 'RH' if rd_hinging else 'LH'
                    swing_code = 'OS' if rd_swinging else 'IS'
                    routing_parts.append(f'{series_id} {hinge_code} {swing_code}')
                routing_info = ' / '.join(routing_parts) if routing_parts else ''
            else:
                # Door
                hinging_right = bool(_extract_param('door_hinging_right', False))
                swinging_out = bool(_extract_param('door_swinging_out', False))
                hinge_code = 'RH' if hinging_right else 'LH'
                swing_code = 'OS' if swinging_out else 'IS'
                routing_info = f'{series_id} {hinge_code} {swing_code}'
            
            # --- Gapping (rabbeting) per side ---
            # Side1 = right, Side2 = left, Side3 = top (always 0), Side4 = bottom (always 0)
            if is_stile:
                gapping_side1 = 1 if bool(_extract_param('right_side_door', False)) else 0
                gapping_side2 = 1 if bool(_extract_param('left_side_door', False)) else 0
            else:
                # Door: check if rabbeting exists on left/right from model
                has_left_rabbeting = _get_model_bool('left_interior_rabbeting') or _get_model_bool('left_exterior_rabbeting')
                has_right_rabbeting = _get_model_bool('right_interior_rabbeting') or _get_model_bool('right_exterior_rabbeting')
                gapping_side1 = 1 if has_right_rabbeting else 0
                gapping_side2 = 1 if has_left_rabbeting else 0
            gapping_side3 = 0
            gapping_side4 = 0
            
            # --- EdgeFinishing = inverse of Gapping ---
            edge_finishing_side1 = 0 if gapping_side1 else 1
            edge_finishing_side2 = 0 if gapping_side2 else 1
            edge_finishing_side3 = 1  # top always edge finished (no gapping)
            edge_finishing_side4 = 1  # bottom always edge finished (no gapping)
            
            # --- GappingStart and GappingLength ---
            if is_stile:
                # Side1 (right): right_rabbeting_top / right_rabbeting_length
                gapping_start_side1 = _get_model_param('right_rabbeting_top', 0) if gapping_side1 else 0
                gapping_length_side1 = _get_model_param('right_rabbeting_length', 0) if gapping_side1 else 0
                # Side2 (left): left_rabbeting_top / left_rabbeting_length
                gapping_start_side2 = _get_model_param('left_rabbeting_top', 0) if gapping_side2 else 0
                gapping_length_side2 = _get_model_param('left_rabbeting_length', 0) if gapping_side2 else 0
            else:
                # Door: no rabbeting start/length params in door model for this CSV
                # (door rabbeting runs full length, so start=0, length=component_height)
                gapping_start_side1 = 0
                gapping_length_side1 = length_value if gapping_side1 else 0
                gapping_start_side2 = 0
                gapping_length_side2 = length_value if gapping_side2 else 0
            gapping_start_side3 = 0
            gapping_start_side4 = 0
            gapping_length_side3 = 0
            gapping_length_side4 = 0
            
            # --- GappingTop (1 = exterior/top face, 0 = interior/bottom face) ---
            if is_stile:
                # Side1 (right): exterior rabbeting = top face (1), interior = bottom (0)
                if gapping_side1:
                    gapping_top_side1 = 1 if _get_model_bool('right_exterior_rabbeting') else 0
                else:
                    gapping_top_side1 = 0
                # Side2 (left): exterior rabbeting = top face (1), interior = bottom (0)
                if gapping_side2:
                    gapping_top_side2 = 1 if _get_model_bool('left_exterior_rabbeting') else 0
                else:
                    gapping_top_side2 = 0
            else:
                # Door
                if gapping_side1:
                    gapping_top_side1 = 1 if _get_model_bool('right_exterior_rabbeting') else 0
                else:
                    gapping_top_side1 = 0
                if gapping_side2:
                    gapping_top_side2 = 1 if _get_model_bool('left_exterior_rabbeting') else 0
                else:
                    gapping_top_side2 = 0
            gapping_top_side3 = 0
            gapping_top_side4 = 0
            
            # --- Thickness ---
            thickness = _get_model_param('component_thickness', 0.75)
            
            # Build cutlist data rows
            cutlist_data = [
                ('gCutlist.Item[0].Qty', '1'),
                ('gCutlist.Item[0].Width', str(width_value)),
                ('gCutlist.Item[0].Length', str(length_value)),
                ('gCutlist.Item[0].ID', component_id),
                ('gCutlist.Item[0].Series', series_id),
                ('gCutlist.Item[0].RoutingInformation', routing_info),
                ('gCutlist.Item[0].SO', order_id),
                ('gCutlist.Item[0].FC', fc_value),
                ('gCutlist.Item[0].GappingSide1', str(gapping_side1)),
                ('gCutlist.Item[0].GappingSide2', str(gapping_side2)),
                ('gCutlist.Item[0].GappingSide3', str(gapping_side3)),
                ('gCutlist.Item[0].GappingSide4', str(gapping_side4)),
                ('gCutlist.Item[0].EdgeFinishingSide1', str(edge_finishing_side1)),
                ('gCutlist.Item[0].EdgeFinishingSide2', str(edge_finishing_side2)),
                ('gCutlist.Item[0].EdgeFinishingSide3', str(edge_finishing_side3)),
                ('gCutlist.Item[0].EdgeFinishingSide4', str(edge_finishing_side4)),
                ('gCutlist.Item[0].GappingStartSide1', str(gapping_start_side1)),
                ('gCutlist.Item[0].GappingStartSide2', str(gapping_start_side2)),
                ('gCutlist.Item[0].GappingStartSide3', str(gapping_start_side3)),
                ('gCutlist.Item[0].GappingStartSide4', str(gapping_start_side4)),
                ('gCutlist.Item[0].GappingLengthSide1', str(gapping_length_side1)),
                ('gCutlist.Item[0].GappingLengthSide2', str(gapping_length_side2)),
                ('gCutlist.Item[0].GappingLengthSide3', str(gapping_length_side3)),
                ('gCutlist.Item[0].GappingLengthSide4', str(gapping_length_side4)),
                ('gCutlist.Item[0].GappingTopSide1', str(gapping_top_side1)),
                ('gCutlist.Item[0].GappingTopSide2', str(gapping_top_side2)),
                ('gCutlist.Item[0].GappingTopSide3', str(gapping_top_side3)),
                ('gCutlist.Item[0].GappingTopSide4', str(gapping_top_side4)),
                ('gCutlist.Item[0].Thickness', str(thickness)),
                ('gCutlist.Item[0].Flip', '1'),
                ('gCutlist.Item[0].Location', 'BLA'),
            ]
            
            logger.info(f'{component_id}: Cutlist - Series={series_id}, FC={fc_value}, '
                        f'Gapping=[{gapping_side1},{gapping_side2},{gapping_side3},{gapping_side4}], '
                        f'GappingTop=[{gapping_top_side1},{gapping_top_side2},{gapping_top_side3},{gapping_top_side4}], '
                        f'Thickness={thickness}')
            
            # Write to CSV (no header, just two columns A and B)
            with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                for row in cutlist_data:
                    writer.writerow(row)
            
            # Verify file was created
            if output_path.exists():
                file_size = output_path.stat().st_size
                logger.info(f'{component_id}: Cutlist CSV exported successfully ({file_size} bytes)')
                return True, f"Exported cutlist to {output_filename} ({file_size} bytes)", str(output_path)
            else:
                return False, f"Export completed but file not found: {output_filename}", ""
            
        except Exception as e:
            return False, f"Cutlist CSV export failed: {str(e)}", ""
    
    def get_output_directory(self) -> str:
        """Get the configured output directory path."""
        return str(self.output_dir)
