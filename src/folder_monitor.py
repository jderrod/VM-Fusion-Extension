"""
Folder Monitor - Continuously watch and process orders from dropbox folder
"""

import adsk.core
import adsk.fusion
import threading
import time
import shutil
from pathlib import Path
from datetime import datetime
from queue import Queue

from logger import get_logger
from validator import OrderValidator
from order_processor import OrderProcessor
import app


class ProcessFileEventHandler(adsk.core.CustomEventHandler):
    """Handles file processing on the UI thread"""
    
    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor
    
    def notify(self, args):
        """Process next file from queue on UI thread"""
        try:
            # Only process if not currently processing another file
            if not self.monitor.currently_processing and not self.monitor.file_queue.empty():
                file_path = self.monitor.file_queue.get()
                self.monitor._process_file_sync(file_path)
                self.monitor.file_queue.task_done()
        except:
            pass  # Silent fail


class FolderMonitor:
    """Monitors dropbox folder and processes orders automatically"""
    
    def __init__(self, app_obj: adsk.core.Application):
        self.app = app_obj
        self.ui = app_obj.userInterface
        self.logger = get_logger()
        self.is_running = False
        self.timer = None
        self.processor = None
        
        # Import config for network folder paths
        from config import ORDER_DROPBOX, ORDER_PROCESSING, ORDER_COMPLETED, ORDER_FAILED
        
        # Folder paths from config
        self.dropbox_folder = ORDER_DROPBOX
        self.processing_folder = ORDER_PROCESSING
        self.completed_folder = ORDER_COMPLETED
        self.failed_folder = ORDER_FAILED
        
        # Ensure folders exist
        self.dropbox_folder.mkdir(parents=True, exist_ok=True)
        self.processing_folder.mkdir(parents=True, exist_ok=True)
        self.completed_folder.mkdir(parents=True, exist_ok=True)
        self.failed_folder.mkdir(parents=True, exist_ok=True)
        
        # File queue for processing
        self.file_queue = Queue()
        self.currently_processing = False
        
        # Track files we've already queued (by full path to avoid duplicates)
        self.queued_files = set()
        
        # Schema for validation
        self.schema_path = str(app.get_schema_path())
        self.validator = OrderValidator(self.schema_path)
        
        # Custom event for thread-safe processing
        self.process_file_event = self.app.registerCustomEvent('FolderMonitorProcessFile')
        self.process_file_handler = ProcessFileEventHandler(self)
        self.process_file_event.add(self.process_file_handler)
    
    def start(self):
        """Start monitoring the dropbox folder"""
        if self.is_running:
            self.ui.messageBox('Folder monitor is already running!', 'Already Running')
            return
        
        self.is_running = True
        self.logger.info("=" * 80)
        self.logger.info("FOLDER MONITOR STARTED")
        self.logger.info(f"Watching: {self.dropbox_folder}")
        self.logger.info("=" * 80)
        
        # Initialize processor once
        self.processor = OrderProcessor(self.app)
        
        # Open all models at startup
        self.logger.info("Opening all models...")
        open_success, open_msg = self.processor.model_manager.open_all_models()
        
        if not open_success:
            self.ui.messageBox(
                f'Failed to open models:\n{open_msg}\n\nMonitoring stopped.',
                'Error',
                adsk.core.MessageBoxButtonTypes.OKButtonType,
                adsk.core.MessageBoxIconTypes.WarningIconType
            )
            self.is_running = False
            return
        
        self.logger.info(f"Models opened: {open_msg}")
        
        # Show status message
        self.ui.messageBox(
            f'Folder Monitor Started!\n\n'
            f'Watching: {self.dropbox_folder.name}/\n\n'
            f'Drop JSON order files into this folder.\n'
            f'Files are queued and processed one at a time.\n'
            f'Monitor runs continuously, waiting for new files.\n\n'
            f'To stop: Run "Run Order" again and click Stop.',
            'Monitor Active',
            adsk.core.MessageBoxButtonTypes.OKButtonType,
            adsk.core.MessageBoxIconTypes.InformationIconType
        )
        
        # Start checking for files
        self._check_for_files()
    
    def stop(self):
        """Stop monitoring"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.timer:
            self.timer.cancel()
            self.timer = None
        
        # Clear queue and tracking sets
        while not self.file_queue.empty():
            try:
                self.file_queue.get_nowait()
            except:
                break
        self.queued_files.clear()
        
        # Clean up custom event
        try:
            if self.process_file_event and self.process_file_handler:
                self.process_file_event.remove(self.process_file_handler)
        except:
            pass
        
        self.logger.info("=" * 80)
        self.logger.info("FOLDER MONITOR STOPPED")
        self.logger.info("=" * 80)
        
        self.ui.messageBox(
            'Folder Monitor Stopped',
            'Monitor Inactive',
            adsk.core.MessageBoxButtonTypes.OKButtonType,
            adsk.core.MessageBoxIconTypes.InformationIconType
        )
    
    def _check_for_files(self):
        """Check dropbox folder for new JSON files and add to queue"""
        if not self.is_running:
            return
        
        try:
            # Get all JSON files in dropbox
            json_files = list(self.dropbox_folder.glob('*.json'))
            
            for file_path in json_files:
                file_key = str(file_path.resolve())
                
                # Skip if already queued for processing
                if file_key in self.queued_files:
                    continue
                
                # Add to queue and mark as queued
                self.queued_files.add(file_key)
                self.logger.info(f"New file detected: {file_path.name}")
                
                # Wait a bit to ensure file is fully written
                time.sleep(0.5)
                
                # Add to queue
                self.file_queue.put(file_path)
                
                # Fire event to process queue (will process next file)
                self.app.fireCustomEvent('FolderMonitorProcessFile')
        
        except Exception as e:
            self.logger.error(f"Error checking for files: {str(e)}")
        
        finally:
            # Schedule next check in 3 seconds
            if self.is_running:
                self.timer = threading.Timer(3.0, self._check_for_files)
                self.timer.daemon = True
                self.timer.start()
    
    def _process_file_sync(self, file_path: Path):
        """Process a single order file (called on UI thread)"""
        file_key = str(file_path.resolve())
        try:
            self.currently_processing = True
            self.logger.info(f"Processing order: {file_path.name}")
            
            # Check if file still exists (might have been deleted)
            if not file_path.exists():
                self.logger.warning(f"File no longer exists: {file_path.name}")
                self.queued_files.discard(file_key)
                return
            
            # Validate JSON
            is_valid, errors = self.validator.validate_json_file(str(file_path))
            if not is_valid:
                self.logger.error(f"Invalid JSON: {file_path.name}")
                for error in errors:
                    self.logger.error(f"  - {error}")
                self._move_to_failed(file_path, '\n'.join(errors))
                self.queued_files.discard(file_key)
                return
            
            # Move to processing folder
            processing_path = self.processing_folder / file_path.name
            shutil.move(str(file_path), str(processing_path))
            self.logger.info(f"Moved to processing folder")
            
            # Remove from queued set since it's now moved
            self.queued_files.discard(file_key)
            
            # Process the order
            success, message = self.processor.process_order_v2(str(processing_path), progress_dialog=None)
            
            # Move to appropriate folder
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            if success:
                final_path = self.completed_folder / f"{timestamp}_{file_path.name}"
                shutil.move(str(processing_path), str(final_path))
                self.logger.info(f"✓ Order completed: {file_path.name}")
                self.logger.info(f"Moved to: {final_path.name}")
            else:
                final_path = self.failed_folder / f"{timestamp}_{file_path.name}"
                shutil.move(str(processing_path), str(final_path))
                
                # Write error message
                error_file = final_path.with_suffix('.txt')
                error_file.write_text(message)
                
                self.logger.error(f"✗ Order failed: {file_path.name}")
                self.logger.error(f"Reason: {message}")
                self.logger.info(f"Moved to: {final_path.name}")
        
        except Exception as e:
            self.logger.error(f"Error processing {file_path.name}: {str(e)}")
            self._move_to_failed(file_path, str(e))
            self.queued_files.discard(file_key)
        finally:
            self.currently_processing = False
            
            # If there are more files in queue, trigger processing for next one
            if not self.file_queue.empty() and self.is_running:
                self.app.fireCustomEvent('FolderMonitorProcessFile')
    
    def _move_to_failed(self, file_path: Path, reason: str):
        """Move file to failed folder with reason"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            failed_path = self.failed_folder / f"{timestamp}_{file_path.name}"
            
            if file_path.exists():
                shutil.move(str(file_path), str(failed_path))
            else:
                # File might be in processing folder
                processing_path = self.processing_folder / file_path.name
                if processing_path.exists():
                    shutil.move(str(processing_path), str(failed_path))
            
            # Write reason
            reason_file = failed_path.with_suffix('.txt')
            reason_file.write_text(reason)
            
            self.logger.info(f"Moved to failed folder: {failed_path.name}")
        except Exception as e:
            self.logger.error(f"Error moving to failed folder: {str(e)}")


# Global monitor instance
_monitor = None


def get_monitor(app_obj: adsk.core.Application) -> FolderMonitor:
    """Get or create the global monitor instance"""
    global _monitor
    if _monitor is None:
        _monitor = FolderMonitor(app_obj)
    return _monitor
