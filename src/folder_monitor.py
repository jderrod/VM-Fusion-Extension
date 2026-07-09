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
import logging

VERSION = "2.4.24"  # Bump on each VM deploy


class ProcessFileEventHandler(adsk.core.CustomEventHandler):
    """Handles file checking and processing on the UI thread.
    
    The timer thread fires the custom event as a wake-up signal.
    All file detection and processing happens here on the UI thread,
    where Fusion API calls are safe and event delivery is reliable.
    """
    
    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor
    
    def notify(self, args):
        """Check for new files and process them on the UI thread"""
        try:
            if not self.monitor.is_running:
                return
            
            # Update heartbeat so timer knows events are being delivered
            self.monitor._last_event_handled = time.time()
            
            # Check for new files in the dropbox
            self.monitor._scan_for_new_files()
            
            # Process next file from queue if not already processing
            if not self.monitor.currently_processing and not self.monitor.file_queue.empty():
                file_path = self.monitor.file_queue.get()
                self.monitor._process_file_sync(file_path)
                self.monitor.file_queue.task_done()
        except Exception as e:
            self.monitor._log_monitor(f"Event handler error: {str(e)}")
            import traceback
            self.monitor._log_monitor(f"Event handler traceback: {traceback.format_exc()}")


class FolderMonitor:
    """Monitors dropbox folder and processes orders automatically"""
    
    def __init__(self, app_obj: adsk.core.Application):
        self.app = app_obj
        self.ui = app_obj.userInterface
        self.logger = get_logger()
        self.is_running = False
        self.timer = None
        self.processor = None
        
        # Folder paths — set to None here, populated in start() after
        # the user picks Local/VM mode via set_run_mode().
        self.dropbox_folder = None
        self.processing_folder = None
        self.completed_folder = None
        self.failed_folder = None
        self.monitor_log_path = None
        
        # File queue for processing
        self.file_queue = Queue()
        self.currently_processing = False
        
        # Track files we've already queued (by full path to avoid duplicates)
        self.queued_files = set()
        
        # Schema for validation
        self.schema_path = str(app.get_schema_path())
        self.validator = OrderValidator(self.schema_path)
        
        # Heartbeat tracking for event delivery monitoring
        self._last_event_handled = time.time()
        self._fire_count = 0
        self._event_id = f'FolderMonitorProcessFile_{id(self)}'
        
        # Custom event for thread-safe processing
        self.process_file_event = self.app.registerCustomEvent(self._event_id)
        self.process_file_handler = ProcessFileEventHandler(self)
        self.process_file_event.add(self.process_file_handler)
    
    def _setup_monitor_log(self):
        """Set up dedicated monitor log file for debugging"""
        try:
            # Create a dedicated file handler for monitor operations
            self.monitor_file_handler = logging.FileHandler(str(self.monitor_log_path), mode='a')
            self.monitor_file_handler.setLevel(logging.DEBUG)
            
            formatter = logging.Formatter(
                '%(asctime)s - MONITOR - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            self.monitor_file_handler.setFormatter(formatter)
            
            # Add to the pipeline logger
            self.logger.logger.addHandler(self.monitor_file_handler)
            
            # Write startup marker
            self._log_monitor(f"{'='*60}")
            self._log_monitor(f"MONITOR LOG INITIALIZED")
            self._log_monitor(f"Log file: {self.monitor_log_path}")
            self._log_monitor(f"Dropbox folder: {self.dropbox_folder}")
            self._log_monitor(f"{'='*60}")
        except Exception as e:
            self.logger.error(f"Failed to set up monitor log: {str(e)}")
    
    def _log_monitor(self, message: str):
        """Write to monitor log file directly"""
        try:
            with open(self.monitor_log_path, 'a') as f:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"{timestamp} - MONITOR - {message}\n")
                f.flush()
        except Exception:
            pass
    
    def start(self, skip_cam: bool = False, skip_drawing: bool = False):
        """Start monitoring the dropbox folder"""
        if self.is_running:
            self.ui.messageBox('Folder monitor is already running!', 'Already Running')
            return
        
        try:
            # Re-read config paths — set_run_mode() may have switched them
            # after the singleton was constructed with LOCAL defaults.
            from config import (ORDER_DROPBOX, ORDER_PROCESSING,
                                ORDER_COMPLETED, ORDER_FAILED, OUTPUT_LOGS,
                                RUN_MODE, ensure_folder_structure)
            self.dropbox_folder = ORDER_DROPBOX
            self.processing_folder = ORDER_PROCESSING
            self.completed_folder = ORDER_COMPLETED
            self.failed_folder = ORDER_FAILED
            
            # Ensure all folders exist (including VM-specific ones)
            ensure_folder_structure()
            
            # Init monitor log in the output dir with datetime stamp
            OUTPUT_LOGS.mkdir(parents=True, exist_ok=True)
            session_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.monitor_log_path = OUTPUT_LOGS / f'folder_monitor_{session_timestamp}.log'
            self._setup_monitor_log()
            
            self.is_running = True
            self.skip_cam = skip_cam
            self.skip_drawing = skip_drawing
            self.logger.info("=" * 80)
            self.logger.info(f"FOLDER MONITOR STARTED  v{VERSION}  (mode={RUN_MODE})")
            self.logger.info(f"Watching: {self.dropbox_folder}")
            self.logger.info(f"CAM generation: {'DISABLED' if skip_cam else 'ENABLED'}")
            self.logger.info(f"Drawing generation: {'DISABLED' if skip_drawing else 'ENABLED'}")
            self.logger.info("=" * 80)
            
            # Initialize processor once
            self.processor = OrderProcessor(self.app, skip_cam=skip_cam, skip_drawing=skip_drawing)
            
            # Set up cloud models from team project (Fusion Hub)
            # Uses saved config from drawing_config.json (editable via Drawing Config palette)
            self.logger.info("Setting up cloud models from Fusion Hub...")
            from cloud_config import get_setup_cloud_models_args
            cloud_kwargs = get_setup_cloud_models_args()
            self.logger.info(f"Cloud config: door={cloud_kwargs.get('door_name')}, panel={cloud_kwargs.get('panel_name')}")
            cloud_success, cloud_msg = self.processor.model_manager.setup_cloud_models(**cloud_kwargs)
            if cloud_success:
                self.logger.info(f"Cloud models: {cloud_msg}")
            else:
                self.logger.warning(f"Cloud models not configured: {cloud_msg}")
                self.logger.info("Will use local models from inputs folder as fallback")
            
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
            
            # Drawing documents are opened on-demand when an order needs one.
            # documents.open() for .f2d files can hang indefinitely on the VM,
            # so we do NOT pre-open them at startup. If a drawing open hangs,
            # the user restarts Fusion; consecutive failure tracking will then
            # skip drawing export for subsequent orders until reset.
            # Alternatively, the user can manually open drawings in Fusion
            # before starting the monitor — the code detects already-open docs.
            if not skip_drawing:
                self.logger.info("Drawing generation enabled — drawings will be opened on-demand (first order that needs one)")
            
            # Show status message
            mode_label = 'VM (network shares)' if RUN_MODE == 'VM' else 'Local (dev machine)'
            self.ui.messageBox(
                f'Folder Monitor Started!\n\n'
                f'Mode: {mode_label}\n'
                f'Watching: {self.dropbox_folder}\n\n'
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
            
        except Exception as e:
            self.is_running = False
            error_msg = f'Error starting folder monitor: {str(e)}'
            self.logger.error(error_msg)
            import traceback
            self.logger.error(traceback.format_exc())
            self.ui.messageBox(
                error_msg,
                'Startup Error',
                adsk.core.MessageBoxButtonTypes.OKButtonType,
                adsk.core.MessageBoxIconTypes.CriticalIconType
            )
    
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
            except Exception:
                break
        self.queued_files.clear()
        
        # Clean up custom event
        try:
            if self.process_file_event and self.process_file_handler:
                self.process_file_event.remove(self.process_file_handler)
            self.app.unregisterCustomEvent(self._event_id)
        except Exception:
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
    
    def _scan_for_new_files(self):
        """Scan dropbox folder for new JSON files and add to queue.
        Called on the UI thread from the event handler."""
        try:
            json_files = sorted(self.dropbox_folder.glob('*.json'))
            
            new_count = 0
            for file_path in json_files:
                # Use filename as key (not resolve() which is unreliable on UNC paths)
                file_key = file_path.name
                
                # Skip if already queued for processing
                if file_key in self.queued_files:
                    continue
                
                # Add to queue and mark as queued
                self.queued_files.add(file_key)
                self._log_monitor(f"NEW FILE detected: {file_path.name}")
                self.logger.info(f"New file detected: {file_path.name}")
                new_count += 1
                
                # Add to queue
                self.file_queue.put(file_path)
            
            # Log scan results when new files found or every scan to aid debugging
            if new_count > 0:
                self._log_monitor(f"Scan: {len(json_files)} file(s) in dropbox, {new_count} new, queue size={self.file_queue.qsize()}")
        
        except Exception as e:
            self._log_monitor(f"ERROR scanning for files: {str(e)}")
            self.logger.error(f"Error scanning for files: {str(e)}")
    
    def _reregister_event(self):
        """Cleanly unregister and re-register the custom event + handler.
        
        Must be called on the UI thread (e.g. from _process_file_sync's
        finally block).  During long processing, the background timer fires
        fireCustomEvent repeatedly while the UI thread is blocked.  Fusion
        may silently invalidate the event registration after many queued
        fires, causing notify() to never be called again.  A clean
        re-registration restores delivery.
        """
        try:
            # Remove old handler / unregister
            try:
                if self.process_file_event and self.process_file_handler:
                    self.process_file_event.remove(self.process_file_handler)
            except Exception:
                pass
            try:
                self.app.unregisterCustomEvent(self._event_id)
            except Exception:
                pass
            
            # Re-register fresh
            self.process_file_event = self.app.registerCustomEvent(self._event_id)
            self.process_file_handler = ProcessFileEventHandler(self)
            self.process_file_event.add(self.process_file_handler)
            self._log_monitor("Custom event re-registered on UI thread")
        except Exception as e:
            self._log_monitor(f"ERROR re-registering custom event: {str(e)}")
    
    def _fire_check_event(self):
        """Timer callback: fires the custom event to wake up the UI thread.
        This runs on a background thread - only fires the event, no Fusion API calls."""
        if not self.is_running:
            return
        
        self._fire_count += 1
        
        try:
            self.app.fireCustomEvent(self._event_id)
            
            # Log heartbeat every 20 fires (~60 seconds) so we know timer is alive
            if self._fire_count % 20 == 0:
                self._log_monitor(f"Timer heartbeat #{self._fire_count} (event_id={self._event_id})")
        except Exception as e:
            # Do NOT re-register the event here on the background thread.
            # Re-registering from a non-UI thread creates duplicate handlers
            # (causes 4x log lines) and can corrupt the event registration
            # so that notify() stops being called entirely.
            # fireCustomEvent failing while the UI thread is blocked is
            # expected and harmless — the next fire after the UI thread
            # unblocks will succeed.
            if self._fire_count % 20 == 0:
                self._log_monitor(f"WARNING: fireCustomEvent failed (attempt #{self._fire_count}): {str(e)}")
        finally:
            # Schedule next wake-up
            if self.is_running:
                self.timer = threading.Timer(3.0, self._fire_check_event)
                self.timer.daemon = True
                self.timer.start()
    
    def _check_for_files(self):
        """Start the periodic file checking loop via custom events."""
        if not self.is_running:
            return
        
        # Do an initial scan on the UI thread directly
        self._scan_for_new_files()
        
        # Start the timer loop that fires custom events every 3 seconds.
        # The first timer fire (after 3s) will pick up any queued files
        # via notify().  Do NOT process synchronously here — 
        # _process_file_sync calls _start_timer() in its finally block,
        # and calling _start_timer() again after it returns would create
        # a timer race condition.
        self._start_timer()
    
    def _start_timer(self):
        """Start or restart the periodic timer."""
        # Cancel existing timer if any
        if self.timer:
            try:
                self.timer.cancel()
            except Exception:
                pass
        
        self._fire_count = 0
        self._last_event_handled = time.time()
        self._log_monitor("Starting periodic file check (3 second interval)...")
        self.timer = threading.Timer(3.0, self._fire_check_event)
        self.timer.daemon = True
        self.timer.start()
    
    def _process_file_sync(self, file_path: Path):
        """Process a single order file (called on UI thread)"""
        file_key = file_path.name
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
            
            # Move to appropriate folder with a human-readable timestamp,
            # e.g. "IBUS447851 Jun 5 2026 - 1313.json" (24-hour time, no colons
            # since they are illegal in Windows filenames).
            human_ts = datetime.now().strftime('%b %#d %Y - %H%M')
            new_name = f"{file_path.stem} {human_ts}{file_path.suffix}"
            if success:
                final_path = self.completed_folder / new_name
                shutil.move(str(processing_path), str(final_path))
                self.logger.info(f"✓ Order completed: {file_path.name}")
                self.logger.info(f"Moved to: {final_path.name}")
            else:
                final_path = self.failed_folder / new_name
                shutil.move(str(processing_path), str(final_path))
                
                # Write error message
                error_file = final_path.with_suffix('.txt')
                error_file.write_text(message)
                
                self.logger.error(f"✗ Order failed: {file_path.name}")
                self.logger.error(f"Reason: {message}")
                self.logger.info(f"Moved to: {final_path.name}")
        
        except Exception as e:
            self.logger.error(f"Error processing {file_path.name}: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            self._move_to_failed(file_path, str(e))
            self.queued_files.discard(file_key)
        finally:
            self.currently_processing = False
            
            # Memory cleanup after each order to prevent accumulation
            self._perform_memory_cleanup()
            
            # Re-register the custom event to ensure clean delivery.
            # During long processing the background timer fires
            # fireCustomEvent repeatedly while the UI thread is blocked.
            # This can corrupt Fusion's internal event state, causing
            # notify() to never be called again.  A clean re-registration
            # on the UI thread (here) restores delivery.
            if self.is_running:
                self._reregister_event()
                self._log_monitor("Order complete - restarting timer for continuous monitoring")
                
                # Scan immediately on the UI thread (we're already here).
                # This picks up files that arrived during the previous order's
                # processing without waiting for the next timer fire.
                self._scan_for_new_files()
                
                # Process next file directly if queue has items.
                # This avoids relying on fireCustomEvent delivery which can
                # be unreliable immediately after event re-registration.
                if not self.file_queue.empty():
                    next_file = self.file_queue.get()
                    self._log_monitor(f"Processing next queued file immediately: {next_file.name}")
                    self._process_file_sync(next_file)
                    self.file_queue.task_done()
                else:
                    # No more files — start timer to wait for new ones
                    self._start_timer()
    
    def _perform_memory_cleanup(self):
        """
        Perform memory cleanup after each order to prevent memory accumulation.
        This is critical for long-running continuous operation.
        Closing cached documents between orders prevents BREP kernel state
        accumulation that causes PassiveIdGenerator crashes.
        """
        try:
            import gc
            import time
            
            # Clean up cached documents in model manager
            # Close documents between orders to prevent BREP state accumulation
            if self.processor and hasattr(self.processor, 'model_manager'):
                cache_status = self.processor.model_manager.get_cache_status()
                self.logger.info(f"Cache status before cleanup: {cache_status['total_cached']} documents")
                
                # Close documents between orders to prevent BREP crash accumulation
                cleanup_success, cleanup_msg = self.processor.model_manager.cleanup_cached_documents(close_documents=True)
                self.logger.info(f"Memory cleanup: {cleanup_msg}")
            
            # NOTE: Do NOT reset _drawing_exporter between orders.
            # Resetting forces a full close/reopen cycle of the drawing on the
            # next order, which pumps 8+ doEvents() calls and triggers PLM360
            # crashes. The cached drawing uses the fast updateAllReferences()
            # path instead, which is safe and much cheaper.
            
            # Force garbage collection
            collected = gc.collect()
            self.logger.info(f"Garbage collection: freed {collected} objects")
            
            # Stabilization delay between orders.
            # When CAM+drawing are skipped (param-only), use a short delay
            # since there's no BREP regeneration or cloud sync to settle.
            if self.processor and self.processor.skip_cam and self.processor.skip_drawing:
                self.logger.info("Stabilization delay between orders (0.5s, param-only mode)...")
                time.sleep(0.5)
            else:
                # Pump one doEvents() so Fusion can process pending saves, cloud
                # uploads, and internal cleanup. A single call is safe — it's
                # sustained loops of hundreds of calls that build PLM360 pressure.
                self.logger.info("Stabilization delay between orders (3s)...")
                adsk.doEvents()
                time.sleep(3.0)
            
        except Exception as e:
            self.logger.warning(f"Memory cleanup warning: {str(e)}")
    
    def _move_to_failed(self, file_path: Path, reason: str):
        """Move file to failed folder with reason"""
        try:
            human_ts = datetime.now().strftime('%b %#d %Y - %H%M')
            failed_path = self.failed_folder / f"{file_path.stem} {human_ts}{file_path.suffix}"
            
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
