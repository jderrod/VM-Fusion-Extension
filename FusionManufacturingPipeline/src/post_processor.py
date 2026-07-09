"""
Post Processor for Fusion 360 Manufacturing Pipeline
Handles G-code generation and output file management
"""

import adsk.core
import adsk.fusion
import adsk.cam
import os
import re
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
    
    def post_process_all_setups(self, cam: adsk.cam.CAM, setups: List[adsk.cam.Setup], component_id: str, order_id: str,
                                  setup_sequence: Optional[List[str]] = None) -> Tuple[bool, str, List[Tuple[str, bool, str, Optional[str]]]]:
        """
        Post process setups individually and stitch them into a single .txt file.
        
        Each setup is posted separately via cam.postProcess(), then the individual
        .nc files are stitched together with M00 stops and "FLIP PART" comments
        between sections.  N-codes are renumbered continuously across the combined
        output so the machine sees one unbroken sequence (N10, N15, N20, ...).
        
        Args:
            cam: CAM object
            setups: List of setups available in the model
            component_id: Component ID (e.g., D1, P1)
            order_id: Order ID (e.g., IBUS366574)
            setup_sequence: Optional ordered list of setup names to post, allowing
                            repeats.  e.g. ["G57 Left", "G59 Right", "G59 Right"]
                            will post G59 Right twice with an M00 flip between.
                            If None, posts each setup with toolpaths once in model order.
            
        Returns:
            Tuple of (overall_success, message, results list)
        """
        try:
            cam_obj = adsk.cam.CAM.cast(cam)
            if not cam_obj:
                return False, 'Could not access CAM data', [('Setups', False, 'No CAM data', None)]
            
            # Build a lookup of setup objects by name
            setup_map = {s.name: s for s in setups}
            
            # Determine which setups have valid (unsuppressed) toolpaths
            setups_with_toolpaths = set()
            for setup in setups:
                for operation in setup.allOperations:
                    if operation.hasToolpath and not operation.isSuppressed:
                        setups_with_toolpaths.add(setup.name)
                        break
            
            # Build the posting sequence
            if setup_sequence:
                # Use the caller-provided sequence (may contain repeats)
                sequence = [name for name in setup_sequence if name in setups_with_toolpaths]
            else:
                # Default: post each setup with toolpaths once, in model order
                sequence = [s.name for s in setups if s.name in setups_with_toolpaths]
            
            if not sequence:
                return False, 'No setups have valid toolpaths to post', [('Setups', False, 'No valid toolpaths', None)]
            
            self.logger.info(f'Setup posting sequence: {sequence}')
            
            # Get post processor path
            if self.post_processor_path and os.path.exists(self.post_processor_path):
                post_config = self.post_processor_path
                self.logger.info(f'Using custom post processor: Anderson Stratos 2.cps')
            else:
                post_config = cam_obj.genericPostFolder + '/richauto.cps'
                self.logger.warning(f'Custom post not found, using richauto.cps')
            
            if not os.path.exists(post_config):
                return False, f'Post processor not found: {post_config}', [('Setups', False, 'Post processor not found', None)]
            
            # ── Phase 1: Post-process each entry in the sequence individually ──
            temp_files = []  # list of (setup_name, Path) for each posted file
            for idx, setup_name in enumerate(sequence):
                setup_obj = setup_map.get(setup_name)
                if not setup_obj:
                    self.logger.warning(f'Setup "{setup_name}" not found in model, skipping')
                    continue
                
                # Each individual post gets a unique program number so filenames don't collide
                prog_num = self.get_next_program_number()
                
                post_input = adsk.cam.PostProcessInput.create(
                    str(prog_num),
                    post_config,
                    str(self.output_dir),
                    adsk.cam.PostOutputUnitOptions.DocumentUnitsOutput
                )
                post_input.isOpenInEditor = False
                
                self.logger.info(f'Posting setup "{setup_name}" (sequence {idx+1}/{len(sequence)}) as {prog_num}.nc')
                cam_obj.postProcess(setup_obj, post_input)
                
                fusion_file = self.output_dir / f'{prog_num}.nc'
                if fusion_file.exists():
                    temp_files.append((setup_name, fusion_file))
                    self.logger.info(f'  -> {fusion_file.name} ({fusion_file.stat().st_size} bytes)')
                else:
                    self.logger.warning(f'  -> Expected {fusion_file.name} but file not found')
            
            if not temp_files:
                return False, 'No setup files were generated', [('Setups', False, 'No output files', None)]
            
            # Ensure G57 sections ALWAYS precede G59 sections in the combined file.
            # This applies whether or not a setup_sequence was provided.
            if setup_sequence:
                # Caller's order is intentional (e.g. stile flip sequences with
                # repeated setups). Use a STABLE sort keyed ONLY on G57-vs-G59 so
                # the relative order within each G-code group is preserved, while
                # still guaranteeing G57 comes before G59 when both are present.
                temp_files.sort(key=lambda x: 1 if 'G59' in x[0] else 0)
            else:
                # Default ordering: G57 before G59, then alphabetical by name.
                temp_files.sort(key=lambda x: ('G59' in x[0], x[0]))
            
            # ── Phase 2: Stitch individual files into one combined file ──
            combined_lines = self._stitch_setup_files(temp_files)
            
            # ── Phase 3: Renumber N-codes continuously ──
            combined_lines = self._renumber_ncodes(combined_lines)
            
            # ── Phase 4: Write final output as .txt ──
            output_filename = f'1-{component_id}-{order_id}.txt'
            output_path = self.output_dir / output_filename
            
            if output_path.exists():
                output_path.unlink()
            
            with open(output_path, 'w') as f:
                f.write('\n'.join(combined_lines) + '\n')
            
            # Clean up individual temp files
            for _, temp_path in temp_files:
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            
            file_size = output_path.stat().st_size
            self.logger.info(f'Successfully generated {output_filename} ({file_size} bytes) from {len(sequence)} section(s)')
            results = [('Setups', True, f'Generated {output_filename} ({file_size} bytes) from {len(sequence)} section(s)', str(output_path))]
            return True, f'Post processed {len(sequence)} section(s) to {output_filename}', results
            
        except Exception as e:
            error_msg = f'Post processing failed: {str(e)}'
            self.logger.error(error_msg)
            return False, error_msg, [('Setups', False, error_msg, None)]
    
    def _stitch_setup_files(self, temp_files: List[Tuple[str, Path]]) -> List[str]:
        """
        Stitch individual setup .nc files into one combined program.
        
        Structure of each individual file from the CPS post processor:
            %                       <- program start
            O####                   <- program number
            (header comments...)    <- machine info, tool table
            N10 ...                 <- G-code body
            ...
            M30                     <- program end
            %                       <- program end marker
        
        Combined output keeps the header from the FIRST file, strips
        headers/footers from subsequent files, and inserts M00 stops
        with flip comments between sections.
        """
        combined = []
        
        for file_idx, (setup_name, file_path) in enumerate(temp_files):
            with open(file_path, 'r') as f:
                lines = [line.rstrip() for line in f.readlines()]
            
            if file_idx == 0:
                # First file: keep everything EXCEPT the trailing M30 and %
                # Find the last M30 line and strip from there
                body = self._strip_footer(lines)
                combined.extend(body)
            else:
                # Subsequent files: insert M00 stop + flip comment, then
                # strip the header (everything up to first N-code line)
                # and strip the footer (M30, %)
                combined.append('M0')
                combined.append('')
                combined.append('(******************)')
                combined.append(f'(NEW SETUP, FLIP PART)')
                combined.append('(******************)')
                combined.append('')
                
                body = self._strip_header(lines)
                body = self._strip_footer(body)
                combined.extend(body)
        
        # Add program end
        combined.append('M30')
        combined.append('%')
        
        return combined
    
    def _strip_header(self, lines: List[str]) -> List[str]:
        """
        Strip the program header from an individual setup's .nc output.
        Removes everything before the first N-code line: the leading %,
        O#### program number, and all comment/header lines.
        
        Also strips repeated initialization blocks (G90 G94 G17 G49, G20/G21,
        M12, G28, M95, M92, G8) since these were already emitted by the first
        setup's header.
        """
        # Find first line starting with N (N-code)
        first_n = None
        for i, line in enumerate(lines):
            if re.match(r'^N\d+\s', line):
                first_n = i
                break
        
        if first_n is None:
            return lines  # No N-codes found, return as-is
        
        return lines[first_n:]
    
    def _strip_footer(self, lines: List[str]) -> List[str]:
        """
        Strip the program footer (M30 and trailing %) from the end of a file.
        """
        # Work backwards from the end
        end = len(lines)
        while end > 0 and lines[end - 1].strip() in ('', '%'):
            end -= 1
        # Check if last remaining line is M30
        if end > 0 and lines[end - 1].strip().startswith('M30'):
            end -= 1
        # Also strip any trailing blank lines and G-code cleanup before M30
        # (G28, G49, G8 P0 lines that are part of the program-end sequence)
        return lines[:end]
    
    def _renumber_ncodes(self, lines: List[str], start: int = 10, increment: int = 5) -> List[str]:
        """
        Renumber all N-code line numbers continuously across the combined file.
        Matches lines starting with N followed by digits (e.g., N10, N285)
        and replaces with a continuous sequence starting at `start`.
        """
        n_pattern = re.compile(r'^(N)\d+(\s)')
        current = start
        result = []
        for line in lines:
            if n_pattern.match(line):
                line = n_pattern.sub(f'N{current}\\2', line, count=1)
                current += increment
            result.append(line)
        return result
    
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
        except Exception:
            return 1000
