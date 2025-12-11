# This is the corrected export_drilling_coordinates method
# Copy this to replace the corrupted one in parameter_exporter.py

def export_drilling_coordinates(self, design: adsk.fusion.Design, component_id: str, order_id: str) -> Tuple[bool, str, str]:
    """
    Export drilling coordinates for hinge holes to a separate JSON file.
    Works for both doors and stiles.
    Only includes the X-axis positions of hinge holes.
    Output is always in inches.
    
    For doors: Exports all standard hinge hole parameters
    For stiles: Conditionally exports left/right drilling based on boolean flags
    
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
            'description': 'Hinge hole drilling coordinates (X-axis positions)',
            'holes': {}
        }
        
        # Search through all parameters (user and model)
        all_params = list(design.userParameters) + [p for p in design.allParameters if p not in design.userParameters]
        logger.info(f'{component_id}: Total parameters in design: {len(all_params)}')
        
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
