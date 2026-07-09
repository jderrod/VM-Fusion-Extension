"""
Auto-Run Handler
Checks for auto-run trigger file and processes orders automatically
"""

import adsk.core
import adsk.fusion
import os
import json
from pathlib import Path
from logger import get_logger


class AutoRunHandler:
    """Handles automatic order processing from file watcher"""
    
    def __init__(self, app):
        self.app = app
        self.ui = app.userInterface
        self.logger = get_logger()
        
        # Get repo root
        from app import get_repo_root
        self.repo_root = get_repo_root()
        
        self.trigger_file = self.repo_root / 'auto_run_order.json'
        self.result_file = self.repo_root / 'auto_run_result.json'
    
    def check_and_run(self):
        """
        Check if there's a trigger file and process it
        
        Returns:
            True if auto-run was triggered
        """
        try:
            if not self.trigger_file.exists():
                return False
            
            self.logger.info('='*60)
            self.logger.info('AUTO-RUN MODE DETECTED')
            self.logger.info(f'Trigger file: {self.trigger_file}')
            self.logger.info('='*60)
            
            # Read order file
            order_file_path = str(self.trigger_file)
            
            # Process the order
            success, message = self._process_order(order_file_path)
            
            # Write result
            self._write_result(success, message)
            
            # Clean up trigger file
            if self.trigger_file.exists():
                self.trigger_file.unlink()
            
            self.logger.info('='*60)
            self.logger.info(f'AUTO-RUN COMPLETE: success={success}')
            self.logger.info('='*60)
            
            return True
            
        except Exception as e:
            self.logger.exception('Error in auto-run handler')
            self._write_result(False, f'Exception: {str(e)}')
            return False
    
    def _process_order(self, order_file_path):
        """
        Process an order file
        
        Args:
            order_file_path: Path to order JSON file
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Import required modules
            from order_processor import OrderProcessor
            from validator import OrderValidator
            from model_selection_dialog import ModelSelectionDialog
            
            # Validate order
            self.logger.info(f'Validating order: {order_file_path}')
            validator = OrderValidator()
            is_valid, validation_msg = validator.validate_order(order_file_path)
            
            if not is_valid:
                self.logger.error(f'Order validation failed: {validation_msg}')
                return False, f'Validation failed: {validation_msg}'
            
            self.logger.info('Order validation passed')
            
            # Create processor
            processor = OrderProcessor(self.app)
            
            # Show model selection dialog (auto-accept current models)
            model_dialog = ModelSelectionDialog(self.app, processor.model_manager)
            confirmed, selected_models = model_dialog.show()
            
            if not confirmed:
                return False, 'Model selection cancelled'
            
            # Update model manager with selected models
            for model_type, model_path in selected_models.items():
                if model_path:
                    processor.model_manager.set_model_path(model_type, model_path)
            
            # Open all models
            self.logger.info('Opening models...')
            open_success, open_msg = processor.model_manager.open_all_models()
            
            if not open_success:
                self.logger.error(f'Failed to open models: {open_msg}')
                return False, f'Model opening failed: {open_msg}'
            
            self.logger.info('Models opened successfully')
            
            # Process order (v2 format)
            self.logger.info('Processing order...')
            success, message = processor.process_order_v2(order_file_path, progress_dialog=None)
            
            return success, message
            
        except Exception as e:
            self.logger.exception('Error processing order in auto-run mode')
            return False, f'Processing exception: {str(e)}'
    
    def _write_result(self, success, message):
        """
        Write result to file for watcher service
        
        Args:
            success: True if successful
            message: Result message
        """
        try:
            result = {
                'success': success,
                'message': message,
                'timestamp': str(Path(__file__).stat().st_mtime)
            }
            
            with open(self.result_file, 'w') as f:
                json.dump(result, f, indent=2)
            
            self.logger.info(f'Result written to: {self.result_file}')
            
        except Exception as e:
            self.logger.error(f'Failed to write result file: {str(e)}')
