"""
Model Exporter for Fusion 360 Manufacturing Pipeline
Exports 3D models after parameter application
Version: 3.0 - Using document-based export
"""

import adsk.core
import adsk.fusion
import os
from typing import Tuple
from pathlib import Path


class ModelExporter:
    """Exports parametric models to various 3D formats"""
    
    def __init__(self, app: adsk.core.Application, output_dir: str):
        """
        Initialize model exporter.
        
        Args:
            app: Fusion Application object
            output_dir: Base directory for exported models
        """
        self.app = app
        self.ui = app.userInterface
        self.output_dir = Path(output_dir)
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def export_as_stl(self, design: adsk.fusion.Design, component_id: str) -> Tuple[bool, str, str]:
        """
        Export design as STL file.
        
        Args:
            design: Design object to export
            component_id: Component identifier for filename
            
        Returns:
            Tuple of (success: bool, message: str, file_path: str)
        """
        try:
            # Build output filename: component_id.stl
            output_filename = f"{component_id}.stl"
            output_path = self.output_dir / output_filename
            
            # Get the root component
            root_comp = design.rootComponent
            
            # Get export manager from data (correct location in API)
            export_mgr = self.app.data.exportManager
            
            # Create STL export options
            stl_export_options = export_mgr.createSTLExportOptions(root_comp, str(output_path))
            stl_export_options.sendToPrintUtility = False
            stl_export_options.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementMedium
            
            # Export
            export_mgr.execute(stl_export_options)
            
            # Verify file was created
            if output_path.exists():
                file_size = output_path.stat().st_size
                return True, f"Exported {output_filename} ({file_size} bytes)", str(output_path)
            else:
                return False, f"Export completed but file not found: {output_filename}", ""
            
        except Exception as e:
            return False, f"STL export failed: {str(e)}", ""
    
    def export_as_step(self, design: adsk.fusion.Design, component_id: str) -> Tuple[bool, str, str]:
        """
        Export design as STEP file.
        
        Args:
            design: Design object to export
            component_id: Component identifier for filename
            
        Returns:
            Tuple of (success: bool, message: str, file_path: str)
        """
        try:
            # Build output filename: component_id.step
            output_filename = f"{component_id}.step"
            output_path = self.output_dir / output_filename
            
            # Get the root component
            root_comp = design.rootComponent
            
            # Get export manager from data (correct location in API)
            export_mgr = self.app.data.exportManager
            
            # Create STEP export options
            step_export_options = export_mgr.createSTEPExportOptions(str(output_path), root_comp)
            
            # Export
            export_mgr.execute(step_export_options)
            
            # Verify file was created
            if output_path.exists():
                file_size = output_path.stat().st_size
                return True, f"Exported {output_filename} ({file_size} bytes)", str(output_path)
            else:
                return False, f"Export completed but file not found: {output_filename}", ""
            
        except Exception as e:
            return False, f"STEP export failed: {str(e)}", ""
    
    def export_as_iges(self, design: adsk.fusion.Design, component_id: str) -> Tuple[bool, str, str]:
        """
        Export design as IGES file.
        
        Args:
            design: Design object to export
            component_id: Component identifier for filename
            
        Returns:
            Tuple of (success: bool, message: str, file_path: str)
        """
        try:
            # Build output filename: component_id.igs
            output_filename = f"{component_id}.igs"
            output_path = self.output_dir / output_filename
            
            # Get the root component
            root_comp = design.rootComponent
            
            # Get export manager from data (correct location in API)
            export_mgr = self.app.data.exportManager
            
            # Create IGES export options
            iges_export_options = export_mgr.createIGESExportOptions(str(output_path), root_comp)
            
            # Export
            export_mgr.execute(iges_export_options)
            
            # Verify file was created
            if output_path.exists():
                file_size = output_path.stat().st_size
                return True, f"Exported {output_filename} ({file_size} bytes)", str(output_path)
            else:
                return False, f"Export completed but file not found: {output_filename}", ""
            
        except Exception as e:
            return False, f"IGES export failed: {str(e)}", ""
    
    def export_as_sat(self, design: adsk.fusion.Design, component_id: str) -> Tuple[bool, str, str]:
        """
        Export design as SAT file (ACIS).
        
        Args:
            design: Design object to export
            component_id: Component identifier for filename
            
        Returns:
            Tuple of (success: bool, message: str, file_path: str)
        """
        try:
            # Build output filename: component_id.sat
            output_filename = f"{component_id}.sat"
            output_path = self.output_dir / output_filename
            
            # Get the root component
            root_comp = design.rootComponent
            
            # Get export manager from data (correct location in API)
            export_mgr = self.app.data.exportManager
            
            # Create SAT export options
            sat_export_options = export_mgr.createSATExportOptions(str(output_path), root_comp)
            
            # Export
            export_mgr.execute(sat_export_options)
            
            # Verify file was created
            if output_path.exists():
                file_size = output_path.stat().st_size
                return True, f"Exported {output_filename} ({file_size} bytes)", str(output_path)
            else:
                return False, f"Export completed but file not found: {output_filename}", ""
            
        except Exception as e:
            return False, f"SAT export failed: {str(e)}", ""
    
    def export_model(self, design: adsk.fusion.Design, component_id: str, format: str = "stl") -> Tuple[bool, str, str]:
        """
        Export model in specified format.
        
        Args:
            design: Design object to export
            component_id: Component identifier for filename
            format: Export format ('stl', 'step', 'iges', 'sat')
            
        Returns:
            Tuple of (success: bool, message: str, file_path: str)
        """
        format_lower = format.lower()
        
        if format_lower == "stl":
            return self.export_as_stl(design, component_id)
        elif format_lower == "step":
            return self.export_as_step(design, component_id)
        elif format_lower == "iges":
            return self.export_as_iges(design, component_id)
        elif format_lower == "sat":
            return self.export_as_sat(design, component_id)
        else:
            return False, f"Unsupported export format: {format}", ""
    
    def get_output_directory(self) -> str:
        """Get the configured output directory path."""
        return str(self.output_dir)
