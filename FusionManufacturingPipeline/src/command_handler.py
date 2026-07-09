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
            result = ui.messageBox(
                'Choose an option:\n\n'
                'YES = Start Folder Monitor (continuous processing)\n'
                '       Watch dropbox folder and process files automatically\n\n'
                'NO = Process Single Order\n'
                '       Process samples/JSON_9013830.json once\n\n'
                'CANCEL = Exit',
                'Specs to Machine - Choose Mode',
                adsk.core.MessageBoxButtonTypes.YesNoCancelButtonType,
                adsk.core.MessageBoxIconTypes.QuestionIconType
            )
            
            if result == adsk.core.DialogResults.DialogCancel:
                # User cancelled
                return
            
            mode_is_monitor = (result == adsk.core.DialogResults.DialogYes)
            
            # Ask about run environment (Local dev vs VM production)
            from config import set_run_mode
            env_result = ui.messageBox(
                'Run Environment\n\n'
                'Where is this running?\n\n'
                'YES = VM (production network shares)\n'
                '       Dropbox: \\\\ddc-mefs\\iBob-Export\\S2S_Export\n'
                '       Output:  \\\\ddc-mefs\\Fusion\\Fusion Folders\\output\n\n'
                'NO = Local (dev machine)\n'
                '       Uses S2S File Test folder',
                'Run Environment',
                adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                adsk.core.MessageBoxIconTypes.QuestionIconType
            )
            
            run_mode = 'VM' if env_result == adsk.core.DialogResults.DialogYes else 'LOCAL'
            set_run_mode(run_mode)
            logger.info(f"Run mode: {run_mode}")
            
            # Ask about CAM generation
            cam_result = ui.messageBox(
                'CAM Generation\n\n'
                'Enable CAM toolpath regeneration and G-code export?\n\n'
                'YES = Full processing (parameters + CAM + G-code)\n'
                'NO = Parameters only (skip CAM / G-code)',
                'CAM Generation',
                adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                adsk.core.MessageBoxIconTypes.QuestionIconType
            )
            
            skip_cam = (cam_result == adsk.core.DialogResults.DialogNo)
            
            if skip_cam:
                logger.info("CAM generation: DISABLED (user unchecked)")
            else:
                logger.info("CAM generation: ENABLED")
            
            # Ask about drawing generation
            drawing_result = ui.messageBox(
                'Drawing Generation\n\n'
                'Enable door drawing export (PDF)?\n\n'
                'YES = Export door drawings after each door component\n'
                'NO = Skip drawing export (faster processing)',
                'Drawing Generation',
                adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                adsk.core.MessageBoxIconTypes.QuestionIconType
            )
            
            skip_drawing = (drawing_result == adsk.core.DialogResults.DialogNo)
            
            if skip_drawing:
                logger.info("Drawing generation: DISABLED (user unchecked)")
            else:
                logger.info("Drawing generation: ENABLED")
            
            if mode_is_monitor:
                # Start folder monitoring
                logger.info("Starting folder monitor mode")
                monitor.start(skip_cam=skip_cam, skip_drawing=skip_drawing)
                return
            
            # Continue with single order processing (NO was clicked on mode dialog)
            logger.info("Processing single order")
            from config import ensure_folder_structure
            ensure_folder_structure()
            
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
            
            processor = OrderProcessor(app_obj, skip_cam=skip_cam, skip_drawing=skip_drawing)
            
            # Set up cloud models from team project (Fusion Hub)
            # Uses saved config from drawing_config.json (editable via Drawing Config palette)
            logger.info("Setting up cloud models from Fusion Hub...")
            progress.update("Setting up cloud models...")
            from cloud_config import get_setup_cloud_models_args
            cloud_kwargs = get_setup_cloud_models_args()
            logger.info(f"Cloud config: door={cloud_kwargs.get('door_name')}, panel={cloud_kwargs.get('panel_name')}")
            cloud_success, cloud_msg = processor.model_manager.setup_cloud_models(**cloud_kwargs)
            if cloud_success:
                logger.info(f"Cloud models: {cloud_msg}")
            else:
                logger.warning(f"Cloud models not configured: {cloud_msg}")
                logger.info("Will use local models from inputs folder as fallback")
            
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
