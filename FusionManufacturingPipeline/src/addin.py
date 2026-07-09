"""
Fusion 360 Manufacturing Pipeline Add-in
Entry point for the Fusion 360 add-in with run/stop lifecycle management.

This add-in processes JSON manufacturing orders to:
1. Apply parameter values to Fusion models
2. Regenerate CAM toolpaths
3. Generate G-code via post processing
"""

import adsk.core
import adsk.fusion
import traceback
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src import app

# Global references to maintain command handlers
_app = None
_ui = None
_handlers = []


def run(context):
    """
    Called when add-in is started.
    
    Args:
        context: Dictionary with keys like 'id', 'version', etc.
    """
    global _app, _ui
    
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        
        # Register the command
        app.register_command(_ui, _handlers)
        
        _ui.messageBox(
            'Fusion Manufacturing Pipeline loaded successfully.\n\n'
            'Look for "Run Order" in the TOOLS tab > ADD-INS panel.',
            'Manufacturing Pipeline'
        )
        
    except Exception:
        if _ui:
            _ui.messageBox('Failed to initialize add-in:\n{}'.format(traceback.format_exc()))


def stop(context):
    """
    Called when add-in is stopped.
    
    Args:
        context: Dictionary with keys like 'id', 'version', etc.
    """
    global _ui, _handlers
    
    try:
        if _ui:
            # Unregister the command
            app.unregister_command(_ui)
            
            _ui.messageBox(
                'Fusion Manufacturing Pipeline unloaded.',
                'Manufacturing Pipeline'
            )
            
        # Clean up handlers
        _handlers.clear()
        
    except Exception:
        if _ui:
            _ui.messageBox('Failed to clean up add-in:\n{}'.format(traceback.format_exc()))
