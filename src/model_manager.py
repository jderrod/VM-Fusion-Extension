"""
Model Manager for Fusion 360 Manufacturing Pipeline
Handles persistent model storage and retrieval for Door, Panel, and Stile components
"""

import adsk.core
import adsk.fusion
import os
from pathlib import Path
from typing import Dict, Optional, Tuple
from logger import get_logger


class ModelManager:
    """Manages persistent storage and retrieval of Fusion 360 models"""
    
    # Component types
    DOOR = "door"
    PANEL = "panel"
    STILE = "stile"
    
    def __init__(self, app: adsk.core.Application, inputs_folder: str = None):
        """
        Initialize model manager.
        
        Args:
            app: Fusion Application object
            inputs_folder: Path to inputs folder (defaults to network INPUT_BASE from config)
        """
        self.app = app
        self.ui = app.userInterface
        self.logger = get_logger()
        
        # Set up inputs folder
        if inputs_folder is None:
            # Default to network INPUT_BASE from config
            from config import INPUT_BASE
            inputs_folder = str(INPUT_BASE)
        
        self.inputs_folder = Path(inputs_folder)
        self._ensure_folder_structure()
        
        # Cache for model paths
        self._model_paths = {
            self.DOOR: None,
            self.PANEL: None,
            self.STILE: None
        }
        
        # Cache for opened documents
        self._cached_documents = {}
        
        # Discover existing models
        self._discover_models()
    
    def _ensure_folder_structure(self):
        """Create inputs folder structure if it doesn't exist"""
        try:
            self.inputs_folder.mkdir(exist_ok=True)
            
            # Create subfolders for each component type
            for component_type in [self.DOOR, self.PANEL, self.STILE]:
                subfolder = self.inputs_folder / component_type
                subfolder.mkdir(exist_ok=True)
                
            self.logger.info(f'Inputs folder structure ready: {self.inputs_folder}')
        except Exception as e:
            self.logger.error(f'Failed to create inputs folder structure: {str(e)}')
    
    def _discover_models(self):
        """Discover .f3d files in the inputs folder"""
        try:
            for component_type in [self.DOOR, self.PANEL, self.STILE]:
                subfolder = self.inputs_folder / component_type
                
                # Find .f3d files in this subfolder
                f3d_files = list(subfolder.glob('*.f3d'))
                
                if f3d_files:
                    # Use the first .f3d file found
                    self._model_paths[component_type] = str(f3d_files[0])
                    self.logger.info(f'Found {component_type} model: {f3d_files[0].name}')
                else:
                    self.logger.warning(f'No .f3d file found for {component_type} in {subfolder}')
        except Exception as e:
            self.logger.error(f'Failed to discover models: {str(e)}')
    
    def get_model_path(self, component_type: str) -> Optional[str]:
        """
        Get the path to the model file for a specific component type.
        
        Args:
            component_type: Type of component (door, panel, stile)
            
        Returns:
            Path to .f3d file or None if not found
        """
        component_type = component_type.lower()
        
        if component_type not in self._model_paths:
            self.logger.error(f'Invalid component type: {component_type}')
            return None
        
        path = self._model_paths[component_type]
        
        if path is None:
            self.logger.warning(f'No model file registered for {component_type}')
        
        return path
    
    def set_model_path(self, component_type: str, file_path: str) -> bool:
        """
        Manually set the model path for a component type.
        
        Args:
            component_type: Type of component (door, panel, stile)
            file_path: Path to .f3d file
            
        Returns:
            True if successful
        """
        component_type = component_type.lower()
        
        if component_type not in self._model_paths:
            self.logger.error(f'Invalid component type: {component_type}')
            return False
        
        if not os.path.exists(file_path):
            self.logger.error(f'Model file does not exist: {file_path}')
            return False
        
        self._model_paths[component_type] = file_path
        self.logger.info(f'Set {component_type} model to: {file_path}')
        return True
    
    def is_model_available(self, component_type: str) -> bool:
        """
        Check if a model is available for a component type.
        
        Args:
            component_type: Type of component (door, panel, stile)
            
        Returns:
            True if model is available
        """
        path = self.get_model_path(component_type)
        return path is not None and os.path.exists(path)
    
    def get_available_models(self) -> Dict[str, Optional[str]]:
        """
        Get all available models and their paths.
        
        Returns:
            Dictionary mapping component type to path (or None)
        """
        return {
            self.DOOR: self._model_paths[self.DOOR],
            self.PANEL: self._model_paths[self.PANEL],
            self.STILE: self._model_paths[self.STILE]
        }
    
    def open_all_models(self) -> Tuple[bool, str]:
        """
        Open all configured models (door, panel, stile) at startup.
        This avoids reopening models for each component.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            opened_models = []
            skipped_models = []
            
            for comp_type in [self.DOOR, self.PANEL, self.STILE]:
                model_path = self.get_model_path(comp_type)
                
                if not model_path:
                    skipped_models.append(f"{comp_type} (no model configured)")
                    continue
                
                if not os.path.exists(model_path):
                    skipped_models.append(f"{comp_type} (file not found)")
                    continue
                
                # Open the model
                self.logger.info(f'Opening {comp_type} model: {model_path}')
                import_manager = self.app.importManager
                import_options = import_manager.createFusionArchiveImportOptions(model_path)
                doc = import_manager.importToNewDocument(import_options)
                
                if doc:
                    self._cached_documents[comp_type] = doc
                    opened_models.append(comp_type)
                    self.logger.info(f'Successfully opened {comp_type} model: {doc.name}')
                else:
                    skipped_models.append(f"{comp_type} (failed to open)")
            
            # Build message
            msg_parts = []
            if opened_models:
                msg_parts.append(f"Opened models: {', '.join(opened_models)}")
            if skipped_models:
                msg_parts.append(f"Skipped: {', '.join(skipped_models)}")
            
            message = '\n'.join(msg_parts) if msg_parts else "No models opened"
            success = len(opened_models) > 0
            
            return success, message
            
        except Exception as e:
            msg = f'Exception opening models: {str(e)}'
            self.logger.exception(msg)
            return False, msg
    
    def open_model(self, component_type: str) -> Tuple[bool, Optional[adsk.core.Document], str]:
        """
        Switch to the model for a specific component type.
        Uses cached document if available from open_all_models().
        
        Args:
            component_type: Type of component (door, panel, stile)
            
        Returns:
            Tuple of (success, document, message)
        """
        try:
            # Check if we have a cached document
            if component_type in self._cached_documents:
                doc = self._cached_documents[component_type]
                
                # Verify document is still valid
                if doc.isValid:
                    # Activate it
                    self.logger.info(f'Activating cached {component_type} model: {doc.name}')
                    doc.activate()
                    
                    # Verify activation
                    if self.app.activeDocument == doc:
                        return True, doc, f'Switched to {component_type} model'
                    else:
                        self.logger.warning(f'Document activation may have failed for {doc.name}')
                        return True, doc, f'Switched to {component_type} model'
                else:
                    # Document no longer valid, remove from cache
                    self.logger.warning(f'Cached {component_type} document no longer valid')
                    del self._cached_documents[component_type]
            
            # No cached document or invalid - need to open it
            model_path = self.get_model_path(component_type)
            
            if not model_path:
                msg = f'No {component_type} model configured in inputs folder'
                self.logger.error(msg)
                return False, None, msg
            
            if not os.path.exists(model_path):
                msg = f'{component_type} model file not found: {model_path}'
                self.logger.error(msg)
                return False, None, msg
            
            # Open the model
            self.logger.info(f'Opening {component_type} model from: {model_path}')
            import_manager = self.app.importManager
            import_options = import_manager.createFusionArchiveImportOptions(model_path)
            doc = import_manager.importToNewDocument(import_options)
            
            if not doc:
                msg = f'Failed to open {component_type} model (returned None)'
                self.logger.error(msg)
                return False, None, msg
            
            # Cache the document
            self._cached_documents[component_type] = doc
            
            # Verify document is active
            if self.app.activeDocument == doc:
                self.logger.info(f'Successfully opened and activated {component_type} model: {doc.name}')
            else:
                self.logger.warning(f'Document opened but not active, attempting activation: {doc.name}')
                doc.activate()
            
            return True, doc, f'Opened {component_type} model: {doc.name}'
            
        except Exception as e:
            msg = f'Exception opening {component_type} model: {str(e)}'
            self.logger.exception(msg)
            return False, None, msg
    
    def get_inputs_folder_info(self) -> str:
        """
        Get information about the inputs folder structure.
        
        Returns:
            Formatted string with folder information
        """
        info = f'Inputs Folder: {self.inputs_folder}\n\n'
        
        for component_type in [self.DOOR, self.PANEL, self.STILE]:
            subfolder = self.inputs_folder / component_type
            model_path = self._model_paths[component_type]
            
            info += f'{component_type.upper()}:\n'
            info += f'  Folder: {subfolder}\n'
            
            if model_path:
                info += f'  Model: {os.path.basename(model_path)}\n'
            else:
                info += f'  Model: NOT FOUND (place .f3d file in folder)\n'
            
            info += '\n'
        
        return info
