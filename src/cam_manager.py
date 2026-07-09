"""
CAM Manager for Fusion 360 Manufacturing Pipeline
Handles CAM workspace operations and toolpath regeneration
"""

import adsk.core
import adsk.fusion
import adsk.cam
import re
import time
from typing import List, Tuple, Optional


class CAMManager:
    """Manages CAM operations for Fusion 360 designs"""
    
    def __init__(self, app: adsk.core.Application, document: adsk.core.Document):
        """
        Initialize CAM manager.
        
        Args:
            app: Fusion Application object
            document: Document containing CAM data
        """
        self.app = app
        self.ui = app.userInterface
        self.document = document
        self.cam_product = None
        
        # Import logger
        from logger import get_logger
        self.logger = get_logger()
    
    def get_cam_product(self) -> Tuple[bool, str]:
        """
        Get the CAM product from the document, activating the Manufacturing
        workspace first to ensure design geometry changes are fully synced
        into CAM (mirrors clicking MANUFACTURE in the UI).
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Activate the Manufacturing (CAM) workspace to force Fusion to
            # reconcile any pending design changes into CAM operations.
            # Without this, generateAllToolpaths may use stale geometry.
            try:
                cam_workspace = self.ui.workspaces.itemById('CAMEnvironment')
                if cam_workspace:
                    cam_workspace.activate()
                    time.sleep(2)  # Let Fusion settle after workspace switch
                    self.logger.info('Activated Manufacturing workspace')
                else:
                    self.logger.warning('CAMEnvironment workspace not found, accessing CAM product directly')
            except Exception as ws_err:
                self.logger.warning(f'Failed to activate Manufacturing workspace: {ws_err}')
            
            # Get the CAM product from the document's products collection
            self.cam_product = self.document.products.itemByProductType('CAMProductType')
            
            if not self.cam_product:
                return False, 'No CAM data found in document. Please create CAM setups first in MANUFACTURE workspace.'
            
            return True, 'CAM product accessed'
            
        except Exception as e:
            return False, f'Failed to access CAM product: {str(e)}'
    
    def get_all_setups(self) -> List[adsk.cam.Setup]:
        """
        Get all CAM setups from the document.
        
        Returns:
            List of CAM Setup objects
        """
        try:
            if not self.cam_product:
                return []
            
            cam = adsk.cam.CAM.cast(self.cam_product)
            if not cam:
                return []
            
            setups = []
            for setup in cam.setups:
                setups.append(setup)
            
            return setups
            
        except Exception as e:
            self.logger.warning(f'Error getting setups: {e}')
            return []
    
    def get_setup_by_name(self, setup_name: str) -> Optional[adsk.cam.Setup]:
        """
        Get a specific CAM setup by name.
        
        Args:
            setup_name: Name of the setup to find
            
        Returns:
            Setup object or None if not found
        """
        try:
            if not self.cam_product:
                return None
            
            cam = adsk.cam.CAM.cast(self.cam_product)
            if not cam:
                return None
            
            for setup in cam.setups:
                if setup.name == setup_name:
                    return setup
            
            return None
            
        except Exception as e:
            self.logger.warning(f'Error finding setup "{setup_name}": {e}')
            return None
    
    def list_setup_names(self) -> List[str]:
        """
        Get names of all CAM setups.
        
        Returns:
            List of setup names
        """
        setups = self.get_all_setups()
        return [setup.name for setup in setups]
    
    def regenerate_all_toolpaths(self) -> Tuple[bool, str, List[Tuple[str, bool, str]]]:
        """
        Regenerate toolpaths for the entire Setups folder at once.
        Uses generateAllToolpaths to regenerate everything in one operation.
        
        Returns:
            Tuple of (success: bool, message: str, results: List[(setup_name, success, message)])
        """
        try:
            if not self.cam_product:
                return False, 'CAM product not initialized', []
            
            cam = adsk.cam.CAM.cast(self.cam_product)
            if not cam:
                return False, 'Could not access CAM data', []
            
            # Get all setups for reporting
            setups = self.get_all_setups()
            
            if not setups:
                return False, 'No CAM setups found in document', []
            
            self.logger.info(f'Regenerating ALL toolpaths for entire Setups folder ({len(setups)} setup(s))')
            
            # Generate ALL toolpaths at once for the entire Setups folder
            # This is more efficient and handles dependencies between setups
            future = cam.generateAllToolpaths(False)  # False = don't show progress dialog
            
            # Wait for completion with heavily throttled event pumping.
            # Each doEvents() call pumps Fusion's internal event queue, which triggers
            # PLM360 version reconciliation (WIPRequest7, getComponentProperties) for
            # all open cloud documents. High-version Dirty documents accumulate internal
            # state during this polling that eventually causes STACK_OVERFLOW crashes.
            # Using 1.5s sleep between doEvents() calls reduces polling rate by 15x
            # compared to 0.1s, significantly reducing PLM360 pressure and CPU usage.
            max_wait_seconds = 300  # 5-minute safety timeout
            start_time = time.time()
            while not future.isGenerationCompleted:
                adsk.doEvents()
                time.sleep(1.5)  # Throttle heavily to reduce CPU and PLM360 pressure
                if time.time() - start_time > max_wait_seconds:
                    self.logger.warning(f'Toolpath generation timed out after {max_wait_seconds}s')
                    break
            
            # Check if generation completed
            if not future.isGenerationCompleted:
                return False, f'Toolpath generation did not complete (timeout after {max_wait_seconds}s)', []
            
            elapsed = time.time() - start_time
            self.logger.info(f'generateAllToolpaths completed in {elapsed:.1f}s')
            
            # Check for operations that still lack toolpaths (e.g. freshly unsuppressed).
            # If any are found, generate them individually.
            ops_missing_toolpath = []
            for setup in setups:
                for operation in setup.allOperations:
                    if not operation.isSuppressed and not operation.hasToolpath:
                        ops_missing_toolpath.append((setup.name, operation))
            
            if ops_missing_toolpath:
                self.logger.info(f'{len(ops_missing_toolpath)} operation(s) still need toolpaths after generateAllToolpaths, generating individually...')
                for setup_name, operation in ops_missing_toolpath:
                    self.logger.info(f'  Generating toolpath for "{setup_name}" / "{operation.name}"')
                    try:
                        op_future = cam.generateToolpath(operation)
                        t0 = time.time()
                        while not op_future.isGenerationCompleted:
                            adsk.doEvents()
                            time.sleep(1.5)
                            if time.time() - t0 > 120:
                                self.logger.warning(f'  Toolpath generation timed out for "{operation.name}"')
                                break
                        if operation.hasToolpath:
                            self.logger.info(f'  "{setup_name}" / "{operation.name}": toolpath generated')
                        else:
                            self.logger.warning(f'  "{setup_name}" / "{operation.name}": still no toolpath after individual generation')
                    except Exception as e:
                        self.logger.warning(f'  Failed to generate toolpath for "{operation.name}": {e}')
            
            # Now check results for each setup
            results = []
            all_success = True
            total_operations_with_toolpaths = 0
            total_operations = 0
            
            for setup in setups:
                setup_name = setup.name
                operations_with_toolpaths = 0
                operations_total = 0
                warning_messages = []
                
                for operation in setup.allOperations:
                    op_name = operation.name
                    operations_total += 1
                    total_operations += 1
                    
                    # Check if operation is suppressed (skip it)
                    if operation.isSuppressed:
                        warning_messages.append(f"'{op_name}' is suppressed (skipped)")
                        continue
                    
                    # Check if operation has a toolpath
                    if operation.hasToolpath:
                        operations_with_toolpaths += 1
                        total_operations_with_toolpaths += 1
                    else:
                        warning_messages.append(f"'{op_name}' (no toolpath)")
                
                # Build result message for this setup
                if operations_with_toolpaths > 0:
                    msg = f'Regenerated {operations_with_toolpaths}/{operations_total} toolpaths'
                    results.append((setup_name, True, msg))
                    self.logger.info(f'{setup_name}: {msg}')
                elif operations_total == 0:
                    msg = 'No operations in setup'
                    results.append((setup_name, True, msg))
                    self.logger.info(f'{setup_name}: {msg}')
                else:
                    msg = f'No toolpaths generated ({operations_total} operations)'
                    results.append((setup_name, False, msg))
                    all_success = False
                    self.logger.warning(f'{setup_name}: {msg}')
            
            # Build summary message
            if total_operations_with_toolpaths > 0:
                message = f'Regenerated {total_operations_with_toolpaths}/{total_operations} toolpaths across {len(setups)} setup(s)'
                all_success = True  # Consider success if at least some toolpaths generated
            else:
                message = f'No toolpaths generated for any of {len(setups)} setup(s)'
            
            return all_success, message, results
            
        except Exception as e:
            return False, f'Failed to regenerate toolpaths: {str(e)}', []
    
    def unsuppress_all_door_operations(self) -> Tuple[bool, str]:
        """
        Unsuppress ALL operations in the door model's CAM setups.
        Must be called BEFORE toolpath regeneration so that all operations
        get toolpaths generated, regardless of previous suppression state.
        """
        try:
            cam = adsk.cam.CAM.cast(self.cam_product)
            if not cam:
                return False, 'Could not access CAM data'
            
            unsuppressed = []
            for setup in cam.setups:
                for operation in setup.allOperations:
                    if operation.isSuppressed:
                        operation.isSuppressed = False
                        unsuppressed.append(f'"{setup.name}" / "{operation.name}"')
            
            if unsuppressed:
                for u in unsuppressed:
                    self.logger.info(f'unsuppress_all_door_operations: Unsuppressed {u}')
                return True, f'Unsuppressed {len(unsuppressed)} operation(s)'
            else:
                return True, 'All operations already active'
                
        except Exception as e:
            return False, f'Failed to unsuppress door operations: {str(e)}'
    
    def suppress_door_toolpaths(self, param_mgr) -> Tuple[bool, str]:
        """
        Selectively suppress/unsuppress door toolpath operations based on
        the model's computed rabbeting and notching parameters.
        
        Must be called AFTER input parameters are applied and toolpaths are
        regenerated, but BEFORE post-processing.
        
        The door model has 8 setups, each containing 3 toolpaths:
          Setup 1 - G57: Left Interior Rabbet, Left Bottom Notch, Left Top Notch
          Setup 2 - G59: Left Interior Rabbet, Left Bottom Notch, Left Top Notch
          Setup 3 - G57: Left Exterior Rabbet, Left Bottom Notch, Left Top Notch
          Setup 4 - G59: Left Exterior Rabbet, Left Bottom Notch, Left Top Notch
          Setup 5 - G57: Right Interior Rabbet, Right Bottom Notch, Right Top Notch
          Setup 6 - G59: Right Interior Rabbet, Right Bottom Notch, Right Top Notch
          Setup 7 - G57: Right Exterior Rabbet, Right Bottom Notch, Right Top Notch
          Setup 8 - G59: Right Exterior Rabbet, Right Bottom Notch, Right Top Notch
        
        Within each setup, individual toolpaths are suppressed based on feature flags:
          - Rabbet toolpath: active if the corresponding rabbeting parameter is true
          - Bottom Notch: active if bottom_left_notching (left setups) or bottom_right_notching (right setups)
          - Top Notch: active if top_left_notching (left setups) or top_right_notching (right setups)
        
        Args:
            param_mgr: ParameterManager instance for reading model output parameters
            
        Returns:
            Tuple of (success, message)
        """
        try:
            def read_bool_param(name: str) -> bool:
                param = param_mgr.user_parameters.itemByName(name)
                if param is None:
                    self.logger.warning(f'suppress_door_toolpaths: parameter "{name}" not found in model')
                    return False
                try:
                    numeric_val = param.value
                    self.logger.info(f'suppress_door_toolpaths: "{name}" value={numeric_val}')
                    return numeric_val != 0
                except Exception as e:
                    self.logger.warning(f'suppress_door_toolpaths: error reading "{name}": {e}')
                    return False
            
            left_int_rabbet = read_bool_param('left_interior_rabbeting')
            left_ext_rabbet = read_bool_param('left_exterior_rabbeting')
            right_int_rabbet = read_bool_param('right_interior_rabbeting')
            right_ext_rabbet = read_bool_param('right_exterior_rabbeting')
            bottom_left_notch = read_bool_param('bottom_left_notching')
            bottom_right_notch = read_bool_param('bottom_right_notching')
            top_left_notch = read_bool_param('top_left_notching')
            top_right_notch = read_bool_param('top_right_notching')
            
            # Build the desired active state for each (setup_name, operation_name) pair.
            # True = operation should be ACTIVE (not suppressed).
            # Rabbet toolpaths are active based on the matching rabbeting flag.
            # Notch toolpaths are active based on the side (left/right) notching flag.
            op_active = {
                # Setup 1 - G57: Left Interior
                ('Setup 1 - G57', 'Left Interior Rabbet'):  left_int_rabbet,
                ('Setup 1 - G57', 'Left Bottom Notch'):     bottom_left_notch,
                ('Setup 1 - G57', 'Left Top Notch'):        top_left_notch,
                # Setup 2 - G59: Left Interior
                ('Setup 2 - G59', 'Left Interior Rabbet'):  left_int_rabbet,
                ('Setup 2 - G59', 'Left Bottom Notch'):     bottom_left_notch,
                ('Setup 2 - G59', 'Left Top Notch'):        top_left_notch,
                # Setup 3 - G57: Left Exterior
                ('Setup 3 - G57', 'Left Exterior Rabbet'):  left_ext_rabbet,
                ('Setup 3 - G57', 'Left Bottom Notch'):     bottom_left_notch,
                ('Setup 3 - G57', 'Left Top Notch'):        top_left_notch,
                # Setup 4 - G59: Left Exterior
                ('Setup 4 - G59', 'Left Exterior Rabbet'):  left_ext_rabbet,
                ('Setup 4 - G59', 'Left Bottom Notch'):     bottom_left_notch,
                ('Setup 4 - G59', 'Left Top Notch'):        top_left_notch,
                # Setup 5 - G57: Right Interior
                ('Setup 5 - G57', 'Right Interior Rabbet'): right_int_rabbet,
                ('Setup 5 - G57', 'Right Bottom Notch'):    bottom_right_notch,
                ('Setup 5 - G57', 'Right Top Notch'):       top_right_notch,
                # Setup 6 - G59: Right Interior
                ('Setup 6 - G59', 'Right Interior Rabbet'): right_int_rabbet,
                ('Setup 6 - G59', 'Right Bottom Notch'):    bottom_right_notch,
                ('Setup 6 - G59', 'Right Top Notch'):       top_right_notch,
                # Setup 7 - G57: Right Exterior
                ('Setup 7 - G57', 'Right Exterior Rabbet'): right_ext_rabbet,
                ('Setup 7 - G57', 'Right Bottom Notch'):    bottom_right_notch,
                ('Setup 7 - G57', 'Right Top Notch'):       top_right_notch,
                # Setup 8 - G59: Right Exterior
                ('Setup 8 - G59', 'Right Exterior Rabbet'): right_ext_rabbet,
                ('Setup 8 - G59', 'Right Bottom Notch'):    bottom_right_notch,
                ('Setup 8 - G59', 'Right Top Notch'):       top_right_notch,
            }
            
            self.logger.info(f'suppress_door_toolpaths: desired active state: {op_active}')
            
            cam = adsk.cam.CAM.cast(self.cam_product)
            if not cam:
                return False, 'Could not access CAM data'
            
            # Log actual setup/operation names for diagnostics
            for setup in cam.setups:
                op_names = [op.name for op in setup.allOperations]
                self.logger.info(f'suppress_door_toolpaths: setup "{setup.name}" operations: {op_names}')
            
            changes = []
            for setup in cam.setups:
                setup_name = setup.name.strip()
                for operation in setup.allOperations:
                    op_name = operation.name.strip()
                    key = (setup_name, op_name)
                    if key in op_active:
                        should_be_active = op_active[key]
                        currently_suppressed = operation.isSuppressed
                        
                        if should_be_active and currently_suppressed:
                            operation.isSuppressed = False
                            changes.append(f'Unsuppressed "{setup_name}" / "{op_name}"')
                        elif not should_be_active and not currently_suppressed:
                            operation.isSuppressed = True
                            changes.append(f'Suppressed "{setup_name}" / "{op_name}"')
            
            if changes:
                for c in changes:
                    self.logger.info(f'suppress_door_toolpaths: {c}')
                return True, f'Updated {len(changes)} toolpath(s): {"; ".join(changes)}'
            else:
                self.logger.info('suppress_door_toolpaths: no changes needed')
                return True, 'No toolpath suppression changes needed'
                
        except Exception as e:
            return False, f'Failed to suppress door toolpaths: {str(e)}'
    
    def unsuppress_all_panel_operations(self) -> Tuple[bool, str]:
        """
        Unsuppress ALL operations in the panel model's CAM setups.
        Must be called BEFORE toolpath regeneration so that all operations
        get toolpaths generated, regardless of previous suppression state.
        """
        try:
            cam = adsk.cam.CAM.cast(self.cam_product)
            if not cam:
                return False, 'Could not access CAM data'
            
            unsuppressed = []
            for setup in cam.setups:
                for operation in setup.allOperations:
                    if operation.isSuppressed:
                        operation.isSuppressed = False
                        unsuppressed.append(f'"{setup.name}" / "{operation.name}"')
            
            if unsuppressed:
                for u in unsuppressed:
                    self.logger.info(f'unsuppress_all_panel_operations: Unsuppressed {u}')
                return True, f'Unsuppressed {len(unsuppressed)} operation(s)'
            else:
                return True, 'All operations already active'
                
        except Exception as e:
            return False, f'Failed to unsuppress panel operations: {str(e)}'
    
    def suppress_panel_toolpaths(self, param_mgr) -> Tuple[bool, str]:
        """
        Selectively suppress/unsuppress panel toolpath operations based on
        the model's computed notching and cutout parameters.
        
        Must be called AFTER input parameters are applied and toolpaths are
        regenerated, but BEFORE post-processing.
        
        Panel setups each contain up to 6 operations:
          - Front Bottom Notch: active if notching_front_edge_bottom != 0
          - Front Top Notch:    active if notching_front_edge_top != 0
          - Back Bottom Notch:  active if notching_back_edge_bottom != 0
          - Back Top Notch:     active if notching_back_edge_top != 0
          - Cutout A:           active if cutout_A_width > 0 and cutout_A_height > 0
          - Cutout B:           active if cutout_B_width > 0 and cutout_B_height > 0
        
        Args:
            param_mgr: ParameterManager instance for reading model output parameters
            
        Returns:
            Tuple of (success, message)
        """
        try:
            def read_bool_param(name: str) -> bool:
                param = param_mgr.user_parameters.itemByName(name)
                if param is None:
                    self.logger.warning(f'suppress_panel_toolpaths: parameter "{name}" not found in model')
                    return False
                try:
                    numeric_val = param.value
                    self.logger.info(f'suppress_panel_toolpaths: "{name}" value={numeric_val}')
                    return numeric_val != 0
                except Exception as e:
                    self.logger.warning(f'suppress_panel_toolpaths: error reading "{name}": {e}')
                    return False
            
            def read_num_param(name: str) -> float:
                param = param_mgr.user_parameters.itemByName(name)
                if param is None:
                    self.logger.warning(f'suppress_panel_toolpaths: parameter "{name}" not found in model')
                    return 0.0
                try:
                    val = param.value
                    self.logger.info(f'suppress_panel_toolpaths: "{name}" value={val}')
                    return float(val)
                except Exception as e:
                    self.logger.warning(f'suppress_panel_toolpaths: error reading "{name}": {e}')
                    return 0.0
            
            front_bottom_notch = read_bool_param('notching_front_edge_bottom')
            front_top_notch = read_bool_param('notching_front_edge_top')
            back_bottom_notch = read_bool_param('notching_back_edge_bottom')
            back_top_notch = read_bool_param('notching_back_edge_top')
            
            cutout_a_width = read_num_param('cutout_A_width')
            cutout_a_height = read_num_param('cutout_A_height')
            cutout_b_width = read_num_param('cutout_B_width')
            cutout_b_height = read_num_param('cutout_B_height')
            
            cutout_a_active = cutout_a_width > 0 and cutout_a_height > 0
            cutout_b_active = cutout_b_width > 0 and cutout_b_height > 0
            
            # Cross-reference: check the cutout TEXT parameters (cutout_A, cutout_B)
            # to detect when a cutout was applied but derived dimensions failed to
            # update. The text params are the authoritative source set by
            # _apply_cutout_parameters; derived width/height may lag behind.
            def read_text_param(name: str) -> str:
                param = param_mgr.user_parameters.itemByName(name)
                if param is None:
                    return ''
                try:
                    expr = param.expression
                    # Text param expressions are wrapped in single quotes: 'B-354'
                    if expr.startswith("'") and expr.endswith("'"):
                        return expr[1:-1].strip()
                    return expr.strip()
                except Exception:
                    return ''
            
            cutout_a_text = read_text_param('cutout_A')
            cutout_b_text = read_text_param('cutout_B')
            
            if cutout_a_text and not cutout_a_active:
                self.logger.warning(
                    f'suppress_panel_toolpaths: cutout_A text="{cutout_a_text}" but '
                    f'derived dimensions are zero (w={cutout_a_width}, h={cutout_a_height}) '
                    f'— forcing cutout_A ACTIVE to prevent incorrect suppression')
                cutout_a_active = True
            if cutout_b_text and not cutout_b_active:
                self.logger.warning(
                    f'suppress_panel_toolpaths: cutout_B text="{cutout_b_text}" but '
                    f'derived dimensions are zero (w={cutout_b_width}, h={cutout_b_height}) '
                    f'— forcing cutout_B ACTIVE to prevent incorrect suppression')
                cutout_b_active = True
            
            self.logger.info(f'suppress_panel_toolpaths: cutout_A active={cutout_a_active} (w={cutout_a_width}, h={cutout_a_height}, text="{cutout_a_text}")')
            self.logger.info(f'suppress_panel_toolpaths: cutout_B active={cutout_b_active} (w={cutout_b_width}, h={cutout_b_height}, text="{cutout_b_text}")')
            
            # Map operation names (normalized to lowercase, no trailing
            # " (N)" copy-suffix) to their active state.  These operation
            # names appear in BOTH panel setups (Setup Back Bottom Corner
            # G58 and Setup Back Top Corner G58).  The second setup's ops
            # carry a " (2)" suffix added by Fusion, e.g. "Cutout A (2)".
            def _normalize_op_name(raw: str) -> str:
                """Strip whitespace, remove trailing ' (N)' copy-suffix, lowercase."""
                name = raw.strip()
                name = re.sub(r'\s+\(\d+\)$', '', name)  # remove " (2)" etc.
                return name.strip().lower()

            op_active_by_name = {
                'front bottom notch': front_bottom_notch,
                'front top notch':    front_top_notch,
                'back bottom notch':  back_bottom_notch,
                'back top notch':     back_top_notch,
                'cutout a':           cutout_a_active,
                'cutout b':           cutout_b_active,
            }
            
            self.logger.info(f'suppress_panel_toolpaths: desired active state: {op_active_by_name}')
            
            cam = adsk.cam.CAM.cast(self.cam_product)
            if not cam:
                return False, 'Could not access CAM data'
            
            # Log actual setup/operation names for diagnostics
            for setup in cam.setups:
                op_names = [op.name for op in setup.allOperations]
                self.logger.info(f'suppress_panel_toolpaths: setup "{setup.name}" operations: {op_names}')
            
            changes = []
            for setup in cam.setups:
                for operation in setup.allOperations:
                    op_name_raw = operation.name.strip()
                    op_name_norm = _normalize_op_name(op_name_raw)
                    currently_suppressed = operation.isSuppressed
                    
                    if op_name_norm in op_active_by_name:
                        # Known operation: set based on parameter state
                        should_be_active = op_active_by_name[op_name_norm]
                    else:
                        # Unknown operation: suppress by default
                        should_be_active = False
                        self.logger.info(f'suppress_panel_toolpaths: unknown op "{op_name_raw}" (normalized: "{op_name_norm}") in "{setup.name.strip()}" -> suppressing')
                    
                    if should_be_active and currently_suppressed:
                        operation.isSuppressed = False
                        changes.append(f'Unsuppressed "{setup.name.strip()}" / "{op_name_raw}"')
                    elif not should_be_active and not currently_suppressed:
                        operation.isSuppressed = True
                        changes.append(f'Suppressed "{setup.name.strip()}" / "{op_name_raw}"')
            
            if changes:
                for c in changes:
                    self.logger.info(f'suppress_panel_toolpaths: {c}')
                return True, f'Updated {len(changes)} toolpath(s): {"; ".join(changes)}'
            else:
                self.logger.info('suppress_panel_toolpaths: no changes needed')
                return True, 'No toolpath suppression changes needed'
                
        except Exception as e:
            return False, f'Failed to suppress panel toolpaths: {str(e)}'
    
    def get_setup_info(self, setup_name: str) -> Optional[dict]:
        """
        Get detailed information about a setup.
        
        Args:
            setup_name: Name of the setup
            
        Returns:
            Dictionary with setup details or None
        """
        setup = self.get_setup_by_name(setup_name)
        
        if not setup:
            return None
        
        try:
            return {
                'name': setup.name,
                'operation_count': setup.allOperations.count,
                'is_suppressed': setup.isSuppressed
            }
        except Exception as e:
            self.logger.warning(f'Error getting setup info for "{setup_name}": {e}')
            return {'name': setup_name, 'error': str(e)}
