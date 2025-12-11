"""
Order Watcher Service
Monitors a folder for new JSON order files and automatically processes them in Fusion 360
"""

import time
import os
import sys
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
import json
import logging

# Setup logging
log_folder = Path(__file__).parent / 'logs'
log_folder.mkdir(exist_ok=True)
log_file = log_folder / f'watcher_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class OrderFileHandler:
    """Handles new JSON order files with polling-based monitoring"""
    
    def __init__(self, watch_folder, processing_folder, completed_folder, failed_folder, fusion_path):
        self.watch_folder = Path(watch_folder)
        self.processing_folder = Path(processing_folder)
        self.completed_folder = Path(completed_folder)
        self.failed_folder = Path(failed_folder)
        self.fusion_path = fusion_path
        self.processing_files = set()
        self.seen_files = set()
        
        # Create folders if they don't exist
        for folder in [self.processing_folder, self.completed_folder, self.failed_folder]:
            folder.mkdir(parents=True, exist_ok=True)
    
    def check_for_new_files(self):
        """Check watch folder for new JSON files (polling approach)"""
        try:
            # Get all JSON files in watch folder
            json_files = list(self.watch_folder.glob('*.json'))
            
            for file_path in json_files:
                file_key = str(file_path)
                
                # Skip if already seen or processing
                if file_key in self.seen_files or file_key in self.processing_files:
                    continue
                
                # Mark as seen
                self.seen_files.add(file_key)
                
                logger.info(f'New file detected: {file_path.name}')
                
                # Wait a bit to ensure file is fully written
                time.sleep(2)
                
                # Validate it's a valid JSON file
                if not self._validate_json(file_path):
                    logger.error(f'Invalid JSON file: {file_path.name}')
                    self._move_to_failed(file_path, 'Invalid JSON format')
                    continue
                
                # Process the order
                self.processing_files.add(file_key)
                self._process_order(file_path)
                self.processing_files.discard(file_key)
                
        except Exception as e:
            logger.exception(f'Error checking for new files: {str(e)}')
    
    def _validate_json(self, file_path):
        """Validate JSON file format"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # Check for required fields (v2 format)
            if 'order_id' not in data:
                logger.warning(f'Missing order_id in {file_path.name}')
                return False
            
            # Should have at least one component type
            if not any(key in data for key in ['panels', 'doors', 'stiles']):
                logger.warning(f'No component arrays found in {file_path.name}')
                return False
            
            return True
        except Exception as e:
            logger.error(f'JSON validation error: {str(e)}')
            return False
    
    def _process_order(self, file_path):
        """Process an order file through Fusion 360"""
        try:
            logger.info(f'Processing order: {file_path.name}')
            
            # Move to processing folder
            processing_path = self.processing_folder / file_path.name
            shutil.move(str(file_path), str(processing_path))
            logger.info(f'Moved to processing folder')
            
            # Launch Fusion 360 and process order
            success = self._run_fusion_order(processing_path)
            
            if success:
                # Move to completed folder
                completed_path = self.completed_folder / f'{datetime.now().strftime("%Y%m%d_%H%M%S")}_{file_path.name}'
                shutil.move(str(processing_path), str(completed_path))
                logger.info(f'Order completed successfully: {file_path.name}')
            else:
                # Move to failed folder
                self._move_to_failed(processing_path, 'Processing failed')
                logger.error(f'Order processing failed: {file_path.name}')
        
        except Exception as e:
            logger.exception(f'Error processing order {file_path.name}: {str(e)}')
            self._move_to_failed(file_path, str(e))
    
    def _run_fusion_order(self, order_file):
        """
        Launch Fusion 360 and process the order
        
        Args:
            order_file: Path to order JSON file
            
        Returns:
            True if successful
        """
        try:
            logger.info(f'Launching Fusion 360...')
            
            # Create a trigger file that the extension will watch for
            trigger_file = Path(__file__).parent / 'auto_run_order.json'
            shutil.copy(str(order_file), str(trigger_file))
            
            # Launch Fusion 360
            # Note: This launches Fusion but doesn't wait for it to close
            subprocess.Popen([self.fusion_path])
            
            logger.info(f'Fusion 360 launched. Waiting for extension to process order...')
            
            # Wait for result file (extension will create this when done)
            result_file = Path(__file__).parent / 'auto_run_result.json'
            if result_file.exists():
                result_file.unlink()  # Remove old result
            
            # Wait up to 30 minutes for processing
            timeout = 1800  # 30 minutes
            check_interval = 5  # Check every 5 seconds
            elapsed = 0
            
            while elapsed < timeout:
                if result_file.exists():
                    # Read result
                    with open(result_file, 'r') as f:
                        result = json.load(f)
                    
                    success = result.get('success', False)
                    message = result.get('message', 'No message')
                    
                    logger.info(f'Result received: success={success}, message={message}')
                    
                    # Clean up
                    result_file.unlink()
                    if trigger_file.exists():
                        trigger_file.unlink()
                    
                    return success
                
                time.sleep(check_interval)
                elapsed += check_interval
            
            # Timeout
            logger.error('Timeout waiting for order processing result')
            if trigger_file.exists():
                trigger_file.unlink()
            return False
            
        except Exception as e:
            logger.exception(f'Error running Fusion order: {str(e)}')
            return False
    
    def _move_to_failed(self, file_path, reason):
        """Move file to failed folder with timestamp and reason"""
        try:
            failed_path = self.failed_folder / f'{datetime.now().strftime("%Y%m%d_%H%M%S")}_{Path(file_path).name}'
            
            if Path(file_path).exists():
                shutil.move(str(file_path), str(failed_path))
            
            # Write failure reason
            reason_file = failed_path.with_suffix('.txt')
            with open(reason_file, 'w') as f:
                f.write(f'Failed at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
                f.write(f'Reason: {reason}\n')
            
            logger.info(f'Moved to failed folder: {failed_path.name}')
        except Exception as e:
            logger.error(f'Error moving file to failed folder: {str(e)}')


def main():
    """Main entry point"""
    logger.info('='*60)
    logger.info('Order Watcher Service Starting')
    logger.info('='*60)
    
    # Configuration
    repo_root = Path(__file__).parent
    watch_folder = repo_root / 'order_dropbox'
    processing_folder = repo_root / 'order_processing'
    completed_folder = repo_root / 'order_completed'
    failed_folder = repo_root / 'order_failed'
    
    # Fusion 360 path - adjust if needed
    fusion_path = r'C:\Users\james.derrod\AppData\Local\Autodesk\webdeploy\production\6a0c9611291d45bb9226980209917c3d\FusionLauncher.exe'
    
    # Create watch folder if it doesn't exist
    watch_folder.mkdir(exist_ok=True)
    
    logger.info(f'Watch folder: {watch_folder}')
    logger.info(f'Processing folder: {processing_folder}')
    logger.info(f'Completed folder: {completed_folder}')
    logger.info(f'Failed folder: {failed_folder}')
    logger.info(f'Fusion 360: {fusion_path}')
    logger.info('')
    logger.info('Waiting for order files...')
    logger.info('(Press Ctrl+C to stop)')
    logger.info('')
    
    # Set up file handler
    handler = OrderFileHandler(
        watch_folder,
        processing_folder,
        completed_folder,
        failed_folder,
        fusion_path
    )
    
    # Poll for new files every 2 seconds
    try:
        while True:
            handler.check_for_new_files()
            time.sleep(2)
    except KeyboardInterrupt:
        logger.info('Stopping watcher service...')
    
    logger.info('Watcher service stopped')


if __name__ == '__main__':
    main()
