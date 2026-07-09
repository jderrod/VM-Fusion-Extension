"""
Model Manager for Fusion 360 Manufacturing Pipeline
Handles persistent model storage and retrieval for Door, Panel, and Stile components
Supports dynamic model selection based on series ID for doors.
"""

import adsk.core
import adsk.fusion
import os
import re
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple
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
        
        # Cache for model paths (default/fallback for panel and stile)
        self._model_paths = {
            self.DOOR: None,
            self.PANEL: None,
            self.STILE: None
        }
        
        # Dictionary of all discovered stile models by series code (e.g., '3081' -> path)
        self._stile_models = {}
        
        # Cache for opened documents - keyed by full path for doors, component_type for others
        self._cached_documents = {}
        
        # Cloud document support - DataFiles for cloud-based models
        self._cloud_data_files = {
            self.DOOR: None,
            self.PANEL: None,
            self.STILE: {}  # Dictionary mapping series code -> DataFile (e.g., '3081' -> DataFile)
        }
        self._door_drawing_data_file = None  # DataFile for cloud-based door drawing
        self._panel_drawing_data_file = None  # DataFile for cloud-based panel drawing
        self._stile_drawing_data_files = {}  # series_code -> DataFile for stile drawings
        self._cached_drawing_docs = {}  # Cache for opened drawing documents (key -> Document)
        self._use_cloud_models = False  # Flag to use cloud models instead of local
        
        # Cloud project configuration
        self._cloud_project_name = None
        self._cloud_folder_name = None
        
        # Discover existing local models (fallback)
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
    
    def _extract_series_code(self, series_id: str) -> Optional[str]:
        """
        Extract the 4-digit series code (e.g., '3081', '3082', '3086') from a series_id.
        
        The second digit is a generation indicator and is irrelevant to model selection.
        It is normalized to '0' so that e.g. '3186' maps to the same model as '3086'.
        
        Examples:
            '3082G.67P' -> '3082'
            '3081G' -> '3081'
            '3086' -> '3086'
            '3082.67P' -> '3082'
            'S3082G.67P' -> '3082'
            '3186G.67P' -> '3086'
            '3182G.67P' -> '3082'
        
        Args:
            series_id: Full series identifier from JSON
            
        Returns:
            4-digit series code or None if not found
        """
        if not series_id:
            return None
        
        # Search for 4-digit code starting with 3 anywhere in the string
        # (handles prefixes like 'S' in 'S3082G.67P' from upstream systems)
        match = re.search(r'(3\d{3})', series_id)
        if match:
            code = match.group(1)
            # Normalize: the 2nd digit is a generation indicator irrelevant to model
            # selection. Replace it with '0' so e.g. '3186' -> '3086', '3182' -> '3082'.
            return code[0] + '0' + code[2:]
        return None
    
    def _discover_models(self):
        """Discover .f3d files in the inputs folder"""
        try:
            for component_type in [self.DOOR, self.PANEL, self.STILE]:
                subfolder = self.inputs_folder / component_type
                
                # Find .f3d files in this subfolder
                f3d_files = list(subfolder.glob('*.f3d'))
                
                if component_type == self.STILE:
                    # For stiles, index all models by their series code
                    for f3d_file in f3d_files:
                        # Extract series code from filename (e.g., stile_3X81.f3d -> 3081)
                        # Pattern: look for 3X8X pattern where X is a digit
                        filename = f3d_file.stem.lower()  # e.g., 'stile_3x81'
                        
                        # Match patterns like 3x81, 3x82, 3x86 (case insensitive)
                        match = re.search(r'3[xX]?(\d)(\d)', filename)
                        if match:
                            # Reconstruct as 30XX (e.g., 3x81 -> 3081)
                            series_code = f'30{match.group(1)}{match.group(2)}'
                            self._stile_models[series_code] = str(f3d_file)
                            self.logger.info(f'Found stile model for series {series_code}: {f3d_file.name}')
                        else:
                            # Fallback: try direct 4-digit match
                            match = re.search(r'(3\d{3})', filename)
                            if match:
                                series_code = match.group(1)
                                self._stile_models[series_code] = str(f3d_file)
                                self.logger.info(f'Found stile model for series {series_code}: {f3d_file.name}')
                    
                    # Set default stile model (first one found, if any)
                    if f3d_files:
                        self._model_paths[self.STILE] = str(f3d_files[0])
                        self.logger.info(f'Default stile model: {f3d_files[0].name}')
                    
                    if self._stile_models:
                        self.logger.info(f'Discovered {len(self._stile_models)} stile model(s): {list(self._stile_models.keys())}')
                    else:
                        self.logger.warning(f'No stile models found in {subfolder}')
                else:
                    # For panel and door, use single model (first found)
                    if f3d_files:
                        self._model_paths[component_type] = str(f3d_files[0])
                        self.logger.info(f'Found {component_type} model: {f3d_files[0].name}')
                    else:
                        self.logger.warning(f'No .f3d file found for {component_type} in {subfolder}')
        except Exception as e:
            self.logger.error(f'Failed to discover models: {str(e)}')
    
    def _get_fusion_cache_dir(self) -> Optional[str]:
        """
        Locate Fusion 360's local cloud document cache directory.
        Pattern: {LOCALAPPDATA}/Autodesk/Autodesk Fusion 360/{userId}/W.login/F/
        
        Returns:
            Absolute path to cache dir, or None if not found.
        """
        try:
            user_local = os.path.join(os.environ.get('LOCALAPPDATA', ''),
                                      'Autodesk', 'Autodesk Fusion 360')
            if not os.path.isdir(user_local):
                return None
            for entry in os.listdir(user_local):
                candidate = os.path.join(user_local, entry, 'W.login', 'F')
                if os.path.isdir(candidate):
                    return candidate
        except Exception:
            pass
        return None

    def _resolve_local_cache_path(self, model_name: str) -> Optional[str]:
        """
        Find the most recent local .f3d cache file for a cloud model.
        
        Fusion stores cloud documents locally as:
            _{ModelName}.{version-guid}.f3d
        
        Args:
            model_name: Cloud model name (e.g., '3X86_Stile', '3X8X_Panel')
            
        Returns:
            Absolute path to the most recent .f3d file, or None if not found.
        """
        try:
            import glob
            cache_dir = self._get_fusion_cache_dir()
            if not cache_dir:
                self.logger.warning('Cannot resolve local cache path: cache dir not found')
                return None
            
            pattern = os.path.join(cache_dir, f'_{model_name}.*.f3d')
            matches = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
            
            if matches:
                self.logger.info(f'Resolved local cache for {model_name}: {os.path.basename(matches[0])}')
                return matches[0]
            
            self.logger.warning(f'No local cache file found for {model_name} in {cache_dir}')
            return None
        except Exception as e:
            self.logger.warning(f'Error resolving local cache path for {model_name}: {e}')
            return None

    def _open_local_import(self, component_type: str, model_name: str,
                            cache_key: str) -> Tuple[bool, Optional[adsk.core.Document], str]:
        """
        Open a cloud model by importing its local .f3d cache file directly.
        
        This completely bypasses documents.open(dataFile) and Fusion's internal
        PLM360OpenAttachmentCommand, which triggers a version reconciliation loop
        on cloud lineages and causes STACK_OVERFLOW crashes.
        
        Use this for models that are READ-ONLY (stile, panel) — they don't need
        cloud linkage since they are never saved back.
        
        Args:
            component_type: Type label for logging (e.g., 'stile (3086)')
            model_name: Cloud model name to find in local cache
            cache_key: Key for document caching
            
        Returns:
            Tuple of (success, document, message)
        """
        try:
            # Step 1: Check Python cache first
            if cache_key in self._cached_documents:
                doc = self._cached_documents[cache_key]
                if doc.isValid:
                    self.logger.info(f'Activating cached {component_type} model: {doc.name}')
                    doc.activate()
                    return True, doc, f'Switched to {component_type} model: {doc.name}'
                else:
                    del self._cached_documents[cache_key]
            
            # Step 2: Resolve local .f3d cache path
            local_path = self._resolve_local_cache_path(model_name)
            if not local_path:
                return False, None, (
                    f'No local cache file for {component_type} model "{model_name}". '
                    f'Open the model manually in Fusion once to create the local cache.'
                )
            
            # Step 3: Import the local .f3d file (no cloud connection = no crash)
            self.logger.info(f'Importing {component_type} model from local cache: {os.path.basename(local_path)}')
            import_manager = self.app.importManager
            import_options = import_manager.createFusionArchiveImportOptions(local_path)
            doc = import_manager.importToNewDocument(import_options)
            
            if not doc:
                return False, None, f'Failed to import {component_type} model from local cache'
            
            # Activate and cache
            doc.activate()
            adsk.doEvents()
            self._cached_documents[cache_key] = doc
            
            self.logger.info(f'Imported {component_type} model from local cache: {doc.name}')
            return True, doc, f'Opened {component_type} model (local import): {doc.name}'
            
        except Exception as e:
            return False, None, f'Error importing {component_type} model from local cache: {str(e)}'

    def _clear_stale_cloud_cache(self, model_names: List[str] = None):
        """
        Clear stale versions from Fusion's local cloud document cache.
        
        Fusion caches cloud documents locally as .f3d files with version GUIDs.
        Over time, accumulated old versions cause Fusion's internal
        CloseDocumentCommand version reconciliation loop, which leads to
        STACK_OVERFLOW crashes when opening cloud documents.
        
        This method keeps only the most recent version of each model and
        deletes all older versions along with their sidecar files (._xx, .png).
        
        MUST be called BEFORE any documents.open(dataFile) calls.
        
        Args:
            model_names: List of model name prefixes to clean (e.g., ['3X86_Stile']).
                         If None, cleans all known 3X8X model caches.
        """
        try:
            import glob
            
            cache_dir = self._get_fusion_cache_dir()
            if not cache_dir:
                self.logger.warning('Fusion cloud cache directory not found')
                return
            
            self.logger.info(f'Clearing stale cloud cache in: {cache_dir}')
            
            # Default model prefixes to clean
            if model_names is None:
                model_names = [
                    '3X81_Stile', '3X82_Stile', '3X86_Stile',
                    '3X8X_Panel', '3X8X_Door', '3X8X-Door',
                    '3X8X_Door Drawing', '3X8X_Panel Drawing',
                    '3X8X_Door_branch_B', '3X8X_Door_branch_B Drawing',
                    '3X8X_Panel_branch_B', '3X8X_Panel_branch_B Drawing',
                    '3X82_Stile Drawing', '3X86_Stile Drawing'
                ]
            
            total_deleted = 0
            total_freed = 0
            
            for model_name in model_names:
                prefix = f'_{model_name}'
                
                # Find all .f3d and .f2d files for this model
                f3d_files = sorted(
                    glob.glob(os.path.join(cache_dir, f'{prefix}.*.f3d')),
                    key=os.path.getmtime, reverse=True
                )
                f2d_files = sorted(
                    glob.glob(os.path.join(cache_dir, f'{prefix}.*.f2d')),
                    key=os.path.getmtime, reverse=True
                )
                
                all_files = f3d_files + f2d_files
                
                if len(all_files) <= 1:
                    continue
                
                # Keep the most recent, delete the rest + sidecars
                keep = all_files[0]
                delete_count = len(all_files) - 1
                
                for old_file in all_files[1:]:
                    try:
                        size = os.path.getsize(old_file)
                        os.remove(old_file)
                        total_deleted += 1
                        total_freed += size
                        
                        # Delete ._xx sidecar (version metadata)
                        xx_file = old_file + '._xx'
                        if os.path.exists(xx_file):
                            total_freed += os.path.getsize(xx_file)
                            os.remove(xx_file)
                            total_deleted += 1
                        
                        # Delete .png thumbnail
                        png_file = os.path.splitext(old_file)[0] + '.png'
                        if os.path.exists(png_file):
                            total_freed += os.path.getsize(png_file)
                            os.remove(png_file)
                            total_deleted += 1
                    except (PermissionError, OSError) as e:
                        # File may be locked by Fusion - skip it
                        self.logger.warning(f'Could not delete cached file {os.path.basename(old_file)}: {e}')
                
                self.logger.info(
                    f'Cache cleanup: {model_name} - kept {os.path.basename(keep)}, '
                    f'deleted {delete_count} old version(s)'
                )
            
            if total_deleted > 0:
                self.logger.info(
                    f'Cloud cache cleanup complete: deleted {total_deleted} files, '
                    f'freed {total_freed / 1024:.1f} KB'
                )
            else:
                self.logger.info('Cloud cache cleanup: no stale files found')
                
        except Exception as e:
            self.logger.warning(f'Cloud cache cleanup failed (non-fatal): {str(e)}')
    
    def setup_cloud_models(self, project_name: str = "Bobrick - Component modeling", 
                            folder_name: str = "3X8X Components",
                            door_name: str = "3X8X_Door",
                            door_drawing_name: str = "3X8X_Door Drawing",
                            panel_name: str = "3X8X_Panel",
                            panel_drawing_name: str = None,
                            stile_names: Dict[str, str] = None,
                            stile_drawing_names: Dict[str, str] = None) -> Tuple[bool, str]:
        """
        Set up cloud-based models for all component types from Fusion Hub team project.
        Call this once at startup to configure cloud model usage.
        
        Args:
            project_name: Team project name (e.g., "Bobrick - Component modeling")
            folder_name: Folder within project containing models (e.g., "3X8X Components")
            door_name: Name of door model in Fusion Hub
            door_drawing_name: Name of door drawing in Fusion Hub
            panel_name: Name of panel model in Fusion Hub
            panel_drawing_name: Name of panel drawing in Fusion Hub (optional)
            stile_names: Dictionary mapping series code to stile model name
                         e.g., {'3081': '3X81_Stile', '3082': '3X82_Stile', '3086': '3X86_Stile'}
            stile_drawing_names: Dictionary mapping series code to stile drawing name
                         e.g., {'3082': '3X82_Stile Drawing', '3086': '3X86_Stile Drawing'}
            
        Returns:
            Tuple of (success, message)
        """
        # Default stile names if not provided
        if stile_names is None:
            stile_names = {
                '3081': '3X81_Stile',
                '3082': '3X82_Stile', 
                '3086': '3X86_Stile'
            }
        
        # Default stile drawing names if not provided
        if stile_drawing_names is None:
            stile_drawing_names = {
                '3082': '3X82_Stile Drawing',
                '3086': '3X86_Stile Drawing'
            }
        
        try:
            self.logger.info(f'========== CLOUD MODEL SETUP ==========')
            self.logger.info(f'Project: "{project_name}"')
            self.logger.info(f'Folder: "{folder_name}"')
            self.logger.info(f'Door: "{door_name}", Drawing: "{door_drawing_name}"')
            self.logger.info(f'Panel: "{panel_name}", Drawing: "{panel_drawing_name}"')
            self.logger.info(f'Stiles: {stile_names}')
            
            # Clear stale cloud cache BEFORE opening any cloud documents
            # This prevents STACK_OVERFLOW crashes caused by Fusion's internal
            # version reconciliation loop on lineages with accumulated old versions
            all_model_names = [door_name, door_drawing_name, panel_name]
            if panel_drawing_name:
                all_model_names.append(panel_drawing_name)
            all_model_names.extend(stile_names.values())
            all_model_names.extend(stile_drawing_names.values())
            self._clear_stale_cloud_cache(all_model_names)
            
            # Store project configuration
            self._cloud_project_name = project_name
            self._cloud_folder_name = folder_name
            
            found_models = []
            missing_models = []
            
            # Find door model
            self.logger.info(f'Searching for door model: "{door_name}"...')
            door_file = self._find_cloud_document(door_name, project_name, folder_name)
            if door_file:
                self._cloud_data_files[self.DOOR] = door_file
                found_models.append(f'Door: {door_file.name}')
                self.logger.info(f'Found cloud door model: {door_file.name}')
            else:
                missing_models.append(f'Door: {door_name}')
                self.logger.warning(f'Door model not found: {door_name}')
            
            # Find door drawing
            drawing_file = self._find_cloud_document(door_drawing_name, project_name, folder_name)
            if drawing_file:
                self._door_drawing_data_file = drawing_file
                self.logger.info(f'Found cloud door drawing: {drawing_file.name}')
            else:
                self.logger.warning(f'Door drawing not found: {door_drawing_name}')
            
            # Find panel model
            panel_file = self._find_cloud_document(panel_name, project_name, folder_name)
            if panel_file:
                self._cloud_data_files[self.PANEL] = panel_file
                found_models.append(f'Panel: {panel_file.name}')
                self.logger.info(f'Found cloud panel model: {panel_file.name}')
            else:
                missing_models.append(f'Panel: {panel_name}')
                self.logger.warning(f'Panel model not found: {panel_name}')
            
            # Find panel drawing (if name provided)
            if panel_drawing_name:
                panel_drawing_file = self._find_cloud_document(panel_drawing_name, project_name, folder_name)
                if panel_drawing_file:
                    self._panel_drawing_data_file = panel_drawing_file
                    self.logger.info(f'Found cloud panel drawing: {panel_drawing_file.name}')
                else:
                    self.logger.warning(f'Panel drawing not found: {panel_drawing_name}')
            
            # Find stile models by series
            for series_code, stile_name in stile_names.items():
                stile_file = self._find_cloud_document(stile_name, project_name, folder_name)
                if stile_file:
                    self._cloud_data_files[self.STILE][series_code] = stile_file
                    found_models.append(f'Stile {series_code}: {stile_file.name}')
                    self.logger.info(f'Found cloud stile model for series {series_code}: {stile_file.name}')
                else:
                    missing_models.append(f'Stile {series_code}: {stile_name}')
                    self.logger.warning(f'Stile model not found for series {series_code}: {stile_name}')
            
            # Find stile drawings by series
            for series_code, drawing_name in stile_drawing_names.items():
                drawing_file = self._find_cloud_document(drawing_name, project_name, folder_name)
                if drawing_file:
                    self._stile_drawing_data_files[series_code] = drawing_file
                    self.logger.info(f'Found cloud stile drawing for series {series_code}: {drawing_file.name}')
                else:
                    self.logger.warning(f'Stile drawing not found for series {series_code}: {drawing_name}')
            
            # Enable cloud models if we found at least one
            if found_models:
                self._use_cloud_models = True
                msg = f'Cloud models configured: {len(found_models)} found'
                if missing_models:
                    msg += f', {len(missing_models)} missing (will use local fallback)'
                self.logger.info(msg)
                return True, msg
            else:
                return False, 'No cloud models found in Fusion Hub'
            
        except Exception as e:
            return False, f'Error setting up cloud models: {str(e)}'
    
    def _find_cloud_document(self, doc_name: str, project_name: str = None, 
                              folder_name: str = None) -> Optional[adsk.core.DataFile]:
        """
        Find a document in Fusion Hub by name.
        
        Args:
            doc_name: Name of the document to find
            project_name: Project name to search in (None = search all)
            folder_name: Folder name to search in (None = search all folders)
            
        Returns:
            DataFile if found, None otherwise
        """
        try:
            data = self.app.data
            
            for proj in data.dataProjects.asArray():
                if project_name and proj.name != project_name:
                    continue
                
                # Search root folder files
                found = self._search_folder_for_file(proj.rootFolder, doc_name)
                if found:
                    return found
                
                # Search subfolders
                for folder in proj.rootFolder.dataFolders.asArray():
                    if folder_name and folder.name != folder_name:
                        continue
                    
                    found = self._search_folder_for_file(folder, doc_name)
                    if found:
                        return found
                    
                    # Search nested folders
                    for subfolder in folder.dataFolders.asArray():
                        found = self._search_folder_for_file(subfolder, doc_name)
                        if found:
                            return found
            
            return None
            
        except Exception as e:
            self.logger.error(f'Error finding cloud document {doc_name}: {str(e)}')
            return None
    
    def _search_folder_for_file(self, folder: adsk.core.DataFolder, 
                                 doc_name: str) -> Optional[adsk.core.DataFile]:
        """Search a folder for a file by exact name match."""
        try:
            for file in folder.dataFiles.asArray():
                if file.name == doc_name:
                    return file
            return None
        except Exception as e:
            self.logger.warning(f'Error searching folder for "{doc_name}": {e}')
            return None
    
    def _close_non_door_cloud_docs(self, keep_key: str = None):
        """
        Close all non-door cloud documents to limit simultaneous cloud doc count.
        
        Fusion's internal CurrentlyOpenDocumentsCommand iterates all open cloud
        documents and spawns PLM360OpenAttachmentCommand for each. With 5 cloud
        docs open, this creates a recursive chain 10+ commands deep that causes
        STACK_OVERFLOW. By closing non-door cloud docs before opening a new one,
        we keep at most 2 cloud documents open (door + current working model).
        
        Args:
            keep_key: Cache key to keep open (e.g., the doc we're about to use).
                      If already open, it won't be closed.
        """
        try:
            keys_to_close = []
            for cache_key, doc in list(self._cached_documents.items()):
                # Never close the door — it needs cloud linkage for save
                if cache_key == "door_cloud":
                    continue
                # Don't close the doc we're about to use
                if cache_key == keep_key:
                    continue
                # Only close cloud docs (keys ending in '_cloud')
                if not cache_key.endswith('_cloud'):
                    continue
                keys_to_close.append(cache_key)
            
            for cache_key in keys_to_close:
                doc = self._cached_documents.get(cache_key)
                if doc and doc.isValid:
                    try:
                        self.logger.info(f'Closing cloud doc to reduce open count: {cache_key} ({doc.name})')
                        doc.close(False)  # close without saving
                    except Exception as e:
                        self.logger.warning(f'Error closing {cache_key}: {e}')
                # Remove from cache either way so it gets re-opened next time
                if cache_key in self._cached_documents:
                    del self._cached_documents[cache_key]
            
            if keys_to_close:
                self.logger.info(f'Closed {len(keys_to_close)} non-door cloud doc(s): {keys_to_close}')
        except Exception as e:
            self.logger.warning(f'Error in _close_non_door_cloud_docs: {e}')
    
    def _open_cloud_model(self, component_type: str, data_file: adsk.core.DataFile, 
                           cache_key: str) -> Tuple[bool, Optional[adsk.core.Document], str]:
        """
        Internal method to open a cloud-based model from Fusion Hub.
        
        Uses a multi-step approach:
        1. Check our Python cache first
        2. Scan app.documents for an already-open document matching this DataFile
        3. Re-fetch the DataFile to ensure it's fresh, then call documents.open()
        
        Args:
            component_type: Type of component for logging
            data_file: DataFile to open
            cache_key: Key for caching the document
            
        Returns:
            Tuple of (success, document, message)
        """
        try:
            # Step 1: Check our Python cache first
            if cache_key in self._cached_documents:
                doc = self._cached_documents[cache_key]
                if doc.isValid:
                    # Skip activate() if this doc is already active.
                    # Each activate() on a cloud doc triggers Fusion's internal
                    # version polling/reconciliation. After hundreds of redundant
                    # activate() calls on a high-version cloud doc, the accumulated
                    # internal state causes PLM360 hang/crash.
                    try:
                        already_active = (self.app.activeDocument == doc)
                    except Exception:
                        already_active = False
                    if already_active:
                        self.logger.info(f'Cached cloud {component_type} model already active: {doc.name}')
                    else:
                        self.logger.info(f'Activating cached cloud {component_type} model: {doc.name}')
                        doc.activate()
                    return True, doc, f'Switched to cloud {component_type} model: {doc.name}'
                else:
                    del self._cached_documents[cache_key]
            
            # Step 2: Scan already-open documents for a matching DataFile
            try:
                for existing_doc in self.app.documents:
                    try:
                        if (existing_doc.isValid and 
                            hasattr(existing_doc, 'dataFile') and 
                            existing_doc.dataFile and 
                            existing_doc.dataFile.id == data_file.id):
                            self.logger.info(
                                f'Found already-open cloud {component_type} model: '
                                f'{existing_doc.name} (skipping documents.open)')
                            existing_doc.activate()
                            self._cached_documents[cache_key] = existing_doc
                            return True, existing_doc, f'Reused open cloud {component_type} model: {existing_doc.name}'
                    except Exception:
                        continue
            except Exception as e:
                self.logger.warning(f'Error scanning open documents: {str(e)}')
            
            # Step 3: Re-fetch the DataFile to ensure it's fresh
            # A stale DataFile (obtained minutes earlier during setup) can trigger
            # Fusion's internal version reconciliation loop on open.
            fresh_data_file = data_file
            try:
                if (self._cloud_project_name and self._cloud_folder_name and 
                    data_file.name):
                    self.logger.info(f'Re-fetching DataFile for {data_file.name}...')
                    refetched = self._find_cloud_document(
                        data_file.name, 
                        self._cloud_project_name, 
                        self._cloud_folder_name
                    )
                    if refetched:
                        fresh_data_file = refetched
                        self.logger.info(f'Using fresh DataFile for {data_file.name}')
                    else:
                        self.logger.warning(f'Could not re-fetch DataFile for {data_file.name}, using original')
            except Exception as e:
                self.logger.warning(f'DataFile re-fetch failed: {e}')
            
            # Step 4: Open from cloud
            self.logger.info(
                f'Opening cloud {component_type} model: {fresh_data_file.name} '
                f'(documents count before: {self.app.documents.count})'
            )
            doc = self.app.documents.open(fresh_data_file)
            
            if not doc:
                return False, None, f'Failed to open cloud {component_type} model'
            
            # Cache and activate - no doEvents pumping to avoid triggering
            # Fusion's internal close/reopen cycle
            self._cached_documents[cache_key] = doc
            doc.activate()
            
            self.logger.info(
                f'Opened cloud {component_type} model: {doc.name} '
                f'(documents count after: {self.app.documents.count})'
            )
            return True, doc, f'Opened cloud {component_type} model: {doc.name}'
            
        except Exception as e:
            return False, None, f'Error opening cloud {component_type} model: {str(e)}'
    
    def open_cloud_door_model(self) -> Tuple[bool, Optional[adsk.core.Document], str]:
        """
        Open the cloud-based door model from Fusion Hub.
        
        Returns:
            Tuple of (success, document, message)
        """
        data_file = self._cloud_data_files[self.DOOR]
        if not data_file:
            return False, None, 'Cloud door model not configured. Call setup_cloud_models first.'
        
        return self._open_cloud_model(self.DOOR, data_file, "door_cloud")
    
    def open_cloud_panel_model(self) -> Tuple[bool, Optional[adsk.core.Document], str]:
        """
        Open the cloud-based panel model from Fusion Hub.
        
        Does NOT close other cloud documents. All cloud docs are saved after
        parameter application (clearing the Dirty flag), so multiple clean
        cloud docs can coexist safely. doc.close() hangs on cloud documents
        with many saved versions.
        
        Returns:
            Tuple of (success, document, message)
        """
        data_file = self._cloud_data_files[self.PANEL]
        if not data_file:
            return False, None, 'Cloud panel model not configured. Call setup_cloud_models first.'
        
        return self._open_cloud_model(self.PANEL, data_file, "panel_cloud")
    
    def open_cloud_stile_model(self, series_id: str) -> Tuple[bool, Optional[adsk.core.Document], str]:
        """
        Open the cloud-based stile model for a specific series from Fusion Hub.
        
        Does NOT close other cloud documents. All cloud docs are saved after
        parameter application (clearing the Dirty flag), so multiple clean
        cloud docs can coexist safely. doc.close() hangs on cloud documents
        with many saved versions.
        
        Args:
            series_id: Series identifier (e.g., '3082G.67P')
            
        Returns:
            Tuple of (success, document, message)
        """
        series_code = self._extract_series_code(series_id)
        if not series_code:
            return False, None, f'Could not extract series code from: {series_id}'
        
        data_file = self._cloud_data_files[self.STILE].get(series_code)
        if not data_file:
            return False, None, f'Cloud stile model not configured for series {series_code}. Call setup_cloud_models first.'
        
        cache_key = f"stile_{series_code}_cloud"
        
        return self._open_cloud_model(f'{self.STILE} ({series_code})', data_file, cache_key)
    
    def save_door_model(self, save_message: str = "Updated by automation", 
                        wait_for_cloud: bool = True, timeout_seconds: int = 60) -> Tuple[bool, str]:
        """
        Save the current door model and wait for the cloud upload to complete.
        This is required before the drawing can be updated, because the drawing
        references the cloud version of the model.
        
        Uses the Application.dataFileComplete event to detect when the upload
        (including cloud-side translations) has finished.
        
        Args:
            save_message: Version comment for the save
            wait_for_cloud: If True, block until the cloud upload completes
            timeout_seconds: Maximum seconds to wait for cloud sync
            
        Returns:
            Tuple of (success, message)
        """
        try:
            cache_key = "door_cloud"
            if cache_key not in self._cached_documents:
                return False, 'No cloud door model is open'
            
            doc = self._cached_documents[cache_key]
            if not doc.isValid:
                return False, 'Door model document is no longer valid'
            
            # Ensure the door model is the active document before saving
            try:
                if self.app.activeDocument != doc:
                    self.logger.info(f'Activating door model before save (was: {self.app.activeDocument.name})')
                    doc.activate()
                    time.sleep(0.5)
            except Exception as e:
                self.logger.warning(f'Could not check/activate document: {str(e)}')
            
            # Log document state before save
            try:
                self.logger.info(f'Door model isModified: {doc.isModified}')
                self.logger.info(f'Door model name: {doc.name}')
                self.logger.info(f'Active document: {self.app.activeDocument.name}')
            except Exception as e:
                self.logger.info(f'Could not log doc state: {str(e)}')
            
            # Record the version number before saving so we can confirm it incremented
            pre_save_version = None
            try:
                if doc.dataFile:
                    pre_save_version = doc.dataFile.versionNumber
                    self.logger.info(f'Door model version before save: v{pre_save_version}')
            except Exception:
                pass
            
            if wait_for_cloud:
                # Set up the dataFileComplete event to detect when the upload finishes
                save_completed = threading.Event()
                save_error = [None]  # Use list to allow mutation in handler
                
                class SaveCompleteHandler(adsk.core.DataEventHandler):
                    def __init__(self, target_doc, logger):
                        super().__init__()
                        self._target_doc = target_doc
                        self._logger = logger
                    
                    def notify(self, args: adsk.core.DataEventArgs):
                        try:
                            # Check if this is the file we saved
                            completed_file = args.file
                            if completed_file and self._target_doc.dataFile:
                                if completed_file.id == self._target_doc.dataFile.id:
                                    self._logger.info(f'dataFileComplete fired for door model: {completed_file.name}')
                                    save_completed.set()
                        except Exception as e:
                            save_error[0] = str(e)
                            save_completed.set()
                
                handler = SaveCompleteHandler(doc, self.logger)
                self.app.dataFileComplete.add(handler)
                
                try:
                    self.logger.info('Saving door model to cloud (waiting for sync)...')
                    doc.save(save_message)
                    
                    # Poll with throttled doEvents to let both the save execute
                    # and the dataFileComplete callback fire. threading.Event.wait()
                    # blocks the UI thread entirely, preventing the save from
                    # processing and the callback from firing. Instead, we pump
                    # doEvents at 1s intervals — enough for the save to work,
                    # slow enough to avoid PLM360 pressure buildup.
                    start_time = time.time()
                    while not save_completed.is_set():
                        adsk.doEvents()
                        time.sleep(1.0)
                        if time.time() - start_time > timeout_seconds:
                            break
                    elapsed = time.time() - start_time
                    
                    if save_error[0]:
                        return False, f'Error during cloud sync: {save_error[0]}'
                    
                    if save_completed.is_set():
                        self.logger.info(f'Door model cloud sync completed in {elapsed:.1f}s')
                    else:
                        self.logger.warning(f'Cloud sync timed out after {timeout_seconds}s, proceeding anyway')
                    
                finally:
                    # Always clean up the event handler
                    try:
                        self.app.dataFileComplete.remove(handler)
                    except Exception:
                        pass
                
                # Verify version incremented
                try:
                    if doc.dataFile and pre_save_version is not None:
                        post_save_version = doc.dataFile.versionNumber
                        self.logger.info(f'Door model version after save: v{post_save_version}')
                        if post_save_version > pre_save_version:
                            return True, f'Door model saved and synced (v{pre_save_version} -> v{post_save_version}, {elapsed:.1f}s)'
                        else:
                            self.logger.warning(f'Version did not increment (v{pre_save_version} -> v{post_save_version})')
                except Exception:
                    pass
                
                return True, f'Door model saved and synced ({elapsed:.1f}s)'
            
            else:
                # Fire-and-forget save — still need one doEvents() to let save execute
                self.logger.info('Saving door model to cloud (no sync wait)...')
                doc.save(save_message)
                adsk.doEvents()
                time.sleep(0.5)
                self.logger.info('Door model save initiated')
                return True, 'Door model save initiated (not waiting for cloud sync)'
            
        except Exception as e:
            return False, f'Error saving door model: {str(e)}'
    
    def save_active_model(self, save_message: str = "Updated by automation") -> Tuple[bool, str]:
        """
        Save the currently active cloud document to clear the Dirty flag.
        
        After parameter application, Fusion marks cloud documents as Dirty.
        Dirty cloud documents trigger Fusion's internal PLM360 version
        reconciliation polling loop (WIPRequest7 every ~15s), which during
        doEvents() processing builds a recursive PLM360OpenAttachmentCommand →
        CurrentlyOpenDocumentsCommand chain that eventually causes
        STACK_OVERFLOW crashes.
        
        This method saves the active document to clear the Dirty flag,
        stopping the version reconciliation polling. Pumps one doEvents()
        after doc.save() to ensure the save actually executes — without it,
        the save is silently ignored when the UI thread is blocked by our
        add-in's continuous processing. The cloud upload happens async.
        
        Args:
            save_message: Version comment for the save
            
        Returns:
            Tuple of (success, message)
        """
        try:
            doc = self.app.activeDocument
            if not doc or not doc.isValid:
                return False, 'No valid active document to save'
            
            doc_name = doc.name
            
            # Only save if the document is actually modified
            if not doc.isModified:
                self.logger.info(f'Model {doc_name} is not modified, skip save')
                return True, f'{doc_name}: not modified, no save needed'
            
            # Log state before save
            pre_save_version = None
            try:
                if doc.dataFile:
                    pre_save_version = doc.dataFile.versionNumber
                    self.logger.info(f'Saving {doc_name} (v{pre_save_version}, isModified={doc.isModified})')
            except Exception:
                self.logger.info(f'Saving {doc_name} (isModified={doc.isModified})')
            
            # doc.save() queues a save command on Fusion's internal command
            # queue. At high version counts (v100+), the save command needs
            # continuous UI-thread event pumping to complete — a single
            # doEvents() is not enough and doc.save() itself can block
            # indefinitely. We poll doEvents() at 1s intervals with a timeout
            # to let the save complete without freezing.
            doc.save(save_message)
            
            # Poll doEvents to let the save execute and clear the Dirty flag.
            # Timeout after 30s — if the save hasn't completed by then, proceed
            # anyway (cloud upload continues async).
            save_timeout = 30
            start_time = time.time()
            save_cleared = False
            while time.time() - start_time < save_timeout:
                adsk.doEvents()
                time.sleep(1.0)
                try:
                    if not doc.isValid:
                        self.logger.warning(f'{doc_name}: Document became invalid during save')
                        break
                    if not doc.isModified:
                        save_cleared = True
                        break
                except Exception:
                    break
            
            elapsed = time.time() - start_time
            if save_cleared:
                self.logger.info(f'Save completed for {doc_name} in {elapsed:.1f}s')
            else:
                self.logger.warning(f'{doc_name}: Dirty flag not cleared after {elapsed:.1f}s — proceeding anyway')
            
            return True, f'{doc_name}: saved (clearing dirty flag, {elapsed:.1f}s)'
            
        except Exception as e:
            return False, f'Error saving active model: {str(e)}'
    
    def save_active_model_for_drawing(self, save_message: str = "Updated by automation",
                                      timeout_seconds: int = 60) -> Tuple[bool, str]:
        """
        Save the currently active cloud document and wait for cloud sync.
        
        Like save_door_model(wait_for_cloud=True) but works on any active doc.
        Required before opening a drawing that references this model — the
        drawing document's cloud open will hang indefinitely if the model's
        cloud-side translation hasn't finished yet.
        
        Args:
            save_message: Version comment for the save
            timeout_seconds: Maximum seconds to wait for cloud sync
            
        Returns:
            Tuple of (success, message)
        """
        try:
            doc = self.app.activeDocument
            if not doc or not doc.isValid:
                return False, 'No valid active document to save'
            
            doc_name = doc.name
            needs_save = doc.isModified
            
            # Record current version
            pre_version = None
            try:
                if doc.dataFile:
                    pre_version = doc.dataFile.versionNumber
                    self.logger.info(f'{doc_name} current version: v{pre_version}, isModified={needs_save}')
            except Exception:
                pass
            
            # Set up dataFileComplete event to detect when cloud translation finishes.
            # We listen for this EVEN if isModified=False, because a prior
            # save_active_model() may have cleared the dirty flag while the
            # cloud upload/translation is still in progress.
            save_completed = threading.Event()
            save_error = [None]
            
            class SaveCompleteHandler(adsk.core.DataEventHandler):
                def __init__(self, target_doc, logger):
                    super().__init__()
                    self._target_doc = target_doc
                    self._logger = logger
                
                def notify(self, args: adsk.core.DataEventArgs):
                    try:
                        completed_file = args.file
                        if completed_file and self._target_doc.dataFile:
                            if completed_file.id == self._target_doc.dataFile.id:
                                self._logger.info(f'dataFileComplete fired for {completed_file.name}')
                                save_completed.set()
                    except Exception as e:
                        save_error[0] = str(e)
                        save_completed.set()
            
            handler = SaveCompleteHandler(doc, self.logger)
            self.app.dataFileComplete.add(handler)
            
            try:
                if needs_save:
                    self.logger.info(f'Saving {doc_name} to cloud (waiting for sync)...')
                    doc.save(save_message)
                else:
                    self.logger.info(f'{doc_name} not modified — waiting for any in-flight cloud sync...')
                
                # Poll with throttled doEvents to let save execute and callback fire.
                # Even when not saving, a prior save_active_model() may have kicked
                # off a cloud upload that hasn't finished yet.
                # Use shorter timeout when not saving — we're just waiting for in-flight sync.
                effective_timeout = timeout_seconds if needs_save else min(15, timeout_seconds)
                start_time = time.time()
                poll_count = 0
                while not save_completed.is_set():
                    adsk.doEvents()
                    time.sleep(1.0)
                    poll_count += 1
                    # Check version every ~10s to exit early if save completed
                    # without the dataFileComplete event firing
                    if needs_save and pre_version and poll_count % 10 == 0:
                        try:
                            cur_ver = doc.dataFile.versionNumber
                            if cur_ver > pre_version:
                                self.logger.info(f'{doc_name} version incremented (v{pre_version} -> v{cur_ver}), sync complete')
                                save_completed.set()
                                break
                        except Exception:
                            pass
                    if time.time() - start_time > effective_timeout:
                        break
                elapsed = time.time() - start_time
                
                if save_error[0]:
                    return False, f'Error during cloud sync: {save_error[0]}'
                
                if save_completed.is_set():
                    self.logger.info(f'{doc_name} cloud sync completed in {elapsed:.1f}s')
                else:
                    if needs_save:
                        # Primary timeout expired but save may still be in progress.
                        # Check if version incremented — if not, wait longer.
                        try:
                            post_ver = doc.dataFile.versionNumber if doc.dataFile else None
                            if post_ver and pre_version and post_ver > pre_version:
                                self.logger.info(f'{doc_name} version incremented during timeout (v{pre_version} -> v{post_ver}, {elapsed:.1f}s)')
                            else:
                                # Version hasn't incremented — wait up to 30 more seconds
                                self.logger.warning(f'Cloud sync not confirmed after {elapsed:.1f}s, extending wait...')
                                ext_start = time.time()
                                while time.time() - ext_start < 30:
                                    adsk.doEvents()
                                    time.sleep(5.0)
                                    if save_completed.is_set():
                                        break
                                    try:
                                        post_ver = doc.dataFile.versionNumber
                                        if post_ver and post_ver > pre_version:
                                            self.logger.info(f'{doc_name} version incremented in extended wait (v{pre_version} -> v{post_ver})')
                                            break
                                    except Exception:
                                        pass
                                elapsed = time.time() - start_time
                                if not save_completed.is_set():
                                    try:
                                        final_ver = doc.dataFile.versionNumber
                                        if final_ver and final_ver > pre_version:
                                            self.logger.info(f'{doc_name} sync confirmed via version check (v{pre_version} -> v{final_ver}, {elapsed:.1f}s)')
                                        else:
                                            self.logger.warning(f'Cloud sync timed out after {elapsed:.1f}s, proceeding anyway')
                                    except Exception:
                                        self.logger.warning(f'Cloud sync timed out after {elapsed:.1f}s, proceeding anyway')
                        except Exception:
                            self.logger.warning(f'Cloud sync timed out after {elapsed:.1f}s, proceeding anyway')
                    else:
                        # No save was needed and no dataFileComplete fired — 
                        # cloud was likely already up to date from a previous sync
                        self.logger.info(f'{doc_name} no in-flight sync detected after {elapsed:.1f}s — cloud is up to date')
                
            finally:
                try:
                    self.app.dataFileComplete.remove(handler)
                except Exception:
                    pass
            
            # Verify version
            try:
                if doc.dataFile and pre_version is not None:
                    post_version = doc.dataFile.versionNumber
                    self.logger.info(f'{doc_name} version after sync: v{post_version}')
                    if needs_save and post_version > pre_version:
                        return True, f'{doc_name} saved and synced (v{pre_version} -> v{post_version}, {elapsed:.1f}s)'
                    elif needs_save:
                        self.logger.warning(f'Version did not increment (v{pre_version} -> v{post_version})')
            except Exception:
                pass
            
            if needs_save:
                return True, f'{doc_name} saved and synced ({elapsed:.1f}s)'
            else:
                return True, f'{doc_name} cloud sync verified ({elapsed:.1f}s)'
            
        except Exception as e:
            return False, f'Error saving model for drawing: {str(e)}'
    
    def get_door_drawing_data_file(self) -> Optional[adsk.core.DataFile]:
        """Get the DataFile for the door drawing (for use with DrawingExporter)."""
        return self._door_drawing_data_file
    
    def get_panel_drawing_data_file(self) -> Optional[adsk.core.DataFile]:
        """Get the DataFile for the panel drawing (for use with DrawingExporter)."""
        return self._panel_drawing_data_file
    
    def get_stile_drawing_data_file(self, series_id: str) -> Optional[adsk.core.DataFile]:
        """Get the DataFile for a stile drawing by series ID (for use with DrawingExporter)."""
        series_code = self._extract_series_code(series_id)
        if series_code and series_code in self._stile_drawing_data_files:
            return self._stile_drawing_data_files[series_code]
        return None
    
    def open_drawing_documents(self) -> Tuple[bool, str]:
        """
        Open all configured drawing documents at startup.
        
        Cloud drawing documents take 5-10+ minutes to open via documents.open()
        and sometimes hang indefinitely. Opening them once at startup (when the
        wait is acceptable) and caching them avoids the per-order hang.
        
        The opened documents are cached in _cached_drawing_docs and can be
        retrieved via get_cached_drawing_doc().
        
        Returns:
            Tuple of (success, message)
        """
        opened = []
        failed = []
        
        drawing_configs = []
        
        # Door drawing
        if self._door_drawing_data_file:
            drawing_configs.append(('door_drawing', self._door_drawing_data_file))
        
        # Panel drawing
        if self._panel_drawing_data_file:
            drawing_configs.append(('panel_drawing', self._panel_drawing_data_file))
        
        # Stile drawings
        for series_code, data_file in self._stile_drawing_data_files.items():
            if data_file:
                drawing_configs.append((f'stile_{series_code}_drawing', data_file))
        
        if not drawing_configs:
            return True, 'No drawing documents configured'
        
        self.logger.info(f'Opening {len(drawing_configs)} drawing document(s) at startup...')
        self.logger.info(f'Current documents count: {self.app.documents.count}')
        
        for cache_key, data_file in drawing_configs:
            try:
                # Log DataFile properties for debugging
                self.logger.info(f'--- Drawing: {data_file.name} (key={cache_key}) ---')
                try:
                    self.logger.info(f'  DataFile.id: {data_file.id}')
                    self.logger.info(f'  DataFile.fileExtension: {data_file.fileExtension}')
                    self.logger.info(f'  DataFile.versionNumber: {data_file.versionNumber}')
                    if hasattr(data_file, 'latestVersionNumber'):
                        self.logger.info(f'  DataFile.latestVersionNumber: {data_file.latestVersionNumber}')
                    if hasattr(data_file, 'hasChildReferences'):
                        self.logger.info(f'  DataFile.hasChildReferences: {data_file.hasChildReferences}')
                    if hasattr(data_file, 'hasParentReferences'):
                        self.logger.info(f'  DataFile.hasParentReferences: {data_file.hasParentReferences}')
                except Exception as prop_e:
                    self.logger.info(f'  (could not read some DataFile properties: {prop_e})')
                
                # Check if already open in Fusion
                already_open = False
                try:
                    for existing_doc in self.app.documents:
                        try:
                            if (existing_doc.isValid and
                                hasattr(existing_doc, 'dataFile') and
                                existing_doc.dataFile and
                                existing_doc.dataFile.id == data_file.id):
                                self.logger.info(f'Drawing already open: {existing_doc.name}')
                                self._cached_drawing_docs[cache_key] = existing_doc
                                opened.append(data_file.name)
                                already_open = True
                                break
                        except Exception:
                            continue
                except Exception:
                    pass
                
                if already_open:
                    continue
                
                # Re-fetch DataFile for freshness
                fresh_data_file = data_file
                try:
                    if self._cloud_project_name and self._cloud_folder_name:
                        self.logger.info(f'Re-fetching DataFile for {data_file.name}...')
                        refetched = self._find_cloud_document(
                            data_file.name,
                            self._cloud_project_name,
                            self._cloud_folder_name
                        )
                        if refetched:
                            fresh_data_file = refetched
                            self.logger.info(f'Using fresh DataFile: id={fresh_data_file.id}, v{fresh_data_file.versionNumber}')
                        else:
                            self.logger.warning(f'Re-fetch returned None, using original DataFile')
                except Exception as e:
                    self.logger.warning(f'Re-fetch failed: {e}')
                
                # Open from cloud — synchronous call.
                # WARNING: On the VM, documents.open() for .f2d files can hang
                # indefinitely. This method is only called if explicitly
                # requested (not during normal startup). If it hangs, the user
                # must restart Fusion.
                doc_count_before = self.app.documents.count
                self.logger.info(f'Calling documents.open() for {fresh_data_file.name} (docs before: {doc_count_before})...')
                open_start = time.time()
                
                try:
                    doc = self.app.documents.open(fresh_data_file, True)
                except TypeError:
                    doc = self.app.documents.open(fresh_data_file)
                
                open_elapsed = time.time() - open_start
                doc_count_after = self.app.documents.count
                self.logger.info(f'documents.open() returned in {open_elapsed:.1f}s (docs after: {doc_count_after})')
                
                if doc:
                    self.logger.info(f'Returned doc: name={doc.name}, isValid={doc.isValid}')
                    try:
                        drawing_cast = adsk.drawing.DrawingDocument.cast(doc)
                        self.logger.info(f'DrawingDocument cast: {"success" if drawing_cast else "FAILED (not a DrawingDocument)"}')
                    except Exception as cast_e:
                        self.logger.info(f'DrawingDocument cast error: {cast_e}')
                    
                    self._cached_drawing_docs[cache_key] = doc
                    opened.append(data_file.name)
                    self.logger.info(f'Drawing cached: {data_file.name} -> key={cache_key}')
                    time.sleep(1.0)  # Brief pause between opens
                else:
                    failed.append(data_file.name)
                    self.logger.warning(f'documents.open() returned None for {data_file.name}')
                    
            except Exception as e:
                failed.append(data_file.name)
                self.logger.error(f'Error opening drawing {data_file.name}: {str(e)}')
        
        # Re-activate the door model so we're back in the Design workspace
        try:
            if "door_cloud" in self._cached_documents:
                door_doc = self._cached_documents["door_cloud"]
                if door_doc.isValid:
                    door_doc.activate()
                    time.sleep(0.5)
        except Exception:
            pass
        
        msg_parts = []
        if opened:
            msg_parts.append(f'Opened: {", ".join(opened)}')
        if failed:
            msg_parts.append(f'Failed: {", ".join(failed)}')
        msg = '; '.join(msg_parts) if msg_parts else 'No drawings opened'
        
        self.logger.info(f'Drawing documents: {msg}')
        return len(opened) > 0, msg
    
    def get_cached_drawing_doc(self, cache_key: str):
        """
        Get a pre-opened drawing document from cache.
        
        Args:
            cache_key: Cache key (e.g., 'door_drawing', 'stile_3086_drawing')
            
        Returns:
            Cached Document or None if not found/invalid
        """
        doc = self._cached_drawing_docs.get(cache_key)
        if doc and doc.isValid:
            return doc
        if doc:
            # Invalid — remove from cache
            del self._cached_drawing_docs[cache_key]
        return None
    
    def is_using_cloud_models(self) -> bool:
        """Check if cloud models are configured and enabled."""
        return self._use_cloud_models
    
    def is_using_cloud_door(self) -> bool:
        """Check if cloud door model is configured and enabled."""
        return self._use_cloud_models and self._cloud_data_files[self.DOOR] is not None
    
    def is_using_cloud_panel(self) -> bool:
        """Check if cloud panel model is configured and enabled."""
        return self._use_cloud_models and self._cloud_data_files[self.PANEL] is not None
    
    def is_using_cloud_stile(self, series_id: str = None) -> bool:
        """
        Check if cloud stile model is configured for a series.
        
        Args:
            series_id: Series identifier (e.g., '3082G.67P')
            
        Returns:
            True if cloud stile model is available for this series
        """
        if not self._use_cloud_models:
            return False
        
        stile_files = self._cloud_data_files[self.STILE]
        if not stile_files:
            return False
        
        if series_id:
            series_code = self._extract_series_code(series_id)
            return series_code in stile_files
        
        # If no series specified, return True if any stile is available
        return len(stile_files) > 0
    
    def get_cloud_stile_data_file(self, series_id: str) -> Optional[adsk.core.DataFile]:
        """
        Get the cloud DataFile for a stile model based on series.
        
        Args:
            series_id: Series identifier (e.g., '3082G.67P')
            
        Returns:
            DataFile if found, None otherwise
        """
        if not self._use_cloud_models:
            return None
        
        series_code = self._extract_series_code(series_id)
        if series_code:
            return self._cloud_data_files[self.STILE].get(series_code)
        return None
    
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
        Checks cloud models first, then falls back to local paths.
        
        Args:
            component_type: Type of component (door, panel, stile)
            
        Returns:
            True if model is available
        """
        # Check cloud models first
        if component_type == self.DOOR and self.is_using_cloud_door():
            return True
        if component_type == self.PANEL and self.is_using_cloud_panel():
            return True
        if component_type == self.STILE and self.is_using_cloud_stile():
            return True
        
        # Fall back to local path check
        path = self.get_model_path(component_type)
        return path is not None and os.path.exists(path)
    
    def get_available_models(self) -> Dict[str, Optional[str]]:
        """
        Get all available models and their paths/status.
        Shows 'cloud' for cloud models, local path for local models, or None.
        
        Returns:
            Dictionary mapping component type to path/status (or None)
        """
        result = {}
        
        # Door
        if self.is_using_cloud_door():
            result[self.DOOR] = 'cloud'
        else:
            result[self.DOOR] = self._model_paths[self.DOOR]
        
        # Panel
        if self.is_using_cloud_panel():
            result[self.PANEL] = 'cloud'
        else:
            result[self.PANEL] = self._model_paths[self.PANEL]
        
        # Stile
        if self.is_using_cloud_stile():
            stile_series = list(self._cloud_data_files[self.STILE].keys())
            result[self.STILE] = f'cloud ({", ".join(stile_series)})'
        else:
            result[self.STILE] = self._model_paths[self.STILE]
        
        return result
    
    def open_all_models(self) -> Tuple[bool, str]:
        """
        Open models at startup.
        
        Only the DOOR model is opened eagerly — it's the only model that needs
        persistent cloud linkage (for save back to cloud + drawing export).
        
        Panel and stile models are opened ON-DEMAND when needed for each order,
        and closed afterward. This limits simultaneous cloud documents to at most
        2 (door + current working model), preventing Fusion's internal
        PLM360OpenAttachmentCommand → CurrentlyOpenDocumentsCommand recursive
        loop that causes STACK_OVERFLOW with 5+ simultaneous cloud docs.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            import time
            opened_models = []
            skipped_models = []
            deferred_models = []
            
            # Open ONLY the door model at startup (cloud)
            if self.is_using_cloud_door():
                success, doc, msg = self.open_cloud_door_model()
                if success:
                    opened_models.append(f"door (cloud)")
                    self.logger.info(f'Opened cloud door model at startup: {msg}')
                    # Brief stabilization for the single cloud doc open.
                    # Do NOT call doEvents() — it pumps Fusion's PLM360 command queue.
                    time.sleep(2.0)
                else:
                    skipped_models.append(f"door (cloud open failed: {msg})")
                    self.logger.warning(f'Could not open cloud door: {msg}')
            else:
                model_path = self.get_model_path(self.DOOR)
                if model_path and os.path.exists(model_path):
                    self.logger.info(f'Opening door model: {model_path}')
                    import_manager = self.app.importManager
                    import_options = import_manager.createFusionArchiveImportOptions(model_path)
                    doc = import_manager.importToNewDocument(import_options)
                    if doc:
                        self._cached_documents[self.DOOR] = doc
                        opened_models.append(self.DOOR)
                        self.logger.info(f'Successfully opened door model: {doc.name}')
                    else:
                        skipped_models.append(f"door (failed to open)")
                else:
                    skipped_models.append(f"door (no model configured)")
            
            # Panel and stile are deferred to on-demand — NOT opened at startup.
            # This keeps only 1 cloud document open at idle, preventing the
            # PLM360 recursive crash that occurs with multiple cloud docs.
            if self.is_using_cloud_panel():
                deferred_models.append("panel (cloud, on-demand)")
            if self.is_using_cloud_stile():
                stile_series = list(self._cloud_data_files[self.STILE].keys())
                deferred_models.append(f"stile (cloud, on-demand: {', '.join(stile_series)})")
            
            # Build message
            msg_parts = []
            if opened_models:
                msg_parts.append(f"Opened: {', '.join(opened_models)}")
            if deferred_models:
                msg_parts.append(f"Deferred: {', '.join(deferred_models)}")
            if skipped_models:
                msg_parts.append(f"Skipped: {', '.join(skipped_models)}")
            
            message = '\n'.join(msg_parts) if msg_parts else "No models configured"
            
            success = len(opened_models) > 0
            
            self.logger.info(f'========== STARTUP MODEL SUMMARY ==========')
            self.logger.info(message)
            
            return success, message
            
        except Exception as e:
            msg = f'Exception opening models: {str(e)}'
            self.logger.exception(msg)
            return False, msg
    
    def get_stile_model_path(self, series_id: str) -> Optional[str]:
        """
        Get the stile model path based on series ID.
        
        Args:
            series_id: Series identifier (e.g., '3082G.67P', '3081G', '3086')
            
        Returns:
            Path to stile model or None if not found
        """
        series_code = self._extract_series_code(series_id)
        
        if series_code and series_code in self._stile_models:
            path = self._stile_models[series_code]
            self.logger.info(f'Found stile model for series {series_code}: {path}')
            return path
        
        # Fallback to default stile model
        self.logger.warning(f'No stile model found for series "{series_id}" (code: {series_code}), using default')
        return self._model_paths[self.STILE]
    
    def is_model_available_for_series(self, component_type: str, series_id: str = None) -> bool:
        """
        Check if a model is available for a component type and optional series.
        
        Args:
            component_type: Type of component (door, panel, stile)
            series_id: Optional series identifier for stiles
            
        Returns:
            True if model is available
        """
        # Check cloud models first
        if component_type == self.DOOR and self.is_using_cloud_door():
            return True
        if component_type == self.PANEL and self.is_using_cloud_panel():
            return True
        if component_type == self.STILE and self.is_using_cloud_stile(series_id):
            return True
        
        # Fall back to local models
        if component_type == self.STILE and series_id:
            path = self.get_stile_model_path(series_id)
        else:
            path = self.get_model_path(component_type)
        return path is not None and os.path.exists(path)
    
    def open_model(self, component_type: str, series_id: str = None) -> Tuple[bool, Optional[adsk.core.Document], str]:
        """
        Switch to the model for a specific component type.
        Uses cloud models if configured, otherwise falls back to local files.
        For stiles, uses series_id to select the appropriate model.
        Uses cached document if available.
        
        Args:
            component_type: Type of component (door, panel, stile)
            series_id: Optional series identifier for stiles (e.g., '3082G.67P')
            
        Returns:
            Tuple of (success, document, message)
        """
        try:
            # Try cloud models first
            if component_type == self.DOOR and self.is_using_cloud_door():
                return self.open_cloud_door_model()
            
            if component_type == self.PANEL and self.is_using_cloud_panel():
                return self.open_cloud_panel_model()
            
            if component_type == self.STILE and series_id and self.is_using_cloud_stile(series_id):
                return self.open_cloud_stile_model(series_id)
            
            # Fall back to local models
            # Determine model path based on component type and series
            if component_type == self.STILE and series_id:
                model_path = self.get_stile_model_path(series_id)
                series_code = self._extract_series_code(series_id)
                cache_key = f"stile_{series_code}" if series_code else "stile_default"
            else:
                model_path = self.get_model_path(component_type)
                cache_key = component_type
            
            # Check if we have a cached document for this specific model
            if cache_key in self._cached_documents:
                doc = self._cached_documents[cache_key]
                
                # Verify document is still valid
                if doc.isValid:
                    # Activate it
                    self.logger.info(f'Activating cached {cache_key} model: {doc.name}')
                    doc.activate()
                    
                    # Verify activation
                    if self.app.activeDocument == doc:
                        return True, doc, f'Switched to {cache_key} model'
                    else:
                        self.logger.warning(f'Document activation may have failed for {doc.name}')
                        return True, doc, f'Switched to {cache_key} model'
                else:
                    # Document no longer valid, remove from cache
                    self.logger.warning(f'Cached {cache_key} document no longer valid')
                    del self._cached_documents[cache_key]
            
            # No cached document or invalid - need to open it
            if not model_path:
                msg = f'No {component_type} model configured in inputs folder'
                if series_id:
                    msg += f' for series {series_id}'
                self.logger.error(msg)
                return False, None, msg
            
            if not os.path.exists(model_path):
                msg = f'{component_type} model file not found: {model_path}'
                self.logger.error(msg)
                return False, None, msg
            
            # Open the model
            self.logger.info(f'Opening {cache_key} model from: {model_path}')
            import_manager = self.app.importManager
            import_options = import_manager.createFusionArchiveImportOptions(model_path)
            doc = import_manager.importToNewDocument(import_options)
            
            if not doc:
                msg = f'Failed to open {cache_key} model (returned None)'
                self.logger.error(msg)
                return False, None, msg
            
            # Cache the document by cache_key
            self._cached_documents[cache_key] = doc
            
            # Verify document is active
            if self.app.activeDocument == doc:
                self.logger.info(f'Successfully opened and activated {cache_key} model: {doc.name}')
            else:
                self.logger.warning(f'Document opened but not active, attempting activation: {doc.name}')
                doc.activate()
            
            return True, doc, f'Opened {cache_key} model: {doc.name}'
            
        except Exception as e:
            msg = f'Exception opening {component_type} model: {str(e)}'
            self.logger.exception(msg)
            return False, None, msg
    
    def _close_duplicate_documents(self) -> int:
        """Close orphaned duplicate model document instances.

        When a Fusion drawing that is kept open across orders (e.g. the door
        drawing) calls updateAllReferences(), Fusion opens a fresh hidden
        instance of the referenced model to regenerate views and leaves the
        previous instance orphaned. Over many orders these duplicates pile up
        (observed: 16 copies of 3X8X_Door), eventually crashing Fusion.

        This method keeps the cached working instance for each lineage and
        closes every other UNMODIFIED, non-active instance sharing that
        lineage id. Only clean reference copies are closed — the edited
        primary (cached) doc is preserved, so this avoids the close() hang
        seen on heavily-versioned edited cloud docs.

        Returns:
            Number of duplicate documents closed.
        """
        closed = 0
        try:
            # Build the list of protected documents (never close these):
            # all cached model docs, all cached drawing docs, and the active doc.
            # Use a list + Fusion '==' comparison rather than a Python set,
            # because SWIG wrapper objects may not hash consistently with
            # equality (two wrappers can reference the same underlying doc).
            protected = []
            for d in list(self._cached_documents.values()) + list(self._cached_drawing_docs.values()):
                try:
                    if d and d.isValid:
                        protected.append(d)
                except Exception:
                    pass
            try:
                active = self.app.activeDocument
                if active:
                    protected.append(active)
            except Exception:
                active = None

            def _is_protected(doc) -> bool:
                for p in protected:
                    try:
                        if doc == p:
                            return True
                    except Exception:
                        continue
                return False

            # Lineage ids we manage (only close duplicates of these).
            managed_lineages = set()
            for d in protected:
                try:
                    if hasattr(d, 'dataFile') and d.dataFile:
                        managed_lineages.add(d.dataFile.id)
                except Exception:
                    pass

            # Snapshot the document list — closing mutates the collection.
            docs_snapshot = [doc for doc in self.app.documents]

            for doc in docs_snapshot:
                try:
                    if not doc.isValid:
                        continue
                    if _is_protected(doc):
                        continue
                    # Only model (FusionDocument) duplicates — leave drawings alone.
                    if not adsk.fusion.FusionDocument.cast(doc):
                        continue
                    if not (hasattr(doc, 'dataFile') and doc.dataFile):
                        continue
                    if doc.dataFile.id not in managed_lineages:
                        continue
                    # Never close a modified doc (would lose work / may hang).
                    if doc.isModified:
                        continue
                    doc_name = doc.name
                    doc.close(False)
                    closed += 1
                    self.logger.info(f'Closed duplicate model instance: {doc_name}')
                except Exception as e:
                    self.logger.warning(f'Failed to close duplicate document: {e}')

            if closed:
                self.logger.info(f'Closed {closed} duplicate model instance(s)')
        except Exception as e:
            self.logger.warning(f'_close_duplicate_documents error: {e}')
        return closed

    def cleanup_cached_documents(self, close_documents: bool = False) -> Tuple[bool, str]:
        """
        Clean up cached documents between orders.
        
        Does NOT close non-door cloud documents here. Closing and immediately
        reopening the same cloud doc every order (e.g., 161 stile close/reopen
        cycles) accumulates Fusion internal document management debt
        (preDocumentClose → removeCollaborator → addCollaborator → reserveLineage)
        that eventually causes a hang/crash.
        
        Instead, non-door cloud docs are closed only when SWITCHING to a
        different model — handled by _close_non_door_cloud_docs(keep_key=...)
        inside open_cloud_panel_model() and open_cloud_stile_model().
        
        This method only:
        1. Removes invalid document references from the cache
        2. Re-activates the door model as the active document
        3. Runs Python garbage collection
        
        Args:
            close_documents: Ignored. Kept for API compatibility.
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            preserved_count = 0
            cleared_count = 0
            
            # Do NOT close non-door cloud docs here.
            # They will be closed only when switching to a different model
            # in open_cloud_stile_model() / open_cloud_panel_model().
            
            # Remove invalid document references from the cache
            cache_keys = list(self._cached_documents.keys())
            
            for cache_key in cache_keys:
                doc = self._cached_documents.get(cache_key)
                if doc and doc.isValid:
                    preserved_count += 1
                else:
                    del self._cached_documents[cache_key]
                    cleared_count += 1
                    self.logger.warning(f'Removed invalid document from cache: {cache_key}')
            
            # Close orphaned duplicate model instances left behind by drawing
            # reference resolution (e.g. accumulating 3X8X_Door copies). Keeps
            # the cached working instance; only closes clean reference copies.
            duplicates_closed = self._close_duplicate_documents()
            
            # Re-activate the door model so Fusion's internal version polling
            # targets the door (which we own) rather than a stile.
            # BUT skip if door is already active — redundant activate() calls on
            # cloud docs accumulate Fusion internal state that causes hangs.
            if "door_cloud" in self._cached_documents:
                door_doc = self._cached_documents["door_cloud"]
                if door_doc and door_doc.isValid:
                    try:
                        if self.app.activeDocument != door_doc:
                            door_doc.activate()
                    except Exception:
                        pass
            
            # Force Python garbage collection
            import gc
            gc.collect()
            
            msg = f'Memory cleanup: preserved {preserved_count} document(s)'
            if cleared_count > 0:
                msg += f', removed {cleared_count} invalid reference(s)'
            if duplicates_closed > 0:
                msg += f', closed {duplicates_closed} duplicate instance(s)'
            
            self.logger.info(msg)
            return True, msg
            
        except Exception as e:
            msg = f'Error during memory cleanup: {str(e)}'
            self.logger.error(msg)
            return False, msg
    
    def get_cache_status(self) -> dict:
        """
        Get information about currently cached documents.
        
        Returns:
            Dictionary with cache statistics
        """
        valid_count = 0
        invalid_count = 0
        
        for cache_key, doc in self._cached_documents.items():
            if doc and doc.isValid:
                valid_count += 1
            else:
                invalid_count += 1
        
        return {
            'total_cached': len(self._cached_documents),
            'valid': valid_count,
            'invalid': invalid_count,
            'cache_keys': list(self._cached_documents.keys())
        }
    
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
