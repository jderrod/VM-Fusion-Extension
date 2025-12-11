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
                except:
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
                except:
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
            for param in design.allParameters:
                # Skip user parameters (already added)
                if param.name not in [p.name for p in design.userParameters]:
                    # Try to get value, fall back to expression if not numeric
                    try:
                        raw_value = param.value
                        unit = param.unit if hasattr(param, 'unit') else ''
                        # Convert from Fusion's internal units (cm) to display units
                        value = self.convert_to_display_units(raw_value, unit)
                    except:
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
                except:
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
                    except:
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
    
    def export_drilling_coordinates(self, design: adsk.fusion.Design, component_id: str, order_id: str) -> Tuple[bool, str, str]:
        """
        Export drilling coordinates for hinge holes to a separate JSON file.
        Works for both doors and stiles.
        Includes the X-axis positions of hinge holes and Y-axis distance (hinge_hole_x_dist).
        Output is always in inches.
        
        For doors: Exports all standard hinge hole parameters + door_hinge_hole_y_dist
        For stiles: Conditionally exports left/right drilling based on boolean flags + stile_hinge_hole_y_dist
        
        Args:
            design: Design object to export parameters from
            component_id: Component identifier (e.g., D1, S1)
            order_id: Order identifier (e.g., IBUS366574)
            
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
                # For stiles, check boolean flags to determine which sides to capture
                logger.info(f'{component_id}: Stile component detected - checking drilling flags')
                all_params_dict = {p.name: p for p in list(design.userParameters) + list(design.allParameters)}
                
                # Check the 4 boolean flags
                left_interior = all_params_dict.get('left_interior_drilling')
                left_exterior = all_params_dict.get('left_exterior_drilling')
                right_interior = all_params_dict.get('right_interior_drilling')
                right_exterior = all_params_dict.get('right_exterior_drilling')
                
                # Determine if left or right drilling is needed
                capture_left = False
                capture_right = False
                
                if left_interior and left_interior.value != 0:
                    capture_left = True
                    logger.info(f'{component_id}: left_interior_drilling is true')
                if left_exterior and left_exterior.value != 0:
                    capture_left = True
                    logger.info(f'{component_id}: left_exterior_drilling is true')
                if right_interior and right_interior.value != 0:
                    capture_right = True
                    logger.info(f'{component_id}: right_interior_drilling is true')
                if right_exterior and right_exterior.value != 0:
                    capture_right = True
                    logger.info(f'{component_id}: right_exterior_drilling is true')
                
                # Build parameter list based on flags
                if capture_left:
                    logger.info(f'{component_id}: Capturing LEFT side drilling parameters')
                    drilling_param_names.extend([
                        'LD_top_hinge_hole_1_y_value',
                        'LD_top_hinge_hole_2_y_value',
                        'LD_mid_top_hinge_hole_1_y_value',
                        'LD_mid_top_hinge_hole_2_y_value',
                        'LD_mid_bottom_hinge_hole_1_y_value',
                        'LD_mid_bottom_hinge_hole_2_y_value',
                        'LD_bottom_hinge_hole_1_y_value',
                        'LD_bottom_hinge_hole_2_y_value'
                    ])
                
                if capture_right:
                    logger.info(f'{component_id}: Capturing RIGHT side drilling parameters')
                    drilling_param_names.extend([
                        'RD_top_hinge_hole_1_y_value',
                        'RD_top_hinge_hole_2_y_value',
                        'RD_mid_top_hinge_hole_1_y_value',
                        'RD_mid_top_hinge_hole_2_y_value',
                        'RD_mid_bottom_hinge_hole_1_y_value',
                        'RD_mid_bottom_hinge_hole_2_y_value',
                        'RD_bottom_hinge_hole_1_y_value',
                        'RD_bottom_hinge_hole_2_y_value'
                    ])
                
                if not capture_left and not capture_right:
                    logger.info(f'{component_id}: No drilling required (all flags are 0)')
                    return False, f"No drilling required for {component_id} (all flags are 0)", ""
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
            
            # Search through all parameters (user and model)
            all_params = list(design.userParameters) + [p for p in design.allParameters if p not in design.userParameters]
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
    
    def export_drilling_coordinates_paired(self, design: adsk.fusion.Design, component_id: str, order_id: str) -> Tuple[bool, str, str]:
        """
        Export drilling coordinates in paired X/Y format.
        Each hole is represented as a coordinate pair.
        
        Args:
            design: Design object to export parameters from
            component_id: Component identifier (e.g., D1, S1)
            order_id: Order identifier (e.g., IBUS366574)
            
        Returns:
            Tuple of (success: bool, message: str, file_path: str)
        """
        try:
            from adsk.core import Application
            import json
            from pathlib import Path
            import logging
            
            logger = logging.getLogger('FusionManufacturingPipeline')
            
            # Output file path
            output_filename = f'1-{component_id}-{order_id}-drilling-paired.json'
            output_path = Path(self.output_dir) / output_filename
            
            # Create output directory if it doesn't exist
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Determine component type
            is_stile = component_id.upper().startswith('S')
            
            # Get the Y-distance value first
            y_dist = None
            all_params = list(design.userParameters) + [p for p in design.allParameters if p not in design.userParameters]
            
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
            
            # Define parameter search based on component type
            if is_stile:
                # Check boolean flags for stiles
                capture_left = False
                capture_right = False
                
                for param in all_params:
                    if param.name in ['left_interior_drilling', 'left_exterior_drilling']:
                        if hasattr(param, 'value') and param.value > 0:
                            capture_left = True
                    elif param.name in ['right_interior_drilling', 'right_exterior_drilling']:
                        if hasattr(param, 'value') and param.value > 0:
                            capture_right = True
                
                if not capture_left and not capture_right:
                    return False, f"No drilling required for {component_id} (all flags are 0)", ""
                
                # Build parameter list based on flags
                drilling_param_names = []
                if capture_left:
                    drilling_param_names.extend([
                        'LD_top_hinge_hole_1_y_value',
                        'LD_top_hinge_hole_2_y_value',
                        'LD_mid_top_hinge_hole_1_y_value',
                        'LD_mid_top_hinge_hole_2_y_value',
                        'LD_mid_bottom_hinge_hole_1_y_value',
                        'LD_mid_bottom_hinge_hole_2_y_value',
                        'LD_bottom_hinge_hole_1_y_value',
                        'LD_bottom_hinge_hole_2_y_value'
                    ])
                if capture_right:
                    drilling_param_names.extend([
                        'RD_top_hinge_hole_1_y_value',
                        'RD_top_hinge_hole_2_y_value',
                        'RD_mid_top_hinge_hole_1_y_value',
                        'RD_mid_top_hinge_hole_2_y_value',
                        'RD_mid_bottom_hinge_hole_1_y_value',
                        'RD_mid_bottom_hinge_hole_2_y_value',
                        'RD_bottom_hinge_hole_1_y_value',
                        'RD_bottom_hinge_hole_2_y_value'
                    ])
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
            
            # Extract X values for each hole
            for param in all_params:
                if param.name in drilling_param_names:
                    try:
                        raw_value = param.value
                        x_value = round(self.convert_to_display_units(raw_value, 'in'), 3)
                        
                        # Extract hole name (remove _y_value suffix)
                        hole_name = param.name.replace('_y_value', '')
                        
                        hole_pairs.append({
                            'hole': hole_name,
                            'x': x_value,
                            'y': y_dist
                        })
                    except Exception as e:
                        logger.warning(f'{component_id}: Error reading {param.name}: {str(e)}')
            
            if len(hole_pairs) == 0:
                return False, f"No drilling coordinates found for {component_id}", ""
            
            # Build output structure
            paired_data = {
                'component_id': component_id,
                'order_id': order_id,
                'unit': 'in',
                'description': 'Paired drilling coordinates (X, Y)',
                'coordinates': hole_pairs
            }
            
            # Write to JSON
            with open(output_path, 'w', encoding='utf-8') as jsonfile:
                json.dump(paired_data, jsonfile, indent=2)
            
            # Verify file was created
            if output_path.exists():
                hole_count = len(hole_pairs)
                file_size = output_path.stat().st_size
                return True, f"Exported {hole_count} paired coordinates to {output_filename} ({file_size} bytes)", str(output_path)
            else:
                return False, f"Export completed but file not found: {output_filename}", ""
            
        except Exception as e:
            return False, f"Paired drilling coordinate export failed: {str(e)}", ""
    
    def get_output_directory(self) -> str:
        """Get the configured output directory path."""
        return str(self.output_dir)
