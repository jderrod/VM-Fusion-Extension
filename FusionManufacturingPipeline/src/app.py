"""
Main application logic for Fusion Manufacturing Pipeline.
Handles command registration and coordination.
"""

import adsk.core
import adsk.fusion
import traceback
import os
from pathlib import Path

from command_handler import RunOrderCommandHandler
from config_palette import register_config_command, unregister_config_command

# Command identifiers
COMMAND_ID = 'ManufacturingPipelineRunOrder'
COMMAND_NAME = 'Specs to Machine'
COMMAND_DESCRIPTION = 'Bobrick Specs to Machine - Automated order processing'
COMMAND_TOOLTIP = 'Start the automated manufacturing pipeline'

# UI location
WORKSPACE_ID = 'FusionSolidEnvironment'


def register_command(ui: adsk.core.UserInterface, handlers: list):
    """
    Register the Run Order command in Fusion UI.
    
    Args:
        ui: Fusion UserInterface object
        handlers: List to store command handlers (prevents garbage collection)
    """
    try:
        # Get the target workspace
        workspace = ui.workspaces.itemById(WORKSPACE_ID)
        if not workspace:
            ui.messageBox(f'Workspace not found: {WORKSPACE_ID}')
            return
        
        # Check if command already exists (cleanup from previous run)
        cmd_def = ui.commandDefinitions.itemById(COMMAND_ID)
        if cmd_def:
            cmd_def.deleteMe()
        
        # Get path to custom Bobrick logo icon
        icon_folder = Path(__file__).parent.parent / 'UI Elements'
        icon_path = str(icon_folder / 'bobrick_logo.png')
        
        # Verify icon exists
        if not os.path.exists(icon_path):
            ui.messageBox(f'Warning: Icon not found at {icon_path}')
        
        # Create command definition with custom icon
        # For Fusion 360, provide the folder path (not the file) for resource icons
        # Or provide the full file path for a single icon
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            COMMAND_ID,
            COMMAND_NAME,
            COMMAND_DESCRIPTION,
            str(icon_folder)  # Provide folder path for Fusion to find resources
        )
        
        # Tooltip is already set in the description parameter above
        # toolClipFilename is for an image file, not text
        
        # Create and connect command handler
        handler = RunOrderCommandHandler()
        cmd_def.commandCreated.add(handler)
        handlers.append(handler)
        
        # Register the Drawing Config command (palette UI)
        register_config_command(ui, handlers)
        
        # Get the SOLID panel in the Design workspace
        solid_panel = workspace.toolbarPanels.itemById('SolidCreatePanel')
        if not solid_panel:
            ui.messageBox('Could not find SOLID panel')
            return
        
        # Check if button already exists in panel
        existing_control = solid_panel.controls.itemById(COMMAND_ID)
        if existing_control:
            existing_control.deleteMe()
        
        # Add button to SOLID panel - add at the end with promotion
        control = solid_panel.controls.addCommand(cmd_def, '', False)
        if control:
            # Promote so it's always visible on toolbar, not in dropdown
            control.isPromoted = True
            control.isPromotedByDefault = True
            control.isVisible = True
        
    except Exception:
        ui.messageBox(f'Failed to register command:\n{traceback.format_exc()}')


def unregister_command(ui: adsk.core.UserInterface):
    """
    Unregister the Run Order command from Fusion UI.
    
    Args:
        ui: Fusion UserInterface object
    """
    try:
        # Get the target workspace
        workspace = ui.workspaces.itemById(WORKSPACE_ID)
        if workspace:
            # Remove control from SOLID panel
            solid_panel = workspace.toolbarPanels.itemById('SolidCreatePanel')
            if solid_panel:
                control = solid_panel.controls.itemById(COMMAND_ID)
                if control:
                    control.deleteMe()
        
        # Remove command definition
        cmd_def = ui.commandDefinitions.itemById(COMMAND_ID)
        if cmd_def:
            cmd_def.deleteMe()
        
        # Unregister the Drawing Config command
        unregister_config_command(ui)
            
    except Exception:
        ui.messageBox(f'Failed to unregister command:\n{traceback.format_exc()}')


def get_repo_root() -> Path:
    """
    Get the repository root directory.
    
    Returns:
        Path object pointing to repo root
    """
    # Go up from src/ to repo root
    return Path(__file__).parent.parent


def get_schema_path() -> Path:
    """
    Get path to schema.json.
    
    Returns:
        Path object pointing to schema.json
    """
    return get_repo_root() / 'schema.json'


def get_log_directory() -> Path:
    """
    Get or create log directory.
    
    Returns:
        Path object pointing to logs directory
    """
    log_dir = get_repo_root() / 'logs'
    log_dir.mkdir(exist_ok=True)
    return log_dir
