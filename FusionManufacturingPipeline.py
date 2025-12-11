"""
Fusion 360 Manufacturing Pipeline Add-in
Entry point file - must match the manifest name exactly.
"""

import adsk.core
import adsk.fusion
import traceback
import sys
import os

# Add src directory to path
_src_path = os.path.join(os.path.dirname(__file__), 'src')
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

# Global references
_app = None
_ui = None
_handlers = []

def run(context):
    """Called when add-in is started"""
    global _app, _ui
    
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        
        # Import after setting up path
        import app
        from config import ensure_folder_structure, ORDER_DROPBOX, OUTPUT_BASE
        
        # Initialize network folder structure
        try:
            ensure_folder_structure()
        except Exception as e:
            _ui.messageBox(
                f'Warning: Could not create network folders.\n\n'
                f'Error: {str(e)}\n\n'
                f'Please ensure M:\\S2S File Test\\ is accessible.',
                'Folder Setup Warning'
            )
        
        # Register the command
        app.register_command(_ui, _handlers)
        
        # Show startup message
        _ui.messageBox(
            'Specs to Machine loaded successfully!\n\n'
            'Button Location:\n'
            '  → Design workspace\n'
            '  → SOLID toolbar panel\n'
            '  → Look for "Specs to Machine" button with Bobrick logo\n\n'
            f'Network Folders:\n'
            f'  Orders: {ORDER_DROPBOX}\n'
            f'  Output: {OUTPUT_BASE}\n\n'
            'System will auto-process orders from iBob!',
            'Specs to Machine - Ready'
        )
        
    except:
        if _ui:
            _ui.messageBox('Failed to initialize add-in:\n{}'.format(traceback.format_exc()))

def stop(context):
    """Called when add-in is stopped"""
    global _ui, _handlers, _app
    
    try:
        # Stop folder monitor if running
        try:
            from folder_monitor import get_monitor
            monitor = get_monitor(_app)
            if monitor.is_running:
                monitor.stop()
        except:
            pass
        
        if _ui:
            # Import after setting up path
            import app
            
            # Unregister the command
            app.unregister_command(_ui)
            
            _ui.messageBox(
                'Fusion Manufacturing Pipeline unloaded.',
                'Manufacturing Pipeline'
            )
            
        # Clean up handlers
        _handlers.clear()
        
    except:
        if _ui:
            _ui.messageBox('Failed to clean up add-in:\n{}'.format(traceback.format_exc()))
