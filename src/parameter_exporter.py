"""
Parameter Exporter for Fusion 360 Manufacturing Pipeline
Exports all model parameters to CSV after parameter application
"""

import adsk.core
import adsk.fusion
import csv
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
                    value = param.value
                except:
                    value = param.expression
                
                param_info = {
                    'Parameter Name': param.name,
                    'Value': value,
                    'Unit': param.unit if hasattr(param, 'unit') else '',
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
    
    def export_all_parameters(self, design: adsk.fusion.Design, component_id: str) -> Tuple[bool, str, str]:
        """
        Export ALL parameters (user, model, and computed) to CSV file.
        
        Args:
            design: Design object to export parameters from
            component_id: Component identifier for filename
            
        Returns:
            Tuple of (success: bool, message: str, file_path: str)
        """
        try:
            # Build output filename: component_id_all_parameters.csv
            output_filename = f"{component_id}_all_parameters.csv"
            output_path = self.output_dir / output_filename
            
            # Collect all parameter types
            param_data = []
            
            # User parameters
            for param in design.userParameters:
                # Try to get value, fall back to expression if not numeric
                try:
                    value = param.value
                except:
                    value = param.expression
                
                param_info = {
                    'Type': 'User',
                    'Parameter Name': param.name,
                    'Value': value,
                    'Unit': param.unit if hasattr(param, 'unit') else '',
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
                        value = param.value
                    except:
                        value = param.expression
                    
                    param_info = {
                        'Type': 'Model',
                        'Parameter Name': param.name,
                        'Value': value,
                        'Unit': param.unit if hasattr(param, 'unit') else '',
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
    
    def get_output_directory(self) -> str:
        """Get the configured output directory path."""
        return str(self.output_dir)
