"""
Cloud model/drawing configuration manager.
Handles loading, saving, and querying the drawing-to-model mapping config.
"""

import json
import os
import adsk.core
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from logger import get_logger


# Default config file location (next to src/)
_CONFIG_FILENAME = 'drawing_config.json'


def _config_path() -> Path:
    """Get the path to the drawing config JSON file."""
    return Path(__file__).parent.parent / _CONFIG_FILENAME


def load_config() -> dict:
    """
    Load drawing configuration from JSON file.
    
    Returns:
        Config dict with keys:
            project_name, folder_name,
            door_model, door_drawing,
            panel_model, panel_drawing,
            stile_models: {series_code: model_name},
            stile_drawings: {series_code: drawing_name}
    """
    path = _config_path()
    if path.exists():
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception as e:
            get_logger().warning(f'Failed to load drawing config: {e}')
    
    # Return defaults matching current hardcoded values
    return get_defaults()


def get_defaults() -> dict:
    """Get the default configuration (matches current hardcoded values)."""
    return {
        'project_name': 'Bobrick - Component modeling',
        'folder_name': '3X8X Components',
        'door_model': '3X8X_Door_branch_B',
        'door_drawing': '3X8X_Door_branch_B Drawing',
        'panel_model': '3X8X_Panel_branch_B',
        'panel_drawing': '3X8X_Panel_branch_B Drawing',
        'stile_models': {
            '3081': '3X81_Stile',
            '3082': '3X82_Stile',
            '3086': '3X86_Stile'
        },
        'stile_drawings': {
            '3082': '3X82_Stile Drawing',
            '3086': '3X86_Stile Drawing'
        }
    }


def save_config(config: dict) -> Tuple[bool, str]:
    """
    Save drawing configuration to JSON file.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Tuple of (success, message)
    """
    try:
        path = _config_path()
        with open(path, 'w') as f:
            json.dump(config, f, indent=2)
        return True, f'Config saved to {path}'
    except Exception as e:
        return False, f'Failed to save config: {e}'


def get_setup_cloud_models_args(config: dict = None) -> dict:
    """
    Convert saved config into kwargs for ModelManager.setup_cloud_models().
    
    Args:
        config: Config dict (loads from file if None)
        
    Returns:
        Dict of keyword arguments for setup_cloud_models()
    """
    if config is None:
        config = load_config()
    
    return {
        'project_name': config.get('project_name', 'Bobrick - Component modeling'),
        'folder_name': config.get('folder_name', '3X8X Components'),
        'door_name': config.get('door_model', '3X8X_Door'),
        'door_drawing_name': config.get('door_drawing', '3X8X_Door Drawing'),
        'panel_name': config.get('panel_model', '3X8X_Panel'),
        'panel_drawing_name': config.get('panel_drawing'),
        'stile_names': config.get('stile_models', {
            '3081': '3X81_Stile',
            '3082': '3X82_Stile',
            '3086': '3X86_Stile'
        }),
        'stile_drawing_names': config.get('stile_drawings', {
            '3082': '3X82_Stile Drawing',
            '3086': '3X86_Stile Drawing'
        })
    }


def list_hub_projects(app: adsk.core.Application) -> List[str]:
    """List all team project names from Fusion Hub."""
    try:
        return [p.name for p in app.data.dataProjects.asArray()]
    except Exception:
        return []


def list_hub_folders(app: adsk.core.Application, project_name: str) -> List[str]:
    """List folder names in a Fusion Hub project (root + one level deep)."""
    try:
        folders = []
        for proj in app.data.dataProjects.asArray():
            if proj.name != project_name:
                continue
            # Root-level folders
            for folder in proj.rootFolder.dataFolders.asArray():
                folders.append(folder.name)
        return sorted(folders)
    except Exception:
        return []


def list_hub_documents(app: adsk.core.Application, project_name: str,
                       folder_name: str) -> List[dict]:
    """
    List all documents in a Fusion Hub project/folder.
    
    Returns:
        List of dicts with 'name' and 'type' ('model' or 'drawing')
    """
    try:
        docs = []
        for proj in app.data.dataProjects.asArray():
            if proj.name != project_name:
                continue
            
            # Search root folder
            _collect_files(proj.rootFolder, docs, folder_name is None)
            
            # Search subfolders
            for folder in proj.rootFolder.dataFolders.asArray():
                if folder_name and folder.name != folder_name:
                    continue
                _collect_files(folder, docs, True)
                
                # One level of nested folders
                for subfolder in folder.dataFolders.asArray():
                    _collect_files(subfolder, docs, True)
        
        return sorted(docs, key=lambda d: d['name'])
    except Exception as e:
        get_logger().warning(f'Error listing hub documents: {e}')
        return []


def _collect_files(folder: adsk.core.DataFolder, docs: list, include: bool):
    """Collect files from a DataFolder into the docs list."""
    if not include:
        return
    try:
        for file in folder.dataFiles.asArray():
            # Determine type from file extension / fileExtension
            name = file.name
            doc_type = 'drawing' if 'Drawing' in name or name.endswith('.f2d') else 'model'
            docs.append({
                'name': name,
                'type': doc_type,
                'id': file.id if hasattr(file, 'id') else ''
            })
    except Exception:
        pass
