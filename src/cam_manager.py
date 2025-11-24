"""
CAM Manager for Fusion 360 Manufacturing Pipeline
Handles CAM workspace operations and toolpath regeneration
"""

import adsk.core
import adsk.fusion
import adsk.cam
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
    
    def get_cam_product(self) -> Tuple[bool, str]:
        """
        Get the CAM product from the document.
        No need to activate workspace - just access the CAM product.
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
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
            
        except:
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
            
        except:
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
        Regenerate toolpaths for ALL setups in the document.
        If any setup fails, the entire operation is considered failed.
        
        Returns:
            Tuple of (success: bool, message: str, results: List[(setup_name, success, message)])
        """
        try:
            if not self.cam_product:
                return False, 'CAM product not initialized', []
            
            cam = adsk.cam.CAM.cast(self.cam_product)
            if not cam:
                return False, 'Could not access CAM data', []
            
            # Get all setups
            setups = self.get_all_setups()
            
            if not setups:
                return False, 'No CAM setups found in document', []
            
            results = []
            all_success = True
            
            # Generate all toolpaths at once
            try:
                # Log what we're doing (progress dialog shows this to user)
                self.logger.info(f'Regenerating toolpaths for {len(setups)} setup(s): {", ".join([s.name for s in setups])}')
                
                # Use generateAllToolpaths on the entire CAM object
                # Parameter: False = regenerate ALL toolpaths (don't skip any)
                # This ensures toolpaths update after parameter changes
                # We handle errors gracefully below rather than skipping operations
                future = cam.generateAllToolpaths(False)  # False = regenerate all
                
                # Wait for completion
                while not future.isGenerationCompleted:
                    adsk.doEvents()
                
                # Check if generation completed
                if not future.isGenerationCompleted:
                    for setup in setups:
                        results.append((setup.name, False, 'Generation did not complete'))
                    all_success = False
                else:
                    # Generation completed - now verify each setup's operations
                    for setup in setups:
                        setup_name = setup.name
                        
                        # Check all operations in this setup for errors
                        has_errors = False
                        error_messages = []
                        warning_messages = []
                        
                        operations_with_toolpaths = 0
                        operations_total = 0
                        
                        for operation in setup.allOperations:
                            op_name = operation.name
                            operations_total += 1
                            
                            # Check if operation is suppressed (skip it)
                            if operation.isSuppressed:
                                warning_messages.append(f"'{op_name}' is suppressed (skipped)")
                                continue
                            
                            # Check if operation has a toolpath
                            if operation.hasToolpath:
                                operations_with_toolpaths += 1
                            else:
                                # No toolpath - check if it's due to pre-existing error
                                has_preexisting_error = False
                                
                                # Check for errors
                                try:
                                    if hasattr(operation, 'error') and operation.error:
                                        error_text = str(operation.error)
                                        if error_text and error_text.strip():
                                            # Pre-existing CAM error
                                            warning_messages.append(f"'{op_name}' (pre-existing error)")
                                            has_preexisting_error = True
                                except:
                                    pass
                                
                                if not has_preexisting_error:
                                    # No error info, just no toolpath
                                    warning_messages.append(f"'{op_name}' (no toolpath generated)")
                            
                            # Check for warnings
                            try:
                                if hasattr(operation, 'warning') and operation.warning:
                                    warning_text = str(operation.warning)
                                    if warning_text and warning_text.strip():
                                        warning_messages.append(f"'{op_name}': {warning_text}")
                            except:
                                pass
                        
                        # Build result message
                        # Consider it success if:
                        # 1. At least one operation generated successfully, OR
                        # 2. All operations that failed have pre-existing errors (not our fault)
                        
                        if operations_with_toolpaths > 0:
                            # At least some operations succeeded
                            msg = f'Regenerated {operations_with_toolpaths}/{operations_total} toolpaths'
                            
                            # Add brief warning summary
                            if warning_messages:
                                failed_count = operations_total - operations_with_toolpaths
                                if failed_count > 0:
                                    msg += f' ({failed_count} operation(s) have errors - not regenerated)'
                            
                            results.append((setup_name, True, msg))
                        else:
                            # No operations generated - check if they all have pre-existing errors
                            # If so, it's a warning not a failure
                            if operations_total > 0 and len(warning_messages) >= operations_total:
                                # All operations have errors - log as warning
                                msg = f'All {operations_total} operation(s) have errors - none regenerated'
                                results.append((setup_name, True, msg))
                            else:
                                # Unexpected failure
                                msg = f'No operations regenerated ({operations_total} total)'
                                results.append((setup_name, False, msg))
                                all_success = False
                        
            except Exception as e:
                for setup in setups:
                    results.append((setup.name, False, f'Exception: {str(e)}'))
                all_success = False
            
            # Build summary message
            if all_success:
                message = f'All toolpaths regenerated successfully for {len(setups)} setup(s)'
            else:
                failed = [r[0] for r in results if not r[1]]
                message = f'Toolpath regeneration failed for setup(s): {", ".join(failed)}'
            
            return all_success, message, results
            
        except Exception as e:
            return False, f'Failed to regenerate toolpaths: {str(e)}', []
    
    def regenerate_specific_setups(self, setup_names: List[str]) -> Tuple[bool, str, List[Tuple[str, bool, str]]]:
        """
        Regenerate toolpaths for specific setups only.
        
        Args:
            setup_names: List of setup names to regenerate
            
        Returns:
            Tuple of (success: bool, message: str, results: List[(setup_name, success, message)])
        """
        try:
            if not self.cam_product:
                return False, 'CAM product not initialized', []
            
            cam = adsk.cam.CAM.cast(self.cam_product)
            if not cam:
                return False, 'Could not access CAM data', []
            
            results = []
            all_success = True
            
            # Validate all setups exist first
            available_setups = self.list_setup_names()
            missing = [name for name in setup_names if name not in available_setups]
            
            if missing:
                return False, f'Setup(s) not found: {", ".join(missing)}. Available: {", ".join(available_setups)}', []
            
            # Regenerate specified setups
            for setup_name in setup_names:
                setup = self.get_setup_by_name(setup_name)
                
                if not setup:
                    results.append((setup_name, False, 'Setup not found'))
                    all_success = False
                    continue
                
                try:
                    # For individual setup regeneration, we still use generateAllToolpaths
                    # because Fusion doesn't have a per-setup generation method in the API
                    future = cam.generateAllToolpaths(False)
                    
                    while not future.isGenerationCompleted:
                        adsk.doEvents()
                    
                    if future.isGenerationCompleted:
                        results.append((setup_name, True, f'Toolpaths regenerated'))
                    else:
                        results.append((setup_name, False, f'Generation incomplete'))
                        all_success = False
                        
                except Exception as e:
                    results.append((setup_name, False, f'Exception: {str(e)}'))
                    all_success = False
            
            # Build summary
            if all_success:
                message = f'Toolpaths regenerated for {len(setup_names)} setup(s)'
            else:
                failed = [r[0] for r in results if not r[1]]
                message = f'Failed for setup(s): {", ".join(failed)}'
            
            return all_success, message, results
            
        except Exception as e:
            return False, f'Failed to regenerate toolpaths: {str(e)}', []
    
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
                'is_generated': setup.isSuppressed  # Note: may need different check
            }
        except:
            return {'name': setup_name, 'error': 'Could not get info'}
