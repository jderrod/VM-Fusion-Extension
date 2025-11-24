"""
Order Processor for Fusion 360 Manufacturing Pipeline
Handles loading orders, opening documents, and coordinating operations
"""

import adsk.core
import adsk.fusion
import json
import os
from typing import Dict, List, Tuple, Optional
from pathlib import Path

from parameter_manager import ParameterManager
from cam_manager import CAMManager
from post_processor import PostProcessor
from model_exporter import ModelExporter
from parameter_exporter import ParameterExporter
from model_manager import ModelManager
from logger import get_logger


class OrderProcessor:
    """Processes manufacturing orders from JSON files"""
    
    def __init__(self, app: adsk.core.Application, inputs_folder: str = None):
        """
        Initialize order processor.
        
        Args:
            app: Fusion Application object
            inputs_folder: Optional path to inputs folder for persistent models
        """
        self.app = app
        self.ui = app.userInterface
        self.logger = get_logger()
        self.model_manager = ModelManager(app, inputs_folder)
    
    def load_order_file(self, file_path: str) -> Optional[Dict]:
        """
        Load and parse order JSON file.
        
        Args:
            file_path: Path to JSON order file
            
        Returns:
            Parsed order dictionary or None on error
        """
        try:
            with open(file_path, 'r') as f:
                order = json.load(f)
            return order
        except Exception as e:
            self.ui.messageBox(f'Failed to load order file:\n{str(e)}', 'Error')
            return None
    
    def open_document(self, file_path: str) -> Tuple[bool, Optional[adsk.core.Document]]:
        """
        Open a Fusion 360 document. If a document with matching name is already open, uses that.
        
        Args:
            file_path: Path to .f3d or cloud document, or just filename
            
        Returns:
            Tuple of (success: bool, document: Document or None)
        """
        try:
            # Extract just the filename from path
            file_name = os.path.basename(file_path)
            
            # Check if a document with this name is already open
            self.logger.info(f'Looking for open document: {file_name}')
            for doc in self.app.documents:
                if doc.name == file_name or doc.name == file_name.replace('.f3d', ''):
                    self.logger.info(f'Found already open document: {doc.name}')
                    self.ui.messageBox(
                        f'Using currently open document:\n{doc.name}',
                        'Document Found',
                        adsk.core.MessageBoxButtonTypes.OKButtonType,
                        adsk.core.MessageBoxIconTypes.InformationIconType
                    )
                    return True, doc
            
            # Document not open, try to open it
            self.logger.info(f'Document not open, attempting to open: {file_path}')
            
            # Check if file exists
            if not os.path.exists(file_path):
                self.logger.error(f'File not found: {file_path}')
                return False, None
            
            # Use importManager to open local .f3d files
            import_manager = self.app.importManager
            import_options = import_manager.createFusionArchiveImportOptions(file_path)
            doc = import_manager.importToNewDocument(import_options)
            
            if not doc:
                return False, None
            
            self.logger.info(f'Successfully opened document: {doc.name}')
            return True, doc
            
        except Exception as e:
            self.logger.exception('Failed to open document')
            self.ui.messageBox(f'Failed to open document:\n{file_path}\n\n{str(e)}', 'Error')
            return False, None
    
    def process_order(self, order_file_path: str) -> Tuple[bool, str]:
        """
        Process a complete manufacturing order.
        
        Args:
            order_file_path: Path to order JSON file
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Load order
            self.logger.info(f'Loading order from: {order_file_path}')
            order = self.load_order_file(order_file_path)
            if not order:
                self.logger.error('Failed to load order file')
                return False, 'Failed to load order file'
            
            order_id = order.get('orderId', 'unknown')
            components = order.get('components', [])
            
            self.logger.info(f'Processing order: {order_id} with {len(components)} component(s)')
            
            if not components:
                return False, 'No components found in order'
            
            results = []
            
            # Process each component
            for idx, component in enumerate(components):
                comp_result = self.process_component(component, idx + 1, len(components))
                results.append(comp_result)
            
            # Summary
            success_count = sum(1 for r in results if r[0])
            total_count = len(results)
            
            if success_count == total_count:
                # All succeeded
                self.ui.messageBox(
                    f'✓ Order Processing Complete!\n\nOrder {order_id}\n{total_count} component(s) processed successfully',
                    'Success',
                    adsk.core.MessageBoxButtonTypes.OKButtonType,
                    adsk.core.MessageBoxIconTypes.InformationIconType
                )
                
                message = f'Order {order_id} completed successfully!\n\n'
                message += f'Processed {total_count} component(s)'
                return True, message
            elif success_count > 0:
                # Partial success
                self.ui.messageBox(
                    f'Order {order_id} partially completed.\n\n{success_count}/{total_count} components successful',
                    'Partial Success',
                    adsk.core.MessageBoxButtonTypes.OKButtonType,
                    adsk.core.MessageBoxIconTypes.WarningIconType
                )
                
                message = f'Order {order_id} partially completed.\n\n'
                message += f'{success_count}/{total_count} components successful\n\n'
                message += 'Failed components:\n'
                for i, (success, msg) in enumerate(results):
                    if not success:
                        comp_id = components[i].get('componentId', f'Component {i+1}')
                        message += f'  {comp_id}: {msg}\n'
                return False, message
            else:
                # All failed
                self.ui.messageBox(
                    f'Order {order_id} failed.\n\n0/{total_count} components successful',
                    'Error',
                    adsk.core.MessageBoxButtonTypes.OKButtonType,
                    adsk.core.MessageBoxIconTypes.CriticalIconType
                )
                
                message = f'Order {order_id} failed.\n\n'
                message += f'0/{total_count} components successful\n\n'
                message += 'Failed components:\n'
                for i, (success, msg) in enumerate(results):
                    comp_id = components[i].get('componentId', f'Component {i+1}')
                    message += f'  {comp_id}: {msg}\n'
                return False, message
            
        except Exception as e:
            return False, f'Order processing failed: {str(e)}'
    
    def process_component(self, component: Dict, comp_num: int, total_comps: int) -> Tuple[bool, str]:
        """
        Process a single component from the order.
        
        Args:
            component: Component dictionary from order
            comp_num: Component number (1-indexed)
            total_comps: Total number of components
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            comp_id = component.get('componentId', f'Component{comp_num}')
            fusion_file = component.get('fusionModelPath', '')
            parameters = component.get('parameters', {})
            
            self.logger.info(f'Processing component {comp_num}/{total_comps}: {comp_id}')
            self.logger.info(f'  Fusion file: {fusion_file}')
            self.logger.info(f'  Parameters to apply: {len(parameters)}')
            
            # Validate component data
            if not fusion_file:
                return False, f'{comp_id}: No fusionFile specified'
            
            if not parameters:
                return False, f'{comp_id}: No parameters specified'
            
            # Show progress
            self.ui.messageBox(
                f'Processing component {comp_num} of {total_comps}:\n{comp_id}',
                'Processing',
                adsk.core.MessageBoxButtonTypes.OKButtonType,
                adsk.core.MessageBoxIconTypes.InformationIconType
            )
            
            # Open the document
            success, doc = self.open_document(fusion_file)
            if not success:
                return False, f'{comp_id}: Failed to open document: {fusion_file}'
            
            # Get the design
            design = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
            if not design:
                return False, f'{comp_id}: No design found in document'
            
            # Apply parameters
            self.logger.info(f'Applying parameters to {comp_id}')
            param_mgr = ParameterManager(design)
            results = param_mgr.update_parameters_batch(parameters)
            
            # Log each parameter update
            for param_name, success, msg in results:
                if success:
                    self.logger.info(f'  ✓ {msg}')
                else:
                    self.logger.error(f'  ✗ {msg}')
            
            # Check results
            failed_params = [r for r in results if not r[1]]
            if failed_params:
                error_msg = f'{comp_id}: Some parameters failed to update:\n'
                for param_name, success, msg in failed_params:
                    error_msg += f'  {msg}\n'
                return False, error_msg
            
            # Success! Parameters updated
            success_msg = f'{comp_id}: Successfully updated {len(parameters)} parameter(s)'
            
            # Show detailed results
            details = '\n'.join([f'  {msg}' for _, _, msg in results])
            self.ui.messageBox(
                f'{success_msg}\n\n{details}',
                'Parameters Updated',
                adsk.core.MessageBoxButtonTypes.OKButtonType,
                adsk.core.MessageBoxIconTypes.InformationIconType
            )
            
            self.logger.info(f'{comp_id}: Parameter updates complete, exporting 3D model')
            
            # Phase 2.5: Export 3D model with applied parameters
            # Export directory: same as NC Programs but in Models subfolder
            models_output_dir = r'C:\Users\james.derrod\OneDrive - Bobrick Washroom Equipment\Documents\Fusion 360\Models'
            model_exporter = ModelExporter(self.app, models_output_dir)
            
            # Export as STEP (good for CAD) - can change to 'stl', 'iges', or 'sat'
            export_success, export_msg, export_path = model_exporter.export_model(design, comp_id, format='step')
            
            if export_success:
                self.logger.info(f'{comp_id}: Model exported: {export_msg}')
            else:
                self.logger.warning(f'{comp_id}: Model export failed: {export_msg}')
                # Don't fail the entire component if export fails - just warn
            
            # Phase 2.6: Export parameters to CSV
            # Export directory: same as Models directory
            params_output_dir = r'C:\Users\james.derrod\OneDrive - Bobrick Washroom Equipment\Documents\Fusion 360\Parameters'
            param_exporter = ParameterExporter(self.app, params_output_dir)
            
            # Export all parameters (user + model parameters)
            param_export_success, param_export_msg, param_export_path = param_exporter.export_all_parameters(design, comp_id)
            
            if param_export_success:
                self.logger.info(f'{comp_id}: Parameters exported: {param_export_msg}')
            else:
                self.logger.warning(f'{comp_id}: Parameter export failed: {param_export_msg}')
                # Don't fail the entire component if export fails - just warn
            
            self.logger.info(f'{comp_id}: Starting CAM regeneration')
            
            # Phase 3: Regenerate CAM toolpaths
            cam_mgr = CAMManager(self.app, doc)
            
            # Get CAM product (no need to activate workspace)
            self.logger.info(f'{comp_id}: Accessing CAM product')
            cam_success, cam_msg = cam_mgr.get_cam_product()
            
            if not cam_success:
                self.logger.error(f'{comp_id}: {cam_msg}')
                return False, f'{comp_id}: CAM access failed: {cam_msg}'
            
            self.logger.info(f'{comp_id}: {cam_msg}')
            
            # List available setups
            setup_names = cam_mgr.list_setup_names()
            self.logger.info(f'{comp_id}: Found {len(setup_names)} CAM setup(s): {", ".join(setup_names)}')
            
            if not setup_names:
                return False, f'{comp_id}: No CAM setups found in document'
            
            # Show setups found
            self.ui.messageBox(
                f'Found {len(setup_names)} CAM setup(s):\n  • ' + '\n  • '.join(setup_names) + '\n\nRegenerating toolpaths...',
                'CAM Setups Found',
                adsk.core.MessageBoxButtonTypes.OKButtonType,
                adsk.core.MessageBoxIconTypes.InformationIconType
            )
            
            # Regenerate ALL toolpaths (requirement: always regenerate all setups)
            self.logger.info(f'{comp_id}: Regenerating toolpaths for all setups')
            regen_success, regen_msg, regen_results = cam_mgr.regenerate_all_toolpaths()
            
            # Log results
            for setup_name, success, msg in regen_results:
                if success:
                    self.logger.info(f'{comp_id}: Setup "{setup_name}": {msg}')
                else:
                    self.logger.error(f'{comp_id}: Setup "{setup_name}": {msg}')
            
            # If regeneration failed, fail entire order (requirement)
            if not regen_success:
                self.logger.error(f'{comp_id}: Toolpath regeneration failed: {regen_msg}')
                
                # Show error details
                error_details = '\n'.join([f'  • {name}: {msg}' for name, success, msg in regen_results if not success])
                self.ui.messageBox(
                    f'{comp_id}: Toolpath regeneration FAILED!\n\n{regen_msg}\n\n{error_details}',
                    'Toolpath Generation Failed',
                    adsk.core.MessageBoxButtonTypes.OKButtonType,
                    adsk.core.MessageBoxIconTypes.CriticalIconType
                )
                
                return False, f'{comp_id}: Toolpath regeneration failed: {regen_msg}'
            
            # Phase 4: Post process all setups to generate G-code
            self.logger.info(f'{comp_id}: Starting post processing')
            
            # Get output directory - hardcoded for now, could be from JSON later
            output_dir = r'C:\Users\james.derrod\OneDrive - Bobrick Washroom Equipment\Documents\Fusion 360\NC Programs'
            
            post_proc = PostProcessor(self.app, output_dir)
            
            # Get all setups for post processing
            all_setups = cam_mgr.get_all_setups()
            
            # Show starting message
            self.ui.messageBox(
                f'Toolpaths regenerated successfully!\n\nStarting post processing for {len(all_setups)} setup(s)...',
                'Post Processing',
                adsk.core.MessageBoxButtonTypes.OKButtonType,
                adsk.core.MessageBoxIconTypes.InformationIconType
            )
            
            # Post process all setups
            post_success, post_msg, post_results = post_proc.post_process_all_setups(cam_mgr.cam_product, all_setups)
            
            # Log post processing results
            for setup_name, success, msg, file_path in post_results:
                if success:
                    self.logger.info(f'{comp_id}: Post "{setup_name}": {msg}')
                else:
                    self.logger.error(f'{comp_id}: Post "{setup_name}": {msg}')
            
            # Check if at least some setups posted successfully
            successful_posts = [r for r in post_results if r[1]]
            
            if not successful_posts:
                # All post processing failed - this is an error
                self.logger.error(f'{comp_id}: All post processing failed')
                
                error_details = '\n'.join([f'  • {name}: {msg}' for name, success, msg, _ in post_results if not success])
                self.ui.messageBox(
                    f'{comp_id}: Post processing FAILED!\n\n{post_msg}\n\n{error_details}',
                    'Post Processing Failed',
                    adsk.core.MessageBoxButtonTypes.OKButtonType,
                    adsk.core.MessageBoxIconTypes.CriticalIconType
                )
                
                return False, f'{comp_id}: Post processing failed: {post_msg}'
            
            # Success! Show final results
            self.logger.info(f'{comp_id}: All operations complete')
            
            final_msg = f'{comp_id}: Processing complete!\n\n'
            final_msg += f'✓ Updated {len(parameters)} parameter(s)\n'
            if export_success:
                model_filename = os.path.basename(export_path) if export_path else f'{comp_id}.step'
                final_msg += f'✓ Exported 3D model: {model_filename}\n'
            if param_export_success:
                param_filename = os.path.basename(param_export_path) if param_export_path else f'{comp_id}_all_parameters.csv'
                final_msg += f'✓ Exported parameters: {param_filename}\n'
            final_msg += f'✓ Regenerated {len(setup_names)} CAM setup(s)\n'
            final_msg += f'✓ Generated {len(successful_posts)}/{len(all_setups)} NC program(s):\n'
            
            for setup_name, success, msg, file_path in post_results:
                if success:
                    # Extract just filename from path
                    filename = os.path.basename(file_path) if file_path else 'unknown'
                    final_msg += f'    • {setup_name}: {filename}\n'
                else:
                    final_msg += f'    • {setup_name}: FAILED ({msg})\n'
            
            final_msg += f'\nOutput: {output_dir}'
            
            self.ui.messageBox(
                final_msg,
                'Component Complete',
                adsk.core.MessageBoxButtonTypes.OKButtonType,
                adsk.core.MessageBoxIconTypes.InformationIconType
            )
            
            return True, f'{comp_id}: Complete - {len(successful_posts)} NC file(s) generated'
            
        except Exception as e:
            return False, f'{comp_id}: Exception: {str(e)}'
    
    def process_order_v2(self, order_file_path: str, progress_dialog=None) -> Tuple[bool, str]:
        """
        Process a complete manufacturing order using the new JSON structure.
        New structure has order_id, panels[], doors[], stiles[] with [value, datatype, description] format.
        
        Args:
            order_file_path: Path to order JSON file
            progress_dialog: Optional ProgressDialog for UI updates
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Load order
            self.logger.info(f'Loading order (v2) from: {order_file_path}')
            order = self.load_order_file(order_file_path)
            if not order:
                self.logger.error('Failed to load order file')
                return False, 'Failed to load order file'
            
            # Extract order_id - it's in [value, datatype, description] format
            order_id_data = order.get('order_id', ['unknown', 'string', ''])
            if isinstance(order_id_data, list):
                order_id = order_id_data[0]
            else:
                order_id = order_id_data
            
            self.logger.info(f'Processing order (v2): {order_id}')
            
            # Check available models
            available_models = self.model_manager.get_available_models()
            self.logger.info(f'Available models: {available_models}')
            
            # Count total components for progress tracking
            total_components = 0
            component_types = [
                ('panels', ModelManager.PANEL),
                ('doors', ModelManager.DOOR),
                ('stiles', ModelManager.STILE)
            ]
            for json_key, _ in component_types:
                total_components += len(order.get(json_key, []))
            
            # Initialize progress tracker
            from progress_dialog import ProgressTracker
            tracker = None
            if progress_dialog:
                tracker = ProgressTracker(progress_dialog, total_components)
            
            results = []
            
            # Process each component type in order: panels, doors, stiles
            for json_key, component_type in component_types:
                components = order.get(json_key, [])
                
                if not components:
                    self.logger.info(f'No {json_key} in order')
                    continue
                
                self.logger.info(f'Processing {len(components)} {json_key}')
                
                # Process each component of this type
                for idx, component in enumerate(components):
                    # Update progress
                    comp_id_data = component.get('id', [f'{json_key[:-1].upper()}{idx+1}', 'string', ''])
                    comp_id = comp_id_data[0] if isinstance(comp_id_data, list) else comp_id_data
                    
                    if tracker:
                        tracker.start_component(comp_id, json_key)
                    
                    comp_result = self.process_component_v2(
                        component, 
                        component_type, 
                        idx + 1, 
                        len(components),
                        tracker
                    )
                    results.append((json_key, comp_result))
                    
                    if tracker:
                        tracker.complete_component(comp_result[0])
            
            # Summary
            success_count = sum(1 for _, r in results if r[0])
            total_count = len(results)
            
            # Show final progress
            if tracker:
                tracker.finish(success_count, total_count - success_count)
            
            if total_count == 0:
                return False, 'No components found in order'
            
            if success_count == total_count:
                # All succeeded
                message = f'Order {order_id} completed successfully!\n\nProcessed {total_count} component(s)'
                return True, message
            elif success_count > 0:
                # Partial success
                message = f'Order {order_id} partially completed.\n\n'
                message += f'{success_count}/{total_count} components successful\n\n'
                message += 'Failed components:\n'
                for comp_type, (success, msg) in results:
                    if not success:
                        message += f'  {comp_type}: {msg}\n'
                return False, message
            else:
                # All failed
                message = f'Order {order_id} failed.\n\n'
                message += f'0/{total_count} components successful\n\n'
                message += 'Failed components:\n'
                for comp_type, (success, msg) in results:
                    message += f'  {comp_type}: {msg}\n'
                
                # Don't show message box - final summary is shown by command_handler
                return False, message
            
        except Exception as e:
            self.logger.exception('Order processing (v2) failed')
            return False, f'Order processing failed: {str(e)}'
    
    def process_component_v2(self, component: Dict, component_type: str, comp_num: int, total_comps: int, tracker=None) -> Tuple[bool, str]:
        """
        Process a single component from the new order format.
        
        Args:
            component: Component dictionary with 'id' and 'parameters' keys
            component_type: Type of component (door, panel, stile)
            comp_num: Component number (1-indexed)
            total_comps: Total number of components of this type
            tracker: Optional ProgressTracker for UI updates
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Extract component ID from [value, datatype, description] format
            comp_id_data = component.get('id', [f'{component_type}{comp_num}', 'string', ''])
            if isinstance(comp_id_data, list):
                comp_id = comp_id_data[0]
            else:
                comp_id = comp_id_data
            
            parameters = component.get('parameters', {})
            
            self.logger.info(f'Processing {component_type} {comp_num}/{total_comps}: {comp_id}')
            self.logger.info(f'  Parameters to apply: {len(parameters)}')
            
            # Validate component data
            if not parameters:
                return False, f'{comp_id}: No parameters specified'
            
            # Check if model is available
            if not self.model_manager.is_model_available(component_type):
                return False, f'{comp_id}: No {component_type} model configured in inputs folder'
            
            # Open/activate the appropriate model
            if tracker:
                tracker.update_step(f"Switching to {component_type} model...")
            
            success, doc, msg = self.model_manager.open_model(component_type)
            if not success:
                return False, f'{comp_id}: {msg}'
            
            self.logger.info(f'{comp_id}: {msg}')
            
            # Get the design
            design = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
            if not design:
                return False, f'{comp_id}: No design found in {component_type} model'
            
            # Apply parameters using new JSON format
            if tracker:
                tracker.update_step(f"Updating {len(parameters)} parameters...")
            
            self.logger.info(f'Applying parameters to {comp_id}')
            param_mgr = ParameterManager(design)
            results = param_mgr.update_parameters_from_json(parameters)
            
            # Log each parameter update
            for param_name, success, msg in results:
                if success:
                    self.logger.info(f'  ✓ {msg}')
                else:
                    self.logger.error(f'  ✗ {msg}')
            
            # Check results
            failed_params = [r for r in results if not r[1]]
            if failed_params:
                error_msg = f'{comp_id}: Some parameters failed to update:\n'
                for param_name, success, msg in failed_params:
                    error_msg += f'  {msg}\n'
                return False, error_msg
            
            # Success! Parameters updated
            self.logger.info(f'{comp_id}: Successfully updated {len(results)} parameter(s)')
            
            if tracker:
                tracker.update_step("Exporting 3D model...")
            
            # Export 3D model with applied parameters
            models_output_dir = r'C:\Users\james.derrod\OneDrive - Bobrick Washroom Equipment\Documents\Fusion 360\Models'
            model_exporter = ModelExporter(self.app, models_output_dir)
            
            export_success, export_msg, export_path = model_exporter.export_model(design, comp_id, format='step')
            
            if export_success:
                self.logger.info(f'{comp_id}: Model exported: {export_msg}')
            else:
                self.logger.warning(f'{comp_id}: Model export failed: {export_msg}')
            
            # Export parameters to CSV
            params_output_dir = r'C:\Users\james.derrod\OneDrive - Bobrick Washroom Equipment\Documents\Fusion 360\Parameters'
            param_exporter = ParameterExporter(self.app, params_output_dir)
            
            param_export_success, param_export_msg, param_export_path = param_exporter.export_all_parameters(design, comp_id)
            
            if param_export_success:
                self.logger.info(f'{comp_id}: Parameters exported: {param_export_msg}')
            else:
                self.logger.warning(f'{comp_id}: Parameter export failed: {param_export_msg}')
            
            if tracker:
                tracker.update_step("Accessing CAM setups...")
            
            self.logger.info(f'{comp_id}: Starting CAM regeneration')
            
            # Regenerate CAM toolpaths
            cam_mgr = CAMManager(self.app, doc)
            
            self.logger.info(f'{comp_id}: Accessing CAM product')
            cam_success, cam_msg = cam_mgr.get_cam_product()
            
            if not cam_success:
                self.logger.error(f'{comp_id}: {cam_msg}')
                return False, f'{comp_id}: CAM access failed: {cam_msg}'
            
            self.logger.info(f'{comp_id}: {cam_msg}')
            
            # List available setups
            setup_names = cam_mgr.list_setup_names()
            self.logger.info(f'{comp_id}: Found {len(setup_names)} CAM setup(s): {", ".join(setup_names)}')
            
            if not setup_names:
                return False, f'{comp_id}: No CAM setups found in {component_type} model'
            
            # Regenerate ALL toolpaths
            if tracker:
                tracker.update_step(f"Regenerating {len(setup_names)} CAM toolpaths...")
            
            self.logger.info(f'{comp_id}: Regenerating toolpaths for all setups')
            regen_success, regen_msg, regen_results = cam_mgr.regenerate_all_toolpaths()
            
            # Log results
            for setup_name, success, msg in regen_results:
                if success:
                    self.logger.info(f'{comp_id}: Setup "{setup_name}": {msg}')
                else:
                    self.logger.error(f'{comp_id}: Setup "{setup_name}": {msg}')
            
            # If regeneration failed, fail entire component
            if not regen_success:
                self.logger.error(f'{comp_id}: Toolpath regeneration failed: {regen_msg}')
                return False, f'{comp_id}: Toolpath regeneration failed: {regen_msg}'
            
            # Post process all setups to generate G-code
            if tracker:
                tracker.update_step("Generating G-code...")
            
            self.logger.info(f'{comp_id}: Starting post processing')
            
            output_dir = r'C:\Users\james.derrod\OneDrive - Bobrick Washroom Equipment\Documents\Fusion 360\NC Programs'
            
            post_proc = PostProcessor(self.app, output_dir)
            
            all_setups = cam_mgr.get_all_setups()
            
            # Post process all setups
            post_success, post_msg, post_results = post_proc.post_process_all_setups(cam_mgr.cam_product, all_setups)
            
            # Log post processing results
            for setup_name, success, msg, file_path in post_results:
                if success:
                    self.logger.info(f'{comp_id}: Post "{setup_name}": {msg}')
                else:
                    self.logger.error(f'{comp_id}: Post "{setup_name}": {msg}')
            
            # Check if at least some setups posted successfully
            successful_posts = [r for r in post_results if r[1]]
            
            if not successful_posts:
                self.logger.error(f'{comp_id}: All post processing failed')
                return False, f'{comp_id}: Post processing failed: {post_msg}'
            
            # Success!
            self.logger.info(f'{comp_id}: All operations complete - {len(successful_posts)} NC files generated')
            
            return True, f'{comp_id}: Complete - {len(successful_posts)} NC file(s) generated'
            
        except Exception as e:
            comp_id_fallback = 'unknown'
            try:
                comp_id_data = component.get('id', ['unknown', 'string', ''])
                if isinstance(comp_id_data, list):
                    comp_id_fallback = comp_id_data[0]
                else:
                    comp_id_fallback = comp_id_data
            except:
                pass
            self.logger.exception(f'Component processing failed: {comp_id_fallback}')
            return False, f'{comp_id_fallback}: Exception: {str(e)}'
    
    def get_current_design(self) -> Optional[adsk.fusion.Design]:
        """
        Get the currently active design.
        
        Returns:
            Design object or None
        """
        try:
            doc = self.app.activeDocument
            if not doc:
                return None
            
            design = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
            return design
            
        except:
            return None
