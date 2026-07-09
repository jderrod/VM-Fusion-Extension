"""
Fusion 360 Palette handler for the Drawing Configuration UI.
Bridges the HTML palette with the Python backend to query Fusion Hub
and save/load drawing-to-model mappings.
"""

import adsk.core
import adsk.fusion
import json
import os
import traceback

from logger import get_logger
import cloud_config


# Palette identifiers
PALETTE_ID = 'DrawingConfigPalette'
PALETTE_NAME = 'Drawing Configuration'
PALETTE_URL = ''  # Set at runtime to the HTML file path
PALETTE_WIDTH = 520
PALETTE_HEIGHT = 720

# Command identifiers
CONFIG_COMMAND_ID = 'ManufacturingPipelineDrawingConfig'
CONFIG_COMMAND_NAME = 'Drawing Config'
CONFIG_COMMAND_DESCRIPTION = 'Configure which cloud drawings are used for each model'


class ConfigPaletteShowHandler(adsk.core.CommandCreatedEventHandler):
    """Handler for when the Drawing Config command is created — shows the palette."""
    
    def __init__(self):
        super().__init__()
    
    def notify(self, args: adsk.core.CommandCreatedEventArgs):
        try:
            app = adsk.core.Application.get()
            ui = app.userInterface
            logger = get_logger()
            
            # Get or create the palette
            palette = ui.palettes.itemById(PALETTE_ID)
            
            if not palette:
                # Build URL to the HTML file
                html_path = os.path.join(os.path.dirname(__file__), 'drawing_config.html')
                html_url = 'file:///' + html_path.replace('\\', '/')
                
                logger.info(f'Creating drawing config palette: {html_url}')
                
                palette = ui.palettes.add(
                    PALETTE_ID,
                    PALETTE_NAME,
                    html_url,
                    True,   # isVisible
                    True,   # showCloseButton
                    True,   # isResizable
                    PALETTE_WIDTH,
                    PALETTE_HEIGHT,
                    True    # useNewWebBrowser
                )
                
                # Connect event handlers
                on_html_event = PaletteHTMLEventHandler()
                palette.incomingFromHTML.add(on_html_event)
                _handlers.append(on_html_event)
                
                on_close = PaletteCloseHandler()
                palette.closed.add(on_close)
                _handlers.append(on_close)
            else:
                palette.isVisible = True
                
        except Exception:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(
                f'Failed to show config palette:\n{traceback.format_exc()}',
                'Error'
            )


class PaletteHTMLEventHandler(adsk.core.HTMLEventHandler):
    """Handles messages from the HTML palette UI."""
    
    def __init__(self):
        super().__init__()
    
    def notify(self, args: adsk.core.HTMLEventArgs):
        try:
            app = adsk.core.Application.get()
            logger = get_logger()
            
            # HTML sends via adsk.fusionSendData('configAction', jsonPayload)
            # args.action = 'configAction', args.data = JSON string
            msg = json.loads(args.data)
            action = msg.get('action', '')
            data = msg.get('data', {})
            
            # Always return something to avoid error
            args.returnData = 'OK'
            
            if action == 'init':
                # Send current config to the UI
                config = cloud_config.load_config()
                self._send(args, {'action': 'init', 'config': config})
                
            elif action == 'get_projects':
                projects = cloud_config.list_hub_projects(app)
                self._send(args, {'action': 'projects', 'data': projects})
                
            elif action == 'get_folders':
                project = data.get('project', '')
                folders = cloud_config.list_hub_folders(app, project)
                self._send(args, {'action': 'folders', 'data': folders})
                
            elif action == 'get_documents':
                project = data.get('project', '')
                folder = data.get('folder', '')
                docs = cloud_config.list_hub_documents(app, project, folder)
                self._send(args, {'action': 'documents', 'data': docs})
                
            elif action == 'save':
                success, message = cloud_config.save_config(data)
                if success:
                    logger.info(f'Drawing config saved: {message}')
                    self._send(args, {'action': 'saved', 'message': message})
                else:
                    logger.warning(f'Drawing config save failed: {message}')
                    self._send(args, {'action': 'error', 'message': message})
                    
            elif action == 'reset_defaults':
                defaults = cloud_config.get_defaults()
                self._send(args, {'action': 'init', 'config': defaults})
                
            elif action == 'cancel':
                palette = app.userInterface.palettes.itemById(PALETTE_ID)
                if palette:
                    palette.isVisible = False
                    
        except Exception as e:
            get_logger().error(f'Palette handler error: {traceback.format_exc()}')
            try:
                self._send(args, {'action': 'error', 'message': str(e)})
            except Exception:
                pass
    
    def _send(self, args: adsk.core.HTMLEventArgs, data: dict):
        """Send a message back to the HTML palette."""
        palette = adsk.core.Application.get().userInterface.palettes.itemById(PALETTE_ID)
        if palette:
            # HTML handler listens for action='configData'
            palette.sendInfoToHTML('configData', json.dumps(data))


class PaletteCloseHandler(adsk.core.UserInterfaceGeneralEventHandler):
    """Handles palette close event."""
    
    def __init__(self):
        super().__init__()
    
    def notify(self, args):
        pass  # Nothing to clean up


# Global handler list to prevent garbage collection
_handlers = []


def register_config_command(ui: adsk.core.UserInterface, handlers: list):
    """
    Register the Drawing Config command in Fusion UI.
    
    Args:
        ui: Fusion UserInterface object
        handlers: List to store command handlers (prevents garbage collection)
    """
    try:
        # Clean up existing
        cmd_def = ui.commandDefinitions.itemById(CONFIG_COMMAND_ID)
        if cmd_def:
            cmd_def.deleteMe()
        
        # Get icon folder
        from pathlib import Path
        icon_folder = Path(__file__).parent.parent / 'UI Elements'
        
        # Create command definition
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            CONFIG_COMMAND_ID,
            CONFIG_COMMAND_NAME,
            CONFIG_COMMAND_DESCRIPTION,
            str(icon_folder)
        )
        
        # Connect handler
        handler = ConfigPaletteShowHandler()
        cmd_def.commandCreated.add(handler)
        handlers.append(handler)
        
        # Add to the same panel as Run Order
        workspace = ui.workspaces.itemById('FusionSolidEnvironment')
        if workspace:
            solid_panel = workspace.toolbarPanels.itemById('SolidCreatePanel')
            if solid_panel:
                existing = solid_panel.controls.itemById(CONFIG_COMMAND_ID)
                if existing:
                    existing.deleteMe()
                control = solid_panel.controls.addCommand(cmd_def, '', False)
                if control:
                    control.isPromoted = True
                    control.isPromotedByDefault = True
                    control.isVisible = True
                    
    except Exception:
        ui.messageBox(f'Failed to register config command:\n{traceback.format_exc()}')


def unregister_config_command(ui: adsk.core.UserInterface):
    """Unregister the Drawing Config command from Fusion UI."""
    try:
        workspace = ui.workspaces.itemById('FusionSolidEnvironment')
        if workspace:
            solid_panel = workspace.toolbarPanels.itemById('SolidCreatePanel')
            if solid_panel:
                control = solid_panel.controls.itemById(CONFIG_COMMAND_ID)
                if control:
                    control.deleteMe()
        
        cmd_def = ui.commandDefinitions.itemById(CONFIG_COMMAND_ID)
        if cmd_def:
            cmd_def.deleteMe()
            
        # Also remove the palette
        palette = ui.palettes.itemById(PALETTE_ID)
        if palette:
            palette.deleteMe()
            
    except Exception:
        pass
