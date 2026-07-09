"""
Parameter Manager for Fusion 360 Manufacturing Pipeline
Handles reading and updating user parameters in Fusion models
"""

import adsk.core
import adsk.fusion
from typing import Dict, List, Tuple, Optional


class ParameterManager:
    """Manages parameter operations for Fusion 360 designs"""
    
    def __init__(self, design: adsk.fusion.Design):
        """
        Initialize parameter manager.
        
        Args:
            design: Fusion Design object
        """
        self.design = design
        self.user_parameters = design.userParameters
    
    def get_all_parameters(self) -> Dict[str, str]:
        """
        Get all settable parameters and their current values.
        Includes user parameters and any named parameters from allParameters
        that may not appear in userParameters due to Fusion API quirks.
        
        Returns:
            Dictionary mapping parameter name to expression (value with units)
        """
        params = {}
        for param in self.user_parameters:
            params[param.name] = param.expression
        # Also include named parameters from allParameters that were missed
        for param in self.design.allParameters:
            if param.name and param.name not in params:
                params[param.name] = param.expression
        return params
    
    def get_parameter_value(self, param_name: str) -> Optional[str]:
        """
        Get a specific parameter's current value.
        
        Args:
            param_name: Name of the parameter
            
        Returns:
            Parameter expression (value with units) or None if not found
        """
        param = self.user_parameters.itemByName(param_name)
        if param:
            return param.expression
        # Fall back to allParameters
        for p in self.design.allParameters:
            if p.name == param_name:
                return p.expression
        return None
    
    def update_parameter(self, param_name: str, new_value: str) -> Tuple[bool, str]:
        """
        Update a parameter's value.
        
        Args:
            param_name: Name of the parameter to update
            new_value: New value as string (can include units, e.g., "100 mm", "2.5", "45 deg")
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Get the parameter (try userParameters first, fall back to allParameters)
            param = self.user_parameters.itemByName(param_name)
            
            if not param:
                # Fall back: search allParameters for params not in userParameters
                for p in self.design.allParameters:
                    if p.name == param_name:
                        param = p
                        break
            
            if not param:
                return False, f"Parameter '{param_name}' not found in model"
            
            # Store old value for logging
            old_value = param.expression
            
            # Fusion Text parameters require expressions wrapped in single quotes.
            # Pre-wrap if the existing expression is already quoted (known Text param).
            if param.unit == '' and old_value.startswith("'") and old_value.endswith("'"):
                if not (new_value.startswith("'") and new_value.endswith("'")):
                    new_value = f"'{new_value}'"
            
            # If parameter has a unit and new_value is a bare number, append the unit
            # to ensure Fusion interprets it in the correct unit system.
            # Without this, Fusion may silently ignore the assignment.
            param_unit = param.unit
            if param_unit and param_unit != '':
                # Check if new_value is a bare number (no unit suffix)
                stripped = new_value.strip()
                try:
                    float(stripped)
                    # It's a bare number — append the unit
                    new_value = f"{stripped} {param_unit}"
                except ValueError:
                    pass  # Already has units or is an expression, leave as-is
            
            # Try setting the expression
            try:
                param.expression = new_value
                # Verify the value actually changed (Fusion can silently no-op)
                actual_expr = param.expression
                if actual_expr != new_value and actual_expr == old_value:
                    return False, f"Parameter '{param_name}' assignment silently failed: tried '{new_value}', still '{actual_expr}'"
                return True, f"Updated '{param_name}' from '{old_value}' to '{new_value}' (actual: '{actual_expr}')"
            except Exception:
                # If it failed and value isn't already quoted, try as a Text parameter
                if not (new_value.startswith("'") and new_value.endswith("'")):
                    quoted_value = f"'{new_value}'"
                    param.expression = quoted_value
                    return True, f"Updated '{param_name}' from '{old_value}' to '{quoted_value}' (auto-quoted)"
                raise
            
        except Exception as e:
            return False, f"Failed to update '{param_name}': {str(e)}"
    
    def update_parameters_batch(self, parameters: Dict[str, str]) -> List[Tuple[str, bool, str]]:
        """
        Update multiple parameters at once.
        
        Args:
            parameters: Dictionary mapping parameter name to new value
            
        Returns:
            List of tuples (param_name, success, message) for each parameter
        """
        results = []
        
        for param_name, new_value in parameters.items():
            success, message = self.update_parameter(param_name, new_value)
            results.append((param_name, success, message))
        
        return results
    
    def validate_parameters_exist(self, param_names: List[str]) -> Tuple[bool, List[str]]:
        """
        Check if all specified parameters exist in the model.
        
        Args:
            param_names: List of parameter names to check
            
        Returns:
            Tuple of (all_exist: bool, missing_params: List[str])
        """
        # Build a set of all known parameter names for O(1) lookup
        all_known = {p.name for p in self.design.allParameters}
        missing = [name for name in param_names if name not in all_known]
        
        return len(missing) == 0, missing
    
    def get_parameter_info(self, param_name: str) -> Optional[Dict[str, any]]:
        """
        Get detailed information about a parameter.
        
        Args:
            param_name: Name of the parameter
            
        Returns:
            Dictionary with parameter details or None if not found
        """
        param = self.user_parameters.itemByName(param_name)
        
        if not param:
            # Fall back to allParameters
            for p in self.design.allParameters:
                if p.name == param_name:
                    param = p
                    break
        
        if not param:
            return None
        
        return {
            'name': param.name,
            'expression': param.expression,
            'value': param.value,
            'unit': param.unit,
            'comment': param.comment if hasattr(param, 'comment') else '',
            'is_favorite': param.isFavorite if hasattr(param, 'isFavorite') else False
        }
    
    def list_all_parameters(self) -> List[Dict[str, any]]:
        """
        Get detailed information about all parameters (user + model).
        
        Returns:
            List of parameter info dictionaries
        """
        params = []
        seen_names = set()
        for param in self.user_parameters:
            params.append({
                'name': param.name,
                'expression': param.expression,
                'value': param.value,
                'unit': param.unit
            })
            seen_names.add(param.name)
        for param in self.design.allParameters:
            if param.name not in seen_names:
                params.append({
                    'name': param.name,
                    'expression': param.expression,
                    'value': param.value,
                    'unit': param.unit
                })
                seen_names.add(param.name)
        return params


    def parse_parameter_value(self, param_data: any) -> Tuple[any, str, str]:
        """
        Parse parameter value from new JSON format [value, datatype, description].
        
        Args:
            param_data: Either a list [value, datatype, description] or a direct value
            
        Returns:
            Tuple of (value, datatype, description)
        """
        if isinstance(param_data, list) and len(param_data) >= 2:
            # New format: [value, datatype, description]
            value = param_data[0]
            datatype = param_data[1] if len(param_data) > 1 else "string"
            description = param_data[2] if len(param_data) > 2 else ""
            return value, datatype, description
        else:
            # Old format: direct value
            return param_data, "string", ""
    
    def format_value_by_type(self, value: any, datatype: str) -> str:
        """
        Format a value based on its datatype for Fusion 360 parameter expression.
        
        Args:
            value: Raw value (could be string, number, bool, etc.)
            datatype: Data type ("string", "float", "int", "bool")
            
        Returns:
            Formatted expression string suitable for Fusion 360
        """
        # Handle null values
        if value is None:
            return "0"
        
        datatype = datatype.lower()
        
        if datatype == "bool" or datatype == "boolean":
            # Boolean: convert to 0 or 1
            if isinstance(value, bool):
                return "1" if value else "0"
            elif isinstance(value, str):
                return "1" if value.lower() in ['true', '1', 'yes'] else "0"
            else:
                return "1" if value else "0"
        
        elif datatype == "float" or datatype == "number":
            # Float: convert to string number
            return str(float(value))
        
        elif datatype == "int" or datatype == "integer":
            # Integer: convert to string integer
            return str(int(value))
        
        elif datatype == "string":
            # String: could have units like "100 mm" or be plain value
            value_str = str(value)
            
            # If it's a number without units, just return it
            # If it has units, return as-is
            return value_str
        
        else:
            # Default: return as string
            return str(value)
    
    def update_parameters_from_json(self, parameters: Dict[str, any], auto_match: bool = True, param_mapping: Dict[str, str] = None) -> List[Tuple[str, bool, str]]:
        """
        Update multiple parameters from JSON format with [value, datatype, description] lists.
        
        Args:
            parameters: Dictionary mapping parameter name to value (can be [value, datatype, description] or direct value)
            auto_match: If True, only update parameters that exist in the model (default: True)
            param_mapping: Optional dictionary mapping JSON param names to model param names (e.g., {"stile_left_side_door": "left_side_door"})
            
        Returns:
            List of tuples (param_name, success, message) for each parameter
        """
        results = []
        
        # Get all existing model parameters if auto-matching
        model_params = set()
        if auto_match:
            model_params = set(self.get_all_parameters().keys())
        
        for json_param_name, param_data in parameters.items():
            # Apply parameter name mapping if provided
            model_param_name = json_param_name
            if param_mapping and json_param_name in param_mapping:
                model_param_name = param_mapping[json_param_name]
            
            # If auto-matching, skip parameters not in model
            if auto_match and model_param_name not in model_params:
                # Silently skip - this allows JSON to have extra parameters
                continue
            
            # Parse the parameter data
            value, datatype, description = self.parse_parameter_value(param_data)
            
            # Format the value based on datatype
            formatted_value = self.format_value_by_type(value, datatype)
            
            # Update the parameter
            success, message = self.update_parameter(model_param_name, formatted_value)
            
            # Add description info to message if available
            if success and description:
                message += f" ({description})"
            
            results.append((model_param_name, success, message))
        
        return results


