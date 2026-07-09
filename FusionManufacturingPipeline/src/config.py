"""
Configuration for Fusion 360 Manufacturing Pipeline
Centralized path management for network folder structure
Supports LOCAL mode (dev machine) and VM mode (production network shares)
"""

from pathlib import Path


# ─── Run mode ────────────────────────────────────────────────────────────────
# Set by set_run_mode() at startup based on user selection.
RUN_MODE = 'LOCAL'  # 'LOCAL' or 'VM'

# ─── LOCAL paths (dev machine) ───────────────────────────────────────────────
_LOCAL_BASE = r'C:\Users\james.derrod\VM Fusion Extension\S2S File Test'

# ─── VM / network paths (production) ────────────────────────────────────────
_VM_BASE = r'\\ddc-mefs\Fusion\Fusion Folders'

# Dedicated network output locations (VM only — files are ALSO copied here)
OUTPUT_DRILLING_NETWORK = Path(r'\\ddc-mefs\Gannomat\F360_output')   # {order_id}.json flat
OUTPUT_NC_NETWORK       = Path(r'\\ddc-mefs\Anderson')               # *.nc flat
OUTPUT_CUTLIST_NETWORK  = Path(r'\\ddc-mefs\Voorwood')               # *.csv flat


def _build_paths(base: str, dropbox_override: str = None):
    """Build all path variables from a base directory."""
    b = Path(base)
    dropbox = Path(dropbox_override) if dropbox_override else b / 'order_dropbox'
    return {
        'NETWORK_BASE':     base,
        'INPUT_BASE':       b / 'input',
        'INPUT_DOOR':       b / 'input' / 'door',
        'INPUT_PANEL':      b / 'input' / 'panel',
        'INPUT_STILE':      b / 'input' / 'stile',
        'ORDER_DROPBOX':    dropbox,
        'ORDER_PROCESSING': b / 'order_processing',
        'ORDER_COMPLETED':  b / 'order_completed',
        'ORDER_FAILED':     b / 'order_failed',
        'OUTPUT_BASE':      b / 'output',
        'OUTPUT_MODELS':    b / 'output' / 'models',
        'OUTPUT_GCODE':     b / 'output' / 'gcode',
        'OUTPUT_PARAMETERS':b / 'output' / 'parameters',
        'OUTPUT_LOGS':      b / 'output' / 'logs',
    }


# Initialise with LOCAL defaults
_paths = _build_paths(_LOCAL_BASE)

NETWORK_BASE     = _paths['NETWORK_BASE']
INPUT_BASE       = _paths['INPUT_BASE']
INPUT_DOOR       = _paths['INPUT_DOOR']
INPUT_PANEL      = _paths['INPUT_PANEL']
INPUT_STILE      = _paths['INPUT_STILE']
ORDER_DROPBOX    = _paths['ORDER_DROPBOX']
ORDER_PROCESSING = _paths['ORDER_PROCESSING']
ORDER_COMPLETED  = _paths['ORDER_COMPLETED']
ORDER_FAILED     = _paths['ORDER_FAILED']
OUTPUT_BASE      = _paths['OUTPUT_BASE']
OUTPUT_MODELS    = _paths['OUTPUT_MODELS']
OUTPUT_GCODE     = _paths['OUTPUT_GCODE']
OUTPUT_PARAMETERS= _paths['OUTPUT_PARAMETERS']
OUTPUT_LOGS      = _paths['OUTPUT_LOGS']


def set_run_mode(mode: str):
    """
    Switch all paths between LOCAL and VM mode.
    Must be called before any folder creation or processing.
    """
    global RUN_MODE, NETWORK_BASE
    global INPUT_BASE, INPUT_DOOR, INPUT_PANEL, INPUT_STILE
    global ORDER_DROPBOX, ORDER_PROCESSING, ORDER_COMPLETED, ORDER_FAILED
    global OUTPUT_BASE, OUTPUT_MODELS, OUTPUT_GCODE, OUTPUT_PARAMETERS, OUTPUT_LOGS

    mode = mode.upper()
    if mode not in ('LOCAL', 'VM'):
        raise ValueError(f"Invalid run mode: {mode!r}. Must be 'LOCAL' or 'VM'.")

    RUN_MODE = mode

    if mode == 'VM':
        p = _build_paths(_VM_BASE, dropbox_override=r'\\ddc-mefs\iBob-Export\S2S_Export')
    else:
        p = _build_paths(_LOCAL_BASE)

    NETWORK_BASE     = p['NETWORK_BASE']
    INPUT_BASE       = p['INPUT_BASE']
    INPUT_DOOR       = p['INPUT_DOOR']
    INPUT_PANEL      = p['INPUT_PANEL']
    INPUT_STILE      = p['INPUT_STILE']
    ORDER_DROPBOX    = p['ORDER_DROPBOX']
    ORDER_PROCESSING = p['ORDER_PROCESSING']
    ORDER_COMPLETED  = p['ORDER_COMPLETED']
    ORDER_FAILED     = p['ORDER_FAILED']
    OUTPUT_BASE      = p['OUTPUT_BASE']
    OUTPUT_MODELS    = p['OUTPUT_MODELS']
    OUTPUT_GCODE     = p['OUTPUT_GCODE']
    OUTPUT_PARAMETERS= p['OUTPUT_PARAMETERS']
    OUTPUT_LOGS      = p['OUTPUT_LOGS']


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
    
    # In VM mode, also create the dedicated network output folders
    if RUN_MODE == 'VM':
        folders.extend([
            OUTPUT_DRILLING_NETWORK,
            OUTPUT_NC_NETWORK,
            OUTPUT_CUTLIST_NETWORK,
        ])
    
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
    info += f"RUN MODE: {RUN_MODE}\n\n"
    
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
    
    if RUN_MODE == 'VM':
        info += "\nDEDICATED NETWORK OUTPUT (VM only):\n"
        info += f"  Drilling:   {OUTPUT_DRILLING_NETWORK}\n"
        info += f"  NC files:   {OUTPUT_NC_NETWORK}\n"
        info += f"  Cutlist:    {OUTPUT_CUTLIST_NETWORK}\n"
    
    return info
