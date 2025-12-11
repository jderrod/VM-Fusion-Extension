"""
Post Processor for Fusion 360 Manufacturing Pipeline
Handles G-code generation and output file management
"""

import adsk.core
import adsk.fusion
import adsk.cam
import os
from typing import List, Tuple, Optional
from pathlib import Path


class PostProcessor:
    """Manages post processing operations for CAM setups"""
    
    def __init__(self, app: adsk.core.Application, output_dir: str):
        """
        Initialize post processor.
        
        Args:
            app: Fusion Application object
            output_dir: Base directory for output files
        """
        self.app = app
        self.ui = app.userInterface
        self.output_dir = Path(output_dir)
        self.counter_file = Path(__file__).parent.parent / 'nc_program_counter.txt'
        
        # Import logger
        from logger import get_logger
        self.logger = get_logger()
        
        # Setup custom post processor
        self._setup_custom_post_processor()
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _setup_custom_post_processor(self):
        """
        Copy custom Anderson Stratos post processor to Fusion's user post folder.
        This ensures Fusion can find and use it.
        """
        import shutil
        
        try:
            # Source: our custom post processor
            source_post = Path(__file__).parent.parent / 'Post Processing' / 'Anderson Stratos 2.cps'
            
            # Destination: Fusion's user post folder
            # Get user's local app data folder
            local_appdata = os.environ.get('LOCALAPPDATA', '')
            user_post_folder = Path(local_appdata) / 'Autodesk' / 'Webservices' / 'CAM360' / 'Posts'
            
            # Create destination folder if needed
            user_post_folder.mkdir(parents=True, exist_ok=True)
            
            # Destination file
            dest_post = user_post_folder / 'Anderson Stratos 2.cps'
            
            # Copy if source exists and dest doesn't exist or is older
            if source_post.exists():
                if not dest_post.exists() or source_post.stat().st_mtime > dest_post.stat().st_mtime:
                    shutil.copy2(str(source_post), str(dest_post))
                    self.logger.info(f'Copied custom post processor to: {dest_post}')
                
                # Store the path in Fusion's user folder
                self.post_processor_path = str(dest_post)
                self.logger.info(f'Using post processor: Anderson Stratos 2.cps')
            else:
                # Fallback to generic post if custom not found
                self.logger.warning(f'Custom post processor not found at {source_post}, will use CAM generic folder')
                self.post_processor_path = None
                
        except Exception as e:
            self.logger.error(f'Error setting up custom post processor: {str(e)}')
            self.post_processor_path = None
    
    def get_next_program_number(self) -> int:
        """
        Get the next program number from persistent counter.
        Starting at 1001, increments for each program.
        
        Returns:
            Next program number
        """
        try:
            if self.counter_file.exists():
                with open(self.counter_file, 'r') as f:
                    last_number = int(f.read().strip())
                    next_number = last_number + 1
            else:
                # First run, start at 1001
                next_number = 1001
            
            # Save the new number
            with open(self.counter_file, 'w') as f:
                f.write(str(next_number))
            
            return next_number
            
        except Exception as e:
            # If anything goes wrong, default to timestamp-based naming
            import time
            return int(time.time() % 10000) + 1000
    
    def post_process_setup(self, cam: adsk.cam.CAM, setup: adsk.cam.Setup, program_number: int, component_id: str, order_id: str) -> Tuple[bool, str, Optional[str]]:
        """
        Post process a single setup to generate G-code.
        
        Args:
            cam: CAM object
            setup: Setup to post process
            program_number: Program number for the file (e.g., 1001)
            component_id: Component ID (e.g., D1, P1)
            order_id: Order ID (e.g., IBUS366574)
            
        Returns:
            Tuple of (success: bool, message: str, output_file_path: str or None)
        """
        try:
            setup_name = setup.name
            
            # Check if setup has any valid toolpaths
            has_toolpaths = False
            for operation in setup.allOperations:
                if operation.hasToolpath and not operation.isSuppressed:
                    has_toolpaths = True
                    break
            
            if not has_toolpaths:
                return False, f"Setup '{setup_name}' has no valid toolpaths to post", None
            
            # Build output filename: 1-component_id-order_id.nc (e.g., 1-D1-IBUS366574.nc)
            # Note: If component has multiple setups, they will overwrite each other
            output_filename = f"1-{component_id}-{order_id}.nc"
            output_path = self.output_dir / output_filename
            
            # Get post processor path
            if self.post_processor_path and os.path.exists(self.post_processor_path):
                # Use custom Anderson Stratos post processor
                post_config = self.post_processor_path
                self.logger.info(f'{setup_name}: Using custom post processor: Anderson Stratos 2.cps')
            else:
                # Fallback to generic richauto if custom not available
                post_config = cam.genericPostFolder + '/richauto.cps'
                self.logger.warning(f'{setup_name}: Custom post not found, using richauto.cps')
            
            # Check if post processor exists
            if not os.path.exists(post_config):
                return False, f"Post processor not found: {post_config}", None
            
            # Create post input
            post_input = adsk.cam.PostProcessInput.create(
                str(program_number),  # Program name/number
                post_config,           # Post processor path
                str(self.output_dir),  # Output folder
                adsk.cam.PostOutputUnitOptions.DocumentUnitsOutput  # Use document units
            )
            
            # Configure post input
            post_input.isOpenInEditor = False  # Don't open in editor
            
            # Post process the setup
            cam.postProcess(setup, post_input)
            
            # Fusion creates the file as: program_number.nc (e.g., 1093.nc)
            # We need to rename it to: program_number-component_id-order_id.nc
            fusion_output_path = self.output_dir / f"{program_number}.nc"
            
            # Verify file was created by Fusion
            if fusion_output_path.exists():
                # Rename to our desired format
                fusion_output_path.rename(output_path)
                
                if output_path.exists():
                    file_size = output_path.stat().st_size
                    return True, f"Generated {output_filename} ({file_size} bytes)", str(output_path)
                else:
                    return False, f"Failed to rename {fusion_output_path.name} to {output_filename}", None
            else:
                return False, f"Post process completed but file not found: {program_number}.nc", None
            
        except Exception as e:
            return False, f"Post processing failed: {str(e)}", None
    
    def post_process_all_setups(self, cam: adsk.cam.CAM, setups: List[adsk.cam.Setup], component_id: str, order_id: str) -> Tuple[bool, str, List[Tuple[str, bool, str, Optional[str]]]]:
        """
        Post process all setups, generating one NC file per setup.
        
        Args:
            cam: CAM object
            setups: List of setups to post process
            component_id: Component ID (e.g., D1, P1)
            order_id: Order ID (e.g., IBUS366574)
            
        Returns:
            Tuple of (overall_success: bool, message: str, results: List[(setup_name, success, message, file_path)])
        """
        results = []
        successful_posts = 0
        output_files = []
        
        for setup in setups:
            setup_name = setup.name
            
            # Get next program number for this setup
            program_number = self.get_next_program_number()
            
            # Log progress (progress dialog shows this to user)
            self.logger.info(f'Post processing setup: {setup_name} (File: 1-{component_id}-{order_id}.nc)')
            
            # Post process this setup
            success, message, file_path = self.post_process_setup(cam, setup, program_number, component_id, order_id)
            
            results.append((setup_name, success, message, file_path))
            
            if success:
                successful_posts += 1
                output_files.append(file_path)
        
        # Build summary
        if successful_posts == len(setups):
            summary = f"All {len(setups)} setup(s) post processed successfully"
            overall_success = True
        elif successful_posts > 0:
            summary = f"{successful_posts}/{len(setups)} setup(s) post processed successfully"
            overall_success = True  # Partial success is okay
        else:
            summary = f"Post processing failed for all {len(setups)} setup(s)"
            overall_success = False
        
        return overall_success, summary, results
    
    def get_output_directory(self) -> str:
        """Get the configured output directory path."""
        return str(self.output_dir)
    
    def get_current_program_number(self) -> int:
        """
        Get the current (last used) program number without incrementing.
        
        Returns:
            Current program number or 1000 if not initialized
        """
        try:
            if self.counter_file.exists():
                with open(self.counter_file, 'r') as f:
                    return int(f.read().strip())
            return 1000  # Not yet initialized
        except:
            return 1000
