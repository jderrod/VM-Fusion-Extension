"""
JSON Schema Validator for Fusion 360 Manufacturing Orders

This module provides schema validation independent of Fusion API,
allowing for pure Python unit testing.
"""

import json
from typing import Dict, List, Tuple, Any
from pathlib import Path


class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass


class OrderValidator:
    """Validates manufacturing order JSON against schema"""
    
    def __init__(self, schema_path: str = None):
        """
        Initialize validator with schema
        
        Args:
            schema_path: Path to schema.json (optional, defaults to repo root)
        """
        if schema_path is None:
            # Default to schema.json in repo root
            repo_root = Path(__file__).parent.parent
            schema_path = repo_root / "schema.json"
        
        self.schema_path = Path(schema_path)
        self.schema = self._load_schema()
    
    def _load_schema(self) -> Dict:
        """Load JSON schema from file"""
        try:
            with open(self.schema_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            raise ValidationError(f"Schema file not found: {self.schema_path}")
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON in schema file: {e}")
    
    def validate_json_file(self, order_path: str) -> Tuple[bool, List[str]]:
        """
        Validate an order JSON file
        
        Args:
            order_path: Path to order JSON file
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        try:
            with open(order_path, 'r') as f:
                order_data = json.load(f)
            return self.validate_order(order_data)
        except FileNotFoundError:
            return False, [f"Order file not found: {order_path}"]
        except json.JSONDecodeError as e:
            return False, [f"Invalid JSON syntax: {e}"]
    
    def is_v2_format(self, order_data: Dict) -> bool:
        """
        Detect if this is the new v2 JSON format.
        v2 format has: order_id (not orderId), panels/doors/stiles arrays
        
        Args:
            order_data: Parsed JSON order data
            
        Returns:
            True if v2 format detected
        """
        if not isinstance(order_data, dict):
            return False
        
        # v2 format indicators
        has_order_id = 'order_id' in order_data
        has_panels = 'panels' in order_data
        has_doors = 'doors' in order_data
        has_stiles = 'stiles' in order_data
        
        # If it has order_id or any of the component type arrays, it's v2
        return has_order_id or has_panels or has_doors or has_stiles
    
    def validate_order(self, order_data: Dict) -> Tuple[bool, List[str]]:
        """
        Validate order data against schema
        
        Args:
            order_data: Parsed JSON order data
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        # Basic structure validation
        if not isinstance(order_data, dict):
            return False, ["Order must be a JSON object"]
        
        # Check if this is v2 format
        if self.is_v2_format(order_data):
            # Skip old validation for v2 format
            # v2 format validation is minimal - just check basic structure
            return self.validate_order_v2(order_data)
        
        # Required fields for v1 format
        required_fields = ['version', 'orderId', 'components']
        for field in required_fields:
            if field not in order_data:
                errors.append(f"Missing required field: '{field}'")
        
        if errors:
            return False, errors
        
        # Validate version format
        version = order_data.get('version', '')
        if not self._validate_version(version):
            errors.append(f"Invalid version format: '{version}' (expected X.Y.Z)")
        
        # Validate orderId
        if not order_data.get('orderId'):
            errors.append("orderId cannot be empty")
        
        # Validate components array
        components = order_data.get('components', [])
        if not isinstance(components, list):
            errors.append("components must be an array")
        elif len(components) == 0:
            errors.append("components array must contain at least 1 item")
        else:
            # Validate each component
            component_ids = set()
            for idx, component in enumerate(components):
                comp_errors = self._validate_component(component, idx)
                errors.extend(comp_errors)
                
                # Check for duplicate componentIds
                comp_id = component.get('componentId')
                if comp_id:
                    if comp_id in component_ids:
                        errors.append(f"Duplicate componentId: '{comp_id}'")
                    component_ids.add(comp_id)
        
        # Validate outputConfig if present
        if 'outputConfig' in order_data:
            config_errors = self._validate_output_config(order_data['outputConfig'])
            errors.extend(config_errors)
        
        return len(errors) == 0, errors
    
    def _validate_version(self, version: str) -> bool:
        """Validate version string format (X.Y.Z)"""
        if not isinstance(version, str):
            return False
        parts = version.split('.')
        if len(parts) != 3:
            return False
        return all(part.isdigit() for part in parts)
    
    def _validate_component(self, component: Dict, index: int) -> List[str]:
        """Validate a single component object"""
        errors = []
        prefix = f"Component[{index}]"
        
        if not isinstance(component, dict):
            return [f"{prefix}: Must be an object"]
        
        # Required fields
        required_fields = ['componentId', 'fusionModelPath', 'parameters']
        for field in required_fields:
            if field not in component:
                errors.append(f"{prefix}: Missing required field '{field}'")
        
        # Validate componentId
        comp_id = component.get('componentId', '')
        if not comp_id or not isinstance(comp_id, str):
            errors.append(f"{prefix}: componentId must be a non-empty string")
        
        # Validate fusionModelPath
        model_path = component.get('fusionModelPath', '')
        if not model_path or not isinstance(model_path, str):
            errors.append(f"{prefix}: fusionModelPath must be a non-empty string")
        
        # Validate parameters object
        parameters = component.get('parameters')
        if parameters is not None:
            if not isinstance(parameters, dict):
                errors.append(f"{prefix}: parameters must be an object")
            else:
                param_errors = self._validate_parameters(parameters, prefix)
                errors.extend(param_errors)
        
        # Validate setupNames if present
        if 'setupNames' in component:
            setup_names = component['setupNames']
            if not isinstance(setup_names, list):
                errors.append(f"{prefix}: setupNames must be an array")
            elif not all(isinstance(name, str) for name in setup_names):
                errors.append(f"{prefix}: All setupNames must be strings")
        
        # Validate postProcessorConfig if present
        if 'postProcessorConfig' in component:
            config = component['postProcessorConfig']
            if not isinstance(config, dict):
                errors.append(f"{prefix}: postProcessorConfig must be an object")
        
        return errors
    
    def _validate_parameters(self, parameters: Dict, prefix: str) -> List[str]:
        """Validate parameter values"""
        errors = []
        
        for param_name, param_value in parameters.items():
            # Parameter name must be a string
            if not isinstance(param_name, str) or not param_name:
                errors.append(f"{prefix}.parameters: Invalid parameter name")
                continue
            
            # Parameter value must be number, string, or integer
            valid_types = (int, float, str)
            if not isinstance(param_value, valid_types):
                errors.append(
                    f"{prefix}.parameters.{param_name}: "
                    f"Invalid value type (must be number, string, or integer)"
                )
        
        return errors
    
    def _validate_output_config(self, config: Dict) -> List[str]:
        """Validate output configuration"""
        errors = []
        
        if not isinstance(config, dict):
            return ["outputConfig must be an object"]
        
        # Validate baseDirectory if present
        if 'baseDirectory' in config:
            base_dir = config['baseDirectory']
            if not isinstance(base_dir, str):
                errors.append("outputConfig.baseDirectory must be a string")
        
        # Validate includeTimestamp if present
        if 'includeTimestamp' in config:
            include_ts = config['includeTimestamp']
            if not isinstance(include_ts, bool):
                errors.append("outputConfig.includeTimestamp must be a boolean")
        
        return errors
    
    def validate_order_v2(self, order_data: Dict) -> Tuple[bool, List[str]]:
        """
        Validate v2 format order data.
        v2 format is more flexible - just check basic structure.
        
        Args:
            order_data: Parsed JSON order data
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        # Check for at least one component type array
        has_components = (
            ('panels' in order_data and isinstance(order_data['panels'], list)) or
            ('doors' in order_data and isinstance(order_data['doors'], list)) or
            ('stiles' in order_data and isinstance(order_data['stiles'], list))
        )
        
        if not has_components:
            errors.append("v2 format requires at least one of: panels, doors, or stiles arrays")
        
        # Check each component type if present
        for comp_type in ['panels', 'doors', 'stiles']:
            if comp_type in order_data:
                components = order_data[comp_type]
                if not isinstance(components, list):
                    errors.append(f"{comp_type} must be an array")
                else:
                    # Basic validation of each component
                    for idx, comp in enumerate(components):
                        if not isinstance(comp, dict):
                            errors.append(f"{comp_type}[{idx}] must be an object")
                        elif 'parameters' not in comp:
                            errors.append(f"{comp_type}[{idx}] missing 'parameters' field")
        
        return len(errors) == 0, errors
    
    def get_schema_version(self) -> str:
        """Get the schema version"""
        return self.schema.get('version', 'unknown')


def validate_order_file(order_path: str, schema_path: str = None) -> Tuple[bool, List[str]]:
    """
    Convenience function to validate an order file
    
    Args:
        order_path: Path to order JSON file
        schema_path: Optional path to schema.json
        
    Returns:
        Tuple of (is_valid, error_messages)
    """
    validator = OrderValidator(schema_path)
    return validator.validate_json_file(order_path)


if __name__ == "__main__":
    # Simple CLI for testing
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python validator.py <order_file.json>")
        sys.exit(1)
    
    order_file = sys.argv[1]
    is_valid, errors = validate_order_file(order_file)
    
    if is_valid:
        print(f"✓ Valid: {order_file}")
    else:
        print(f"✗ Invalid: {order_file}")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)
