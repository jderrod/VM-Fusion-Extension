"""
Command handler for Run Order command.
Handles user interaction, file selection, and order validation.
"""

import adsk.core
import adsk.fusion
import traceback
import os
from pathlib import Path

import json

from validator import OrderValidator
from logger import get_logger, log_order_start, log_order_complete
from progress_dialog import ProgressDialog
import app


def _load_start_defaults() -> dict:
    """Read autostart_config.json (add-in root) for the button's start settings.

    Falls back to production defaults (VM, CAM on, drawings on) if the file is
    missing or unreadable — the same "all YES" answers the old prompts implied.
    """
    defaults = {'run_mode': 'VM', 'skip_cam': False, 'skip_drawing': False}
    try:
        path = app.get_repo_root() / 'autostart_config.json'
        with open(path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        for k in defaults:
            if k in cfg:
                defaults[k] = cfg[k]
    except Exception:
        pass
    return defaults


class RunOrderCommandHandler(adsk.core.CommandCreatedEventHandler):
    """Handler for when the Run Order command is created"""
    
    def __init__(self):
        super().__init__()
    
    def notify(self, args: adsk.core.CommandCreatedEventArgs):
        """
        Called when command is created.
        Shows dialog to choose between single order or folder monitoring.
        """
        try:
            app_obj = adsk.core.Application.get()
            ui = app_obj.userInterface
            
            # Initialize logger for this run
            logger = get_logger()
            logger.info("=" * 80)
            logger.info("RUN ORDER COMMAND STARTED")
            logger.info(f"Log file: {logger.get_log_path()}")
            logger.info("=" * 80)
            
            # Check if monitor is running
            from folder_monitor import get_monitor
            monitor = get_monitor(app_obj)
            
            if monitor.is_running:
                # Monitor is running - offer to stop it
                result = ui.messageBox(
                    'Folder Monitor is currently running.\n\n'
                    'Click OK to stop monitoring, or Cancel to keep it running.',
                    'Stop Monitor?',
                    adsk.core.MessageBoxButtonTypes.OKCancelButtonType,
                    adsk.core.MessageBoxIconTypes.QuestionIconType
                )
                
                if result == adsk.core.DialogResults.DialogOK:
                    monitor.stop(show_message=True)
                return
            
            # No prompts. Clicking the button starts the folder monitor with
            # the standard production answers (formerly the "all YES" path):
            # monitor mode, VM + CAM + drawings enabled. Values come from
            # autostart_config.json so one file controls both the button and
            # the Fusion-startup auto-start.
            from config import set_run_mode
            cfg = _load_start_defaults()
            run_mode = cfg.get('run_mode', 'VM')
            skip_cam = bool(cfg.get('skip_cam', False))
            skip_drawing = bool(cfg.get('skip_drawing', False))
            set_run_mode(run_mode)
            logger.info(
                f"Button start (no prompts): mode={run_mode}, "
                f"CAM={'OFF' if skip_cam else 'ON'}, "
                f"Drawing={'OFF' if skip_drawing else 'ON'}"
            )
            # auto_resume=True suppresses the "Monitor Active" info box so the
            # button is truly dialog-free.
            monitor.start(skip_cam=skip_cam, skip_drawing=skip_drawing, auto_resume=True)

        except Exception as e:
            # Hide progress dialog if it exists
            try:
                if 'progress' in locals():
                    progress.hide()
            except Exception:
                pass
            
            app_obj = adsk.core.Application.get()
            ui = app_obj.userInterface
            logger = get_logger()
            logger.exception("COMMAND EXECUTION FAILED")
            logger.error(f"Exception: {str(e)}")
            logger.info(f"Log file: {logger.get_log_path()}")
            ui.messageBox(f'Failed to execute command:\n{str(e)}\n\nLog: {logger.get_log_path()}\n\n{traceback.format_exc()}', 'Error')


# Phase 1: No additional handlers needed - command executes immediately
