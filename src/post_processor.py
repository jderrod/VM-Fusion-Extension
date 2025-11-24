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
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
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
    
    def post_process_setup(self, cam: adsk.cam.CAM, setup: adsk.cam.Setup, program_number: int) -> Tuple[bool, str, Optional[str]]:
        """
        Post process a single setup to generate G-code.
        
        Args:
            cam: CAM object
            setup: Setup to post process
            program_number: Program number for the file (e.g., 1001)
            
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
            
            # Build output filename: program_number.nc (e.g., 1001.nc)
            output_filename = f"{program_number}.nc"
            output_path = self.output_dir / output_filename
            
            # Get post processor path
            # richauto.cps is in Fusion's post processor library
            post_config = cam.genericPostFolder + '/richauto.cps'
            
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
            
            # Verify file was created
            if output_path.exists():
                file_size = output_path.stat().st_size
                return True, f"Generated {output_filename} ({file_size} bytes)", str(output_path)
            else:
                return False, f"Post process completed but file not found: {output_filename}", None
            
        except Exception as e:
            return False, f"Post processing failed: {str(e)}", None
    
    def post_process_all_setups(self, cam: adsk.cam.CAM, setups: List[adsk.cam.Setup]) -> Tuple[bool, str, List[Tuple[str, bool, str, Optional[str]]]]:
        """
        Post process all setups, generating one NC file per setup.
        
        Args:
            cam: CAM object
            setups: List of setups to post process
            
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
            self.logger.info(f'Post processing setup: {setup_name} (Program: {program_number}.nc)')
            
            # Post process this setup
            success, message, file_path = self.post_process_setup(cam, setup, program_number)
            
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
