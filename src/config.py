"""
Configuration for Fusion 360 Manufacturing Pipeline
Centralized path management for network folder structure
"""

from pathlib import Path


# Network base folder
NETWORK_BASE = r'M:\S2S File Test'

# Input folders
INPUT_BASE = Path(NETWORK_BASE) / 'input'
INPUT_DOOR = INPUT_BASE / 'door'
INPUT_PANEL = INPUT_BASE / 'panel'
INPUT_STILE = INPUT_BASE / 'stile'

# Order processing folders
ORDER_DROPBOX = Path(NETWORK_BASE) / 'order_dropbox'
ORDER_PROCESSING = Path(NETWORK_BASE) / 'order_processing'
ORDER_COMPLETED = Path(NETWORK_BASE) / 'order_completed'
ORDER_FAILED = Path(NETWORK_BASE) / 'order_failed'

# Output folders
OUTPUT_BASE = Path(NETWORK_BASE) / 'output'
OUTPUT_MODELS = OUTPUT_BASE / 'models'
OUTPUT_GCODE = OUTPUT_BASE / 'gcode'
OUTPUT_PARAMETERS = OUTPUT_BASE / 'parameters'
OUTPUT_LOGS = OUTPUT_BASE / 'logs'


def ensure_folder_structure():
    """
    Create all required folders if they don't exist.
    Call this on startup to initialize the folder structure.
    """
    folders = [
        # Input folders
        INPUT_DOOR,
        INPUT_PANEL,
        INPUT_STILE,
        # Order processing folders
        ORDER_DROPBOX,
        ORDER_PROCESSING,
        ORDER_COMPLETED,
        ORDER_FAILED,
        # Output folders
        OUTPUT_MODELS,
        OUTPUT_GCODE,
        OUTPUT_PARAMETERS,
        OUTPUT_LOGS
    ]
    
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)
    
    return True


def get_paths_info() -> str:
    """
    Get formatted information about all configured paths.
    
    Returns:
        Formatted string with path information
    """
    info = "=== Fusion 360 Manufacturing Pipeline - Folder Configuration ===\n\n"
    
    info += "INPUT FOLDERS:\n"
    info += f"  Base:  {INPUT_BASE}\n"
    info += f"  Door:  {INPUT_DOOR}\n"
    info += f"  Panel: {INPUT_PANEL}\n"
    info += f"  Stile: {INPUT_STILE}\n\n"
    
    info += "ORDER PROCESSING FOLDERS:\n"
    info += f"  Dropbox:    {ORDER_DROPBOX}\n"
    info += f"  Processing: {ORDER_PROCESSING}\n"
    info += f"  Completed:  {ORDER_COMPLETED}\n"
    info += f"  Failed:     {ORDER_FAILED}\n\n"
    
    info += "OUTPUT FOLDERS:\n"
    info += f"  Base:       {OUTPUT_BASE}\n"
    info += f"  Models:     {OUTPUT_MODELS}\n"
    info += f"  G-Code:     {OUTPUT_GCODE}\n"
    info += f"  Parameters: {OUTPUT_PARAMETERS}\n"
    info += f"  Logs:       {OUTPUT_LOGS}\n"
    
    return info
