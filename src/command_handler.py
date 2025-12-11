"""
Command handler for Run Order command.
Handles user interaction, file selection, and order validation.
"""

import adsk.core
import adsk.fusion
import traceback
import os
from pathlib import Path

from validator import OrderValidator
from logger import get_logger, log_order_start, log_order_complete
from progress_dialog import ProgressDialog
import app


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
                    monitor.stop()
                return
            
            # Ask user what they want to do
            from config import ORDER_DROPBOX
            result = ui.messageBox(
                'Choose an option:\n\n'
                'YES = Start Folder Monitor (continuous processing)\n'
                f'       Watch {ORDER_DROPBOX}\\ and process files automatically\n\n'
                'NO = Process Single Order\n'
                '       Process samples/JSON_9013830.json once\n\n'
                'CANCEL = Exit',
                'Specs to Machine - Choose Mode',
                adsk.core.MessageBoxButtonTypes.YesNoCancelButtonType,
                adsk.core.MessageBoxIconTypes.QuestionIconType
            )
            
            if result == adsk.core.DialogResults.DialogYes:
                # Start folder monitoring
                logger.info("Starting folder monitor mode")
                monitor.start()
                return
            elif result == adsk.core.DialogResults.DialogCancel:
                # User cancelled
                return
            
            # Continue with single order processing (NO was clicked)
            logger.info("Processing single order")
            
            # Get order file path (v2 format only)
            repo_root = app.get_repo_root()
            sample_order = repo_root / 'samples' / 'JSON_9013830.json'
            
            if not sample_order.exists():
                ui.messageBox(
                    f'Order file not found:\n{sample_order}\n\n'
                    'Please ensure samples/JSON_9013830.json exists.',
                    'File Not Found'
                )
                logger.error(f"Order file not found: {sample_order}")
                return
            
            # Validate the sample file
            logger.info(f"Validating order file: {sample_order}")
            schema_path = str(app.get_schema_path())
            validator = OrderValidator(schema_path)
            is_valid, errors = validator.validate_json_file(str(sample_order))
            
            if not is_valid:
                logger.error("Order validation failed:")
                for error in errors:
                    logger.error(f"  - {error}")
                error_text = 'Sample order file validation failed:\n\n' + '\n'.join(f'  • {e}' for e in errors[:5])
                if len(errors) > 5:
                    error_text += f'\n  ... and {len(errors) - 5} more errors'
                ui.messageBox(error_text, 'Validation Failed')
                return
            
            logger.info("Order validation passed")
            
            # Initialize progress dialog
            progress = ProgressDialog(app_obj, "Processing Order")
            progress.show(f"Validated: {sample_order.name}\nOpening models...")
            
            # Phase 2: Load and process the order
            from order_processor import OrderProcessor
            
            processor = OrderProcessor(app_obj)
            
            # Open all models at startup
            logger.info("Opening all models...")
            progress.update("Opening door, panel, and stile models...")
            open_success, open_msg = processor.model_manager.open_all_models()
            
            if not open_success:
                progress.hide()
                ui.messageBox(
                    f'Failed to open models:\n{open_msg}',
                    'Error',
                    adsk.core.MessageBoxButtonTypes.OKButtonType,
                    adsk.core.MessageBoxIconTypes.WarningIconType
                )
                return
            
            logger.info(f"Models opened: {open_msg}")
            
            # Process order using v2 format (panels/doors/stiles)
            logger.info("Processing order with v2 format (panels/doors/stiles)")
            progress.update("Starting order processing...")
            
            success, message = processor.process_order_v2(str(sample_order), progress)
            
            # Log completion
            logger.info("=" * 80)
            if success:
                logger.info("ORDER PROCESSING COMPLETED SUCCESSFULLY")
            else:
                logger.error("ORDER PROCESSING FAILED")
            logger.info(f"Result: {message}")
            logger.info(f"Log file: {logger.get_log_path()}")
            logger.info("=" * 80)
            
            # Show final result in progress dialog for 2 seconds, then show summary
            if success:
                progress.update("✓ Complete! See results...", 100)
            else:
                progress.update("✗ Failed - see details...", 100)
            
            # Brief pause to show completion
            import time
            time.sleep(2)
            
            # Hide progress and show summary
            progress.hide()
            
            if success:
                ui.messageBox(
                    f'✓ Order Processing Complete!\n\n{message}\n\nLog: {logger.get_log_path()}',
                    'Success',
                    adsk.core.MessageBoxButtonTypes.OKButtonType,
                    adsk.core.MessageBoxIconTypes.InformationIconType
                )
            else:
                ui.messageBox(
                    f'Order Processing Failed:\n\n{message}\n\nLog: {logger.get_log_path()}',
                    'Error',
                    adsk.core.MessageBoxButtonTypes.OKButtonType,
                    adsk.core.MessageBoxIconTypes.WarningIconType
                )
            
        except Exception as e:
            # Hide progress dialog if it exists
            try:
                if 'progress' in locals():
                    progress.hide()
            except:
                pass
            
            app_obj = adsk.core.Application.get()
            ui = app_obj.userInterface
            logger = get_logger()
            logger.exception("COMMAND EXECUTION FAILED")
            logger.error(f"Exception: {str(e)}")
            logger.info(f"Log file: {logger.get_log_path()}")
            ui.messageBox(f'Failed to execute command:\n{str(e)}\n\nLog: {logger.get_log_path()}\n\n{traceback.format_exc()}', 'Error')


# Phase 1: No additional handlers needed - command executes immediately
