"""
Configuration for Fusion 360 Manufacturing Pipeline
Centralized path management for network folder structure
Supports LOCAL mode (dev machine) and VM mode (production network shares)

Toggling modes
--------------
Mode is chosen by set_run_mode('LOCAL'|'VM'), which is driven by the
"run_mode" field in autostart_config.json (used by both the toolbar button
and the Fusion-startup auto-start). Nothing else needs editing to switch.

LOCAL mode is a fully self-contained sandbox: every output the pipeline
produces in VM mode — including the three flat machine-drop folders that
normally live on separate shares (Gannomat / Anderson / Voorwood) — is
redirected under a single local base folder, so a local run exercises the
same code paths as production without touching any network share.

The LOCAL base resolves in this order (first hit wins):
  1. env var  FUSION_PIPELINE_LOCAL_BASE
  2. "local_base" in local_config.json next to this add-in's root
  3. DEFAULT_LOCAL_BASE below
"""

import json
import os
from pathlib import Path


# ─── Run mode ────────────────────────────────────────────────────────────────
# Set by set_run_mode() at startup based on user selection.
RUN_MODE = 'LOCAL'  # 'LOCAL' or 'VM'

# ─── LOCAL paths (dev machine sandbox) ───────────────────────────────────────
DEFAULT_LOCAL_BASE = r'C:\Users\james.derrod\VM Fusion Extension\local_test_env'

# ─── VM / network paths (production) ────────────────────────────────────────
_VM_BASE = r'\\ddc-mefs\Fusion\Fusion Folders'
_VM_DROPBOX = r'\\ddc-mefs\iBob-Export\S2S_Export'

# Dedicated flat machine-drop locations, VM mode (files are ALSO copied here)
_VM_DRILLING = r'\\ddc-mefs\Gannomat\F360_output'   # {order_id}.json flat
_VM_NC       = r'\\ddc-mefs\Anderson'               # *.nc flat
_VM_CUTLIST  = r'\\ddc-mefs\Voorwood'               # *.csv flat


def _resolve_local_base() -> str:
    """LOCAL sandbox root: env var > local_config.json > DEFAULT_LOCAL_BASE."""
    env = os.environ.get('FUSION_PIPELINE_LOCAL_BASE', '').strip()
    if env:
        return env
    try:
        # This file lives at <addin_root>/src/config.py
        cfg_path = Path(__file__).resolve().parent.parent / 'local_config.json'
        with open(cfg_path, 'r', encoding='utf-8') as f:
            value = json.load(f).get('local_base', '').strip()
        if value:
            return value
    except Exception:
        pass
    return DEFAULT_LOCAL_BASE


def _build_paths(base: str, dropbox_override: str = None,
                 drilling: str = None, nc: str = None, cutlist: str = None):
    """Build all path variables from a base directory.

    drilling/nc/cutlist default to local subfolders of `base` so LOCAL mode
    keeps every artifact inside the sandbox; VM mode passes the real shares.
    """
    b = Path(base)
    dropbox = Path(dropbox_override) if dropbox_override else b / 'order_dropbox'
    drops = b / 'machine_drops'
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
        'OUTPUT_DRILLING_NETWORK': Path(drilling) if drilling else drops / 'gannomat',
        'OUTPUT_NC_NETWORK':       Path(nc)       if nc       else drops / 'anderson',
        'OUTPUT_CUTLIST_NETWORK':  Path(cutlist)  if cutlist  else drops / 'voorwood',
    }


def _apply(p: dict):
    """Rebind every module-level path global from a built path dict."""
    global NETWORK_BASE
    global INPUT_BASE, INPUT_DOOR, INPUT_PANEL, INPUT_STILE
    global ORDER_DROPBOX, ORDER_PROCESSING, ORDER_COMPLETED, ORDER_FAILED
    global OUTPUT_BASE, OUTPUT_MODELS, OUTPUT_GCODE, OUTPUT_PARAMETERS, OUTPUT_LOGS
    global OUTPUT_DRILLING_NETWORK, OUTPUT_NC_NETWORK, OUTPUT_CUTLIST_NETWORK

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
    OUTPUT_DRILLING_NETWORK = p['OUTPUT_DRILLING_NETWORK']
    OUTPUT_NC_NETWORK       = p['OUTPUT_NC_NETWORK']
    OUTPUT_CUTLIST_NETWORK  = p['OUTPUT_CUTLIST_NETWORK']


# Initialise with LOCAL defaults
_apply(_build_paths(_resolve_local_base()))


def set_run_mode(mode: str):
    """
    Switch all paths between LOCAL and VM mode.
    Must be called before any folder creation or processing.
    """
    global RUN_MODE

    mode = mode.upper()
    if mode not in ('LOCAL', 'VM'):
        raise ValueError(f"Invalid run mode: {mode!r}. Must be 'LOCAL' or 'VM'.")

    RUN_MODE = mode

    if mode == 'VM':
        p = _build_paths(_VM_BASE, dropbox_override=_VM_DROPBOX,
                         drilling=_VM_DRILLING, nc=_VM_NC, cutlist=_VM_CUTLIST)
    else:
        p = _build_paths(_resolve_local_base())

    _apply(p)


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
        OUTPUT_LOGS,
        # Flat machine-drop folders (local sandbox dirs in LOCAL mode,
        # the Gannomat/Anderson/Voorwood shares in VM mode)
        OUTPUT_DRILLING_NETWORK,
        OUTPUT_NC_NETWORK,
        OUTPUT_CUTLIST_NETWORK,
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
    info += f"  Dashboard:  {Path(OUTPUT_BASE) / 'dashboard'}\n\n"

    label = "DEDICATED NETWORK OUTPUT (VM)" if RUN_MODE == 'VM' \
        else "MACHINE DROP FOLDERS (local sandbox)"
    info += f"{label}:\n"
    info += f"  Drilling:   {OUTPUT_DRILLING_NETWORK}\n"
    info += f"  NC files:   {OUTPUT_NC_NETWORK}\n"
    info += f"  Cutlist:    {OUTPUT_CUTLIST_NETWORK}\n"

    return info
