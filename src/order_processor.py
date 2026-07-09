"""
Order Processor for Fusion 360 Manufacturing Pipeline
Handles loading orders, opening documents, and coordinating operations
"""

import adsk.core
import adsk.fusion
import json
import os
import re
import time
from typing import Dict, List, Tuple, Optional
from pathlib import Path

from parameter_manager import ParameterManager
from cam_manager import CAMManager
from post_processor import PostProcessor
from model_exporter import ModelExporter
from parameter_exporter import ParameterExporter
from model_manager import ModelManager
from drawing_exporter import DrawingExporter
from logger import get_logger


class OrderProcessor:
    """Processes manufacturing orders from JSON files"""
    
    def __init__(self, app: adsk.core.Application, inputs_folder: str = None, skip_cam: bool = False, skip_drawing: bool = False):
        """
        Initialize order processor.
        
        Args:
            app: Fusion Application object
            inputs_folder: Optional path to inputs folder for persistent models
            skip_cam: If True, skip CAM regeneration and G-code export
            skip_drawing: If True, skip door drawing export
        """
        self.app = app
        self.ui = app.userInterface
        self.logger = get_logger()
        self.model_manager = ModelManager(app, inputs_folder)
        self.skip_cam = skip_cam
        self.skip_drawing = skip_drawing
        self._drawing_exporter = None
    
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
            
            # Validate order_id - empty/None would scatter output into root folders
            if not order_id or str(order_id).strip() == '':
                # Use the JSON filename (without extension) as fallback
                fallback_id = os.path.splitext(os.path.basename(order_file_path))[0]
                self.logger.warning(f'Order has empty order_id, using filename as fallback: {fallback_id}')
                order_id = fallback_id
            
            self.logger.info(f'Processing order (v2): {order_id}')

            # Capture a single human-readable "order ran" timestamp shared by all
            # output-type archive folders (e.g. "Jun 5 2026 - 1313"). 24-hour time,
            # no colons since they are illegal in Windows filenames.
            from datetime import datetime as _dt
            self._order_run_ts = _dt.now().strftime('%b %#d %Y - %H%M')

            # Create order-specific log file in network output directory
            from config import OUTPUT_BASE
            order_log_path = self.logger.add_order_log_handler(order_id, str(OUTPUT_BASE))
            
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
            self._cam_report = []  # Per-component CAM validation results for end-of-order report
            drilling_paired_collection = []  # Collect paired drilling data for compiled file
            
            # Organized drilling collections by component type for structured output
            drilling_paired_by_type = {'doors': [], 'panels': [], 'stiles': []}
            
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
                    
                    comp_result, drilling_tuple = self.process_component_v2(
                        component, 
                        component_type, 
                        idx + 1, 
                        len(components),
                        order_id,
                        tracker
                    )
                    results.append((json_key, comp_result))
                    
                    # Collect drilling data if available (doors and stiles)
                    if drilling_tuple:
                        drilling_data, drilling_paired_data = drilling_tuple
                        if drilling_paired_data:
                            self.logger.info(f'{comp_id}: Adding drilling data to compiled collection')
                            drilling_paired_collection.append(drilling_paired_data)
                            # Also add to organized collection
                            if json_key in drilling_paired_by_type:
                                drilling_paired_by_type[json_key].append(drilling_paired_data)
                    
                    if tracker:
                        tracker.complete_component(comp_result[0])
                    
                    # Stabilization delay between components. Pump one doEvents()
                    # so Fusion can process pending internal events (save completion,
                    # cloud upload, BREP entity cleanup). A single doEvents call is
                    # safe — it's sustained loops of hundreds that cause PLM360 issues.
                    # When CAM+drawing are skipped (param-only), use a short delay
                    # since there's no BREP regeneration or cloud sync to settle.
                    if idx < len(components) - 1:
                        if self.skip_cam and self.skip_drawing:
                            time.sleep(0.5)
                        else:
                            adsk.doEvents()
                            time.sleep(3)
                
                # --- Close this type's drawing after all components are done ---
                # Drawing documents have their own AutoCAD subprocess. Every
                # doEvents() during CAM regeneration of a DIFFERENT component type
                # pokes ALL open drawing subprocesses (triggering DWG saves and
                # cross-process IPC). After many saves the accumulated state
                # crashes Fusion. Closing non-active drawings between types
                # eliminates this pressure.
                # The door drawing is NOT exempted. There is a single shared
                # AcFusionService drawing subprocess; closing panel/stile
                # drawings unloads it, and a persistently-cached door drawing
                # then has no live subprocess, so its PDF export hangs for the
                # full 600s Fusion timeout ("export timed out"). Closing the
                # door drawing too forces a fresh documents.open() next order,
                # which respawns a working subprocess (like panels, ~15-25s).
                if not self.skip_drawing:
                    self._close_type_drawing(component_type)
            
            # Write compiled drilling coordinates file if we have any paired data
            if drilling_paired_collection:
                try:
                    from config import OUTPUT_GCODE
                    
                    drilling_output_dir = os.path.join(str(OUTPUT_GCODE), order_id)
                    os.makedirs(drilling_output_dir, exist_ok=True)
                    
                    compiled_paired_filename = f"{order_id}.json"
                    compiled_paired_path = os.path.join(drilling_output_dir, compiled_paired_filename)
                    
                    # Build structured output organized by component type (similar to input JSON)
                    compiled_paired_data = {
                        order_id: {
                            'unit': 'in',
                            'description': 'Compiled paired drilling coordinates for all components organized by type',
                            'doors': [],
                            'panels': [],
                            'stiles': []
                        }
                    }
                    
                    # Add drilling data for each component type
                    for comp_type in ['doors', 'panels', 'stiles']:
                        for comp_data in drilling_paired_by_type.get(comp_type, []):
                            # Extract just the component_id and coordinates for cleaner output
                            comp_entry = {
                                'component_id': comp_data.get('component_id'),
                                'coordinates': comp_data.get('coordinates', [])
                            }
                            compiled_paired_data[order_id][comp_type].append(comp_entry)
                    
                    with open(compiled_paired_path, 'w', encoding='utf-8') as f:
                        json.dump(compiled_paired_data, f, indent=2)
                    
                    total_comps = sum(len(drilling_paired_by_type.get(t, [])) for t in ['doors', 'panels', 'stiles'])
                    self.logger.info(f'Created compiled paired drilling file: {compiled_paired_filename} with {total_comps} component(s)')
                    
                    # VM mode: also copy drilling JSON flat to dedicated network location
                    from config import RUN_MODE
                    if RUN_MODE == 'VM':
                        try:
                            from config import OUTPUT_DRILLING_NETWORK
                            import shutil
                            dest = os.path.join(str(OUTPUT_DRILLING_NETWORK), compiled_paired_filename)
                            shutil.copy2(compiled_paired_path, dest)
                            self.logger.info(f'Drilling JSON copied to network: {dest}')
                        except Exception as copy_e:
                            self.logger.warning(f'Failed to copy drilling JSON to network: {str(copy_e)}')
                except Exception as e:
                    self.logger.warning(f'Failed to create compiled paired drilling file: {str(e)}')
            
            # Summary
            success_count = sum(1 for _, r in results if r[0])
            total_count = len(results)
            
            # Show final progress
            if tracker:
                tracker.finish(success_count, total_count - success_count)
            
            if total_count == 0:
                self.logger.remove_order_log_handler(order_id)
                return False, 'No components found in order'
            
            # Create timestamped archive copies of this order's per-output-type
            # folders. The latest files stay in 'base/{order_id}'; an additional
            # snapshot is created at 'base/{order_id} {timestamp}' for each type.
            self._archive_order_outputs(order_id, getattr(self, '_order_run_ts', ''))
            
            cam_report = self._build_cam_report()
            cam_report_block = f'\n\n{cam_report}' if cam_report else ''
            if cam_report:
                self.logger.info(cam_report)

            if success_count == total_count:
                # All succeeded
                message = f'Order {order_id} completed successfully!\n\nProcessed {total_count} component(s)'
                message += cam_report_block
                self.logger.remove_order_log_handler(order_id)
                return True, message
            elif success_count > 0:
                # Partial success
                message = f'Order {order_id} partially completed.\n\n'
                message += f'{success_count}/{total_count} components successful\n\n'
                message += 'Failed components:\n'
                for comp_type, (success, msg) in results:
                    if not success:
                        message += f'  {comp_type}: {msg}\n'
                message += cam_report_block
                self.logger.remove_order_log_handler(order_id)
                return False, message
            else:
                # All failed
                message = f'Order {order_id} failed.\n\n'
                message += f'0/{total_count} components successful\n\n'
                message += 'Failed components:\n'
                for comp_type, (success, msg) in results:
                    message += f'  {comp_type}: {msg}\n'
                message += cam_report_block
                
                # Don't show message box - final summary is shown by command_handler
                self.logger.remove_order_log_handler(order_id)
                return False, message
            
        except Exception as e:
            self.logger.exception('Order processing (v2) failed')
            # Try to clean up order log handler even on exception
            try:
                if 'order_id' in locals():
                    self.logger.remove_order_log_handler(order_id)
            except Exception:
                pass
            return False, f'Order processing failed: {str(e)}'
    
    def _close_type_drawing(self, component_type: str):
        """Close the drawing document for the given component type.
        
        Drawing documents each spawn an AutoCAD subprocess. Leaving them open
        while processing a DIFFERENT component type means every doEvents() call
        during CAM regeneration triggers cross-process DWG saves on the idle
        drawing. After many saves across multiple orders, this accumulated IPC
        state causes Fusion to crash.
        
        Closing the drawing between component types eliminates the cross-process
        overhead. The drawing will be reopened from cloud on the next order
        (typically <15 s).
        """
        try:
            if component_type == ModelManager.PANEL:
                cache_key = 'panel_drawing'
            elif component_type == ModelManager.DOOR:
                cache_key = 'door_drawing'
            elif component_type == ModelManager.STILE:
                # Stile drawings are cached per series code (e.g. 'stile_3086_drawing')
                # Close ALL stile drawings
                keys_to_close = [k for k in self.model_manager._cached_drawing_docs
                                 if k.startswith('stile_') and k.endswith('_drawing')]
                for key in keys_to_close:
                    doc = self.model_manager._cached_drawing_docs.get(key)
                    if doc and doc.isValid:
                        try:
                            doc.close(False)
                            self.logger.info(f'Closed stile drawing (key={key}) to reduce subprocess pressure')
                        except Exception as e:
                            self.logger.warning(f'Failed to close stile drawing (key={key}): {e}')
                    if key in self.model_manager._cached_drawing_docs:
                        del self.model_manager._cached_drawing_docs[key]
                # Reset the shared drawing exporter state
                if self._drawing_exporter:
                    self._drawing_exporter._drawing_doc = None
                    self._drawing_exporter._drawing_data_file = None
                    self._drawing_exporter._drawing_opened_once = False
                return
            else:
                return  # Unknown component type — nothing to close
            
            doc = self.model_manager._cached_drawing_docs.get(cache_key)
            if doc and doc.isValid:
                try:
                    doc.close(False)
                    self.logger.info(f'Closed {component_type} drawing (key={cache_key}) to reduce subprocess pressure')
                except Exception as e:
                    self.logger.warning(f'Failed to close {component_type} drawing (key={cache_key}): {e}')
            if cache_key in self.model_manager._cached_drawing_docs:
                del self.model_manager._cached_drawing_docs[cache_key]
            
            # Reset the shared drawing exporter state so it doesn't try to
            # reuse a reference to the now-closed document.
            if self._drawing_exporter:
                self._drawing_exporter._drawing_doc = None
                self._drawing_exporter._drawing_data_file = None
                self._drawing_exporter._drawing_opened_once = False
        except Exception as e:
            self.logger.warning(f'_close_type_drawing({component_type}): {e}')
    
    def process_component_v2(self, component: Dict, component_type: str, comp_num: int, total_comps: int, order_id: str, tracker=None) -> Tuple[Tuple[bool, str], Optional[Dict]]:
        """
        Process a single component from the new order format.
        
        Args:
            component: Component dictionary with 'id' and 'parameters' keys
            component_type: Type of component (door, panel, stile)
            comp_num: Component number (1-indexed)
            total_comps: Total number of components of this type
            order_id: Order ID for organizing outputs
            tracker: Optional ProgressTracker for UI updates
            
        Returns:
            Tuple of ((success: bool, message: str), drilling_data: Dict or None)
            drilling_data is only populated for door components
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
                return (False, f'{comp_id}: No parameters specified'), None
            
            # Extract series_id from parameters for model selection (stiles use different models per series)
            series_id = None
            if 'series_id' in parameters:
                series_id_data = parameters['series_id']
                if isinstance(series_id_data, list):
                    series_id = series_id_data[0]
                else:
                    series_id = series_id_data
            
            # Check if model is available (for stiles, check series-specific model)
            if component_type == ModelManager.STILE:
                if not self.model_manager.is_model_available_for_series(component_type, series_id):
                    return (False, f'{comp_id}: No {component_type} model configured for series {series_id}'), None
            else:
                if not self.model_manager.is_model_available(component_type):
                    return (False, f'{comp_id}: No {component_type} model configured in inputs folder'), None
            
            # Open/activate the appropriate model (pass series_id for stiles)
            if tracker:
                tracker.update_step(f"Switching to {component_type} model...")
            
            success, doc, msg = self.model_manager.open_model(component_type, series_id)
            if not success:
                return (False, f'{comp_id}: {msg}'), None
            
            self.logger.info(f'{comp_id}: {msg}')
            
            # Get the design
            design = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
            if not design:
                return (False, f'{comp_id}: No design found in {component_type} model'), None
            
            # Apply parameters using new JSON format
            if tracker:
                tracker.update_step(f"Updating {len(parameters)} parameters...")
            
            self.logger.info(f'Applying parameters to {comp_id}')
            param_mgr = ParameterManager(design)
            
            # Debug: log model params vs JSON params to diagnose auto_match skipping
            model_params = set(param_mgr.get_all_parameters().keys())
            json_params = set(parameters.keys())
            matched = json_params & model_params
            skipped = json_params - model_params
            self.logger.info(f'{comp_id}: Model has {len(model_params)} user params, JSON has {len(json_params)} params')
            self.logger.info(f'{comp_id}: All model user params: {sorted(model_params)}')
            self.logger.info(f'{comp_id}: Matched: {sorted(matched)}')
            if skipped:
                self.logger.info(f'{comp_id}: Skipped (not in model): {sorted(skipped)}')
            
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
                return (False, error_msg), None
            
            # Success! Parameters updated
            self.logger.info(f'{comp_id}: Successfully updated {len(results)} parameter(s)')
            
            # For door components, set a_order_number text parameter from order_id
            if component_type == ModelManager.DOOR:
                order_num_success, order_num_msg = param_mgr.update_parameter('a_order_number', f"'{order_id}'")
                if order_num_success:
                    self.logger.info(f'{comp_id}: {order_num_msg}')
                else:
                    self.logger.warning(f'{comp_id}: Could not set a_order_number: {order_num_msg}')
            
            # Save the model after parameter application to clear Dirty flag.
            # WHY: Dirty cloud documents trigger PLM360 version reconciliation
            # on every doEvents() call during CAM/drawing processing, eventually
            # causing STACK_OVERFLOW crashes.
            if not self.skip_cam or not self.skip_drawing:
                post_param_save_success, post_param_save_msg = self.model_manager.save_active_model(
                    f"Parameters applied for {comp_id}"
                )
                if post_param_save_success:
                    self.logger.info(f'{comp_id}: Post-parameter save: {post_param_save_msg}')
                else:
                    self.logger.warning(f'{comp_id}: Post-parameter save failed: {post_param_save_msg}')
            else:
                self.logger.info(f'{comp_id}: Skipping post-parameter save (no CAM/drawing)')
            
            # For panel components, apply cutout parameters if specified
            if component_type == ModelManager.PANEL:
                cutout_value = None
                if 'cutout' in parameters:
                    cutout_data = parameters['cutout']
                    if isinstance(cutout_data, list):
                        cutout_value = cutout_data[0]  # Extract value from [value, type, description]
                    else:
                        cutout_value = cutout_data
                
                # Apply cutout parameters (cutout_A / cutout_B text params)
                cutout_success, cutout_msg = self._apply_cutout_parameters(param_mgr, cutout_value, comp_id)
                if cutout_success:
                    self.logger.info(f'{comp_id}: {cutout_msg}')
                else:
                    self.logger.error(f'{comp_id}: {cutout_msg}')
                    return (False, f'{comp_id}: Cutout parameter failed: {cutout_msg}'), None
            
            if tracker:
                tracker.update_step("Exporting 3D model...")
            
            # Export 3D model with applied parameters
            from config import OUTPUT_MODELS
            models_output_dir = os.path.join(str(OUTPUT_MODELS), order_id)
            model_exporter = ModelExporter(self.app, models_output_dir)
            
            export_success, export_msg, export_path = model_exporter.export_model(design, comp_id, format='step')
            
            if export_success:
                self.logger.info(f'{comp_id}: Model exported: {export_msg}')
            else:
                self.logger.warning(f'{comp_id}: Model export failed: {export_msg}')
            
            # Export parameters to CSV and JSON
            from config import OUTPUT_PARAMETERS
            params_output_dir = os.path.join(str(OUTPUT_PARAMETERS), order_id)
            param_exporter = ParameterExporter(self.app, params_output_dir)
            
            # Build metadata dict for non-model parameters (series_id already extracted above)
            metadata = {}
            if series_id:
                metadata['series_id'] = series_id
            
            # Export CSV
            param_export_success, param_export_msg, param_export_path = param_exporter.export_all_parameters(design, comp_id, metadata=metadata)
            
            if param_export_success:
                self.logger.info(f'{comp_id}: Parameters exported (CSV): {param_export_msg}')
            else:
                self.logger.warning(f'{comp_id}: Parameter export failed (CSV): {param_export_msg}')
            
            # Export JSON
            json_export_success, json_export_msg, json_export_path = param_exporter.export_all_parameters_json(design, comp_id, metadata=metadata)
            
            if json_export_success:
                self.logger.info(f'{comp_id}: Parameters exported (JSON): {json_export_msg}')
            else:
                self.logger.warning(f'{comp_id}: Parameter export failed (JSON): {json_export_msg}')
            
            # Compute drilling coordinates (doors and stiles)
            # Data is collected here and written to the compiled order-level file later
            drilling_data = None
            drilling_paired_data = None
            if component_type in [ModelManager.DOOR, ModelManager.STILE]:
                drilling_exporter = ParameterExporter(self.app, '')  # no output dir needed
                
                # Compute paired drilling coordinates (returns data dict directly)
                paired_success, paired_msg, paired_data = drilling_exporter.export_drilling_coordinates_paired(design, comp_id, order_id, parameters)
                
                if paired_success:
                    self.logger.info(f'{comp_id}: {paired_msg}')
                    drilling_paired_data = paired_data
                else:
                    # No drilling extracted — create a fallback air drilling entry
                    # so the component still appears in the compiled output.
                    self.logger.info(f'{comp_id}: No drilling coordinates ({paired_msg}) — adding air drilling at workstop 1')
                    from datetime import datetime as _dt
                    _ts = _dt.now().strftime('%Y-%m-%d %H:%M:%S')
                    drilling_paired_data = {
                        'component_id': comp_id,
                        'order_id': order_id,
                        'unit': 'in',
                        'description': 'No drilling required',
                        'coordinates': [{
                            'ProgramName': f'1-{comp_id}-{order_id}',
                            'WorkStop': 1,
                            'PositionX': 121,
                            'PositionY': 0.197,
                            'PositionZ': None,
                            'Function': 4,
                            'ToolDM': 1,
                            'FlipRotate': 1,
                            'SSMA_TimeStamp': None,
                            'Fusion_TimeStamp': _ts,
                            'DrillName': 'NO DRILLING REQUIRED'
                        }, {
                            'ProgramName': f'1-{comp_id}-{order_id}',
                            'WorkStop': 4,
                            'PositionX': 121,
                            'PositionY': 0.197,
                            'PositionZ': None,
                            'Function': 4,
                            'ToolDM': 1,
                            'FlipRotate': 1,
                            'SSMA_TimeStamp': None,
                            'Fusion_TimeStamp': _ts,
                            'DrillName': 'NO DRILLING REQUIRED'
                        }]
                    }
            
            # Export cutlist CSV for all component types
            # Output goes to gcode folder: M:\S2S File Test\output\gcode\{order_id}\{order_id}.csv
            from config import OUTPUT_GCODE
            cutlist_output_dir = os.path.join(str(OUTPUT_GCODE), order_id)
            cutlist_exporter = ParameterExporter(self.app, cutlist_output_dir)
            
            cutlist_export_success, cutlist_export_msg, cutlist_export_path = cutlist_exporter.export_cutlist_csv(design, comp_id, order_id, component_params=parameters, component_type=component_type)
            
            if cutlist_export_success:
                self.logger.info(f'{comp_id}: Cutlist CSV exported: {cutlist_export_msg}')
                # VM mode: copy cutlist CSV flat to dedicated Voorwood network folder
                from config import RUN_MODE
                if RUN_MODE == 'VM' and cutlist_export_path:
                    try:
                        from config import OUTPUT_CUTLIST_NETWORK
                        import shutil
                        csv_dest = os.path.join(str(OUTPUT_CUTLIST_NETWORK), os.path.basename(cutlist_export_path))
                        shutil.copy2(cutlist_export_path, csv_dest)
                        self.logger.info(f'{comp_id}: Cutlist CSV copied to network: {csv_dest}')
                    except Exception as copy_e:
                        self.logger.warning(f'{comp_id}: Failed to copy cutlist CSV to network: {str(copy_e)}')
            else:
                self.logger.warning(f'{comp_id}: Cutlist CSV export failed: {cutlist_export_msg}')
            
            # --- Drawing export (independent of CAM) ---
            drawing_exported = False
            if self.skip_drawing:
                self.logger.info(f'{comp_id}: Drawing export skipped (disabled by user)')
            elif component_type == ModelManager.DOOR:
                # Door drawing export — works with both cloud and local .f3d door models.
                # The drawing is always a cloud document; the model can be either.
                drawing_data_file = self.model_manager.get_door_drawing_data_file()
                if drawing_data_file:
                    if tracker:
                        tracker.update_step("Saving door model...")
                    
                    self.logger.info(f'{comp_id}: Starting drawing export')
                    
                    # Attempt pre-drawing save. For cloud models this creates a new
                    # version; for local .f3d models this will fail (expected) but
                    # the drawing can still pick up in-memory model state via
                    # updateAllReferences().
                    try:
                        doc = self.app.activeDocument
                        if doc and doc.isModified:
                            self.logger.info(f'{comp_id}: Saving model before drawing export...')
                            doc.save(f"Updated for {comp_id}")
                            time.sleep(3.0)
                            self.logger.info(f'{comp_id}: Model saved')
                        else:
                            self.logger.info(f'{comp_id}: Model not modified, skipping save')
                    except Exception as e:
                        self.logger.warning(f'{comp_id}: Pre-drawing save warning (non-fatal): {e}')
                    
                    if tracker:
                        tracker.update_step("Exporting door drawing...")
                    
                    if self._drawing_exporter is None:
                        from config import OUTPUT_GCODE
                        self._drawing_exporter = DrawingExporter(self.app, str(OUTPUT_GCODE))
                    drawing_exporter = self._drawing_exporter
                    
                    # Get cached drawing doc (from a previous order's open)
                    pre_opened_drawing = self.model_manager.get_cached_drawing_doc('door_drawing')
                    if pre_opened_drawing:
                        self.logger.info(f'{comp_id}: Using cached door drawing document')
                    else:
                        self.logger.info(f'{comp_id}: No cached drawing — first order will open from cloud (may take minutes)')
                    
                    drawing_success, drawing_msg, drawing_path = drawing_exporter.export_door_drawing(
                        comp_id, order_id, drawing_data_file, pre_opened_doc=pre_opened_drawing
                    )
                    
                    if drawing_success:
                        self.logger.info(f'{comp_id}: Drawing exported: {drawing_msg}')
                        drawing_exported = True
                        # Cache the opened drawing doc for subsequent orders
                        if not pre_opened_drawing and drawing_exporter._drawing_doc:
                            self.model_manager._cached_drawing_docs['door_drawing'] = drawing_exporter._drawing_doc
                            self.logger.info(f'{comp_id}: Door drawing cached for future orders')
                    else:
                        self.logger.warning(f'{comp_id}: Drawing export failed: {drawing_msg}')
                    
                    # Re-activate the door model for next component.
                    # Use open_model() which handles both cloud and local .f3d models.
                    self.model_manager.open_model(component_type, series_id)
                    adsk.doEvents()
                    time.sleep(1.0)
                    self.logger.info(f'{comp_id}: Door model re-activated after drawing export')
                else:
                    self.logger.info(f'{comp_id}: No door drawing configured - skipping drawing export')
            elif component_type == ModelManager.STILE and series_id:
                # Stile drawing export
                stile_drawing_data_file = self.model_manager.get_stile_drawing_data_file(series_id)
                if stile_drawing_data_file:
                    if tracker:
                        tracker.update_step("Saving stile model to cloud...")
                    
                    self.logger.info(f'{comp_id}: Starting stile drawing export')
                    
                    # Save model before drawing export (best effort).
                    # Even if save fails, we proceed — updateAllReferences()
                    # picks up in-memory model state.
                    try:
                        doc = self.app.activeDocument
                        if doc and doc.isModified:
                            self.logger.info(f'{comp_id}: Saving model before drawing export...')
                            doc.save(f"Updated for {comp_id}")
                            time.sleep(3.0)
                            self.logger.info(f'{comp_id}: Model saved')
                        else:
                            self.logger.info(f'{comp_id}: Model not modified, skipping save')
                    except Exception as e:
                        self.logger.warning(f'{comp_id}: Pre-drawing save error (non-fatal, proceeding): {e}')
                    
                    # Always proceed with drawing export
                    if tracker:
                        tracker.update_step("Exporting stile drawing...")
                    
                    if self._drawing_exporter is None:
                        from config import OUTPUT_GCODE
                        self._drawing_exporter = DrawingExporter(self.app, str(OUTPUT_GCODE))
                    drawing_exporter = self._drawing_exporter
                    
                    # Get cached drawing doc (from a previous order's open)
                    series_code = self.model_manager._extract_series_code(series_id)
                    cache_key = f'stile_{series_code}_drawing' if series_code else None
                    pre_opened_drawing = self.model_manager.get_cached_drawing_doc(cache_key) if cache_key else None
                    if pre_opened_drawing:
                        self.logger.info(f'{comp_id}: Using cached drawing document (key={cache_key})')
                    else:
                        self.logger.info(f'{comp_id}: No cached drawing — first order will open from cloud (may take minutes)')
                    
                    drawing_success, drawing_msg, drawing_path = drawing_exporter.export_stile_drawing(
                        comp_id, order_id, stile_drawing_data_file, pre_opened_doc=pre_opened_drawing
                    )
                    
                    if drawing_success:
                        self.logger.info(f'{comp_id}: Stile drawing exported: {drawing_msg}')
                        drawing_exported = True
                        # Cache the opened drawing doc for subsequent orders
                        if not pre_opened_drawing and cache_key and drawing_exporter._drawing_doc:
                            self.model_manager._cached_drawing_docs[cache_key] = drawing_exporter._drawing_doc
                            self.logger.info(f'{comp_id}: Stile drawing cached for future orders (key={cache_key})')
                    else:
                        self.logger.warning(f'{comp_id}: Stile drawing export failed: {drawing_msg}')
                    
                    # Re-activate the stile model for CAM/next operations.
                    # Pump doEvents so Fusion fully transitions back to Design workspace.
                    self.model_manager.open_cloud_stile_model(series_id)
                    adsk.doEvents()
                    time.sleep(1.0)
                    self.logger.info(f'{comp_id}: Stile model re-activated after drawing export')
                else:
                    self.logger.info(f'{comp_id}: No stile drawing configured for series {series_id} - skipping drawing export')
            elif component_type == ModelManager.PANEL:
                # Panel drawing export
                panel_drawing_data_file = self.model_manager.get_panel_drawing_data_file()
                if panel_drawing_data_file:
                    if tracker:
                        tracker.update_step("Saving panel model to cloud...")
                    
                    self.logger.info(f'{comp_id}: Starting panel drawing export')
                    
                    # Save model to cloud before drawing export (best effort).
                    # Even if save fails/times out, we still proceed with drawing
                    # export — updateAllReferences() picks up in-memory model state.
                    try:
                        self.logger.info(f'{comp_id}: Saving panel model before drawing export...')
                        save_ok, save_msg = self.model_manager.save_active_model_for_drawing(
                            f"Updated for {comp_id}", timeout_seconds=60
                        )
                        self.logger.info(f'{comp_id}: Pre-drawing save: {save_msg}')
                        if not save_ok:
                            self.logger.warning(f'{comp_id}: Pre-drawing save did not fully succeed, proceeding with drawing export anyway')
                    except Exception as e:
                        self.logger.warning(f'{comp_id}: Pre-drawing save error (non-fatal, proceeding): {e}')
                    
                    # Always proceed with drawing export
                    if tracker:
                        tracker.update_step("Exporting panel drawing...")
                    
                    if self._drawing_exporter is None:
                        from config import OUTPUT_GCODE
                        self._drawing_exporter = DrawingExporter(self.app, str(OUTPUT_GCODE))
                    drawing_exporter = self._drawing_exporter
                    
                    # Get cached drawing doc (from a previous order's open)
                    pre_opened_drawing = self.model_manager.get_cached_drawing_doc('panel_drawing')
                    if pre_opened_drawing:
                        self.logger.info(f'{comp_id}: Using cached panel drawing document')
                    else:
                        self.logger.info(f'{comp_id}: No cached drawing — first order will open from cloud (may take minutes)')
                    
                    drawing_success, drawing_msg, drawing_path = drawing_exporter.export_panel_drawing(
                        comp_id, order_id, panel_drawing_data_file, pre_opened_doc=pre_opened_drawing
                    )
                    
                    if drawing_success:
                        self.logger.info(f'{comp_id}: Panel drawing exported: {drawing_msg}')
                        drawing_exported = True
                        # Cache the opened drawing doc for subsequent orders
                        if not pre_opened_drawing and drawing_exporter._drawing_doc:
                            self.model_manager._cached_drawing_docs['panel_drawing'] = drawing_exporter._drawing_doc
                            self.logger.info(f'{comp_id}: Panel drawing cached for future orders')
                    else:
                        self.logger.warning(f'{comp_id}: Panel drawing export failed: {drawing_msg}')
                    
                    # Re-activate the panel model for CAM/next operations.
                    self.model_manager.open_cloud_panel_model()
                    adsk.doEvents()
                    time.sleep(1.0)
                    self.logger.info(f'{comp_id}: Panel model re-activated after drawing export')
                else:
                    self.logger.info(f'{comp_id}: No panel drawing configured - skipping drawing export')
            
            # Skip CAM regeneration and G-code export if skip_cam is set
            if self.skip_cam:
                result_msg = f'{comp_id}: Complete - CAM skipped'
                if drawing_exported:
                    result_msg += ', drawing exported'
                self.logger.info(f'{comp_id}: CAM generation skipped (checkbox unchecked)')
                return (True, result_msg), (drilling_data, drilling_paired_data)
            
            # Safety-net save before CAM: only if the model became dirty again
            # (e.g., drawing export may have dirtied it). The post-parameter save
            # above should have already cleared the dirty flag for the normal case.
            # save_active_model() checks isModified internally and skips if clean,
            # so this is a cheap no-op most of the time — no extra version increment.
            save_success, save_msg = self.model_manager.save_active_model(
                f"Pre-CAM save for {comp_id}"
            )
            if save_success:
                self.logger.info(f'{comp_id}: Pre-CAM save: {save_msg}')
            
            if tracker:
                tracker.update_step("Accessing CAM setups...")
            
            self.logger.info(f'{comp_id}: Starting CAM regeneration')
            
            # Regenerate CAM toolpaths
            # Use activeDocument instead of cached doc — after drawing export
            # the original doc reference may be stale (drawing close/reopen cycle
            # can invalidate document references)
            active_doc = self.app.activeDocument
            cam_mgr = CAMManager(self.app, active_doc)
            
            self.logger.info(f'{comp_id}: Accessing CAM product')
            cam_success, cam_msg = cam_mgr.get_cam_product()
            
            if not cam_success:
                self.logger.error(f'{comp_id}: {cam_msg}')
                return (False, f'{comp_id}: CAM access failed: {cam_msg}'), (drilling_data, drilling_paired_data)
            
            self.logger.info(f'{comp_id}: {cam_msg}')
            
            # List available setups
            setup_names = cam_mgr.list_setup_names()
            self.logger.info(f'{comp_id}: Found {len(setup_names)} CAM setup(s): {", ".join(setup_names)}')
            
            if not setup_names:
                return (False, f'{comp_id}: No CAM setups found in {component_type} model'), (drilling_data, drilling_paired_data)
            
            # For doors and panels: unsuppress all operations before regen so all
            # toolpaths get generated. Previous orders may have left some suppressed.
            if component_type == ModelManager.DOOR:
                unsup_ok, unsup_msg = cam_mgr.unsuppress_all_door_operations()
                self.logger.info(f'{comp_id}: Pre-regen unsuppress: {unsup_msg}')
            elif component_type == ModelManager.PANEL:
                unsup_ok, unsup_msg = cam_mgr.unsuppress_all_panel_operations()
                self.logger.info(f'{comp_id}: Pre-regen unsuppress: {unsup_msg}')
            
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
                return (False, f'{comp_id}: Toolpath regeneration failed: {regen_msg}'), (drilling_data, drilling_paired_data)
            
            # For doors and panels: selectively suppress/unsuppress toolpath operations
            # based on the model's computed parameters.
            # This must happen AFTER regen (so toolpaths exist) and BEFORE
            # post-processing (so only active toolpaths get posted).
            if component_type == ModelManager.DOOR:
                if tracker:
                    tracker.update_step("Configuring door toolpaths...")
                design = self.get_current_design()
                if design:
                    door_param_mgr = ParameterManager(design)
                    suppress_ok, suppress_msg = cam_mgr.suppress_door_toolpaths(door_param_mgr)
                    self.logger.info(f'{comp_id}: Door toolpath suppression: {suppress_msg}')
                    if not suppress_ok:
                        self.logger.warning(f'{comp_id}: Toolpath suppression failed (continuing): {suppress_msg}')
                else:
                    self.logger.warning(f'{comp_id}: Could not get design for toolpath suppression')
            elif component_type == ModelManager.PANEL:
                if tracker:
                    tracker.update_step("Configuring panel toolpaths...")
                design = self.get_current_design()
                if design:
                    panel_param_mgr = ParameterManager(design)
                    suppress_ok, suppress_msg = cam_mgr.suppress_panel_toolpaths(panel_param_mgr)
                    self.logger.info(f'{comp_id}: Panel toolpath suppression: {suppress_msg}')
                    if not suppress_ok:
                        self.logger.warning(f'{comp_id}: Panel toolpath suppression failed (continuing): {suppress_msg}')
                else:
                    self.logger.warning(f'{comp_id}: Could not get design for panel toolpath suppression')
            
            # Post process all setups to generate G-code
            if tracker:
                tracker.update_step("Generating G-code...")
            
            self.logger.info(f'{comp_id}: Starting post processing')
            
            from config import OUTPUT_GCODE
            nc_output_dir = os.path.join(str(OUTPUT_GCODE), order_id)
            
            post_proc = PostProcessor(self.app, nc_output_dir)
            
            all_setups = cam_mgr.get_all_setups()
            
            # For stiles: determine setup posting sequence from Anderson handling
            # decision tree (may produce repeated setups for flip scenarios).
            setup_sequence = None
            if component_type == ModelManager.STILE:
                # Read model-derived drilling flags for the stile ordering logic
                design = self.get_current_design()
                stile_design_params = dict(parameters)  # start with JSON params
                if design:
                    param_mgr_for_sequence = ParameterManager(design)
                    for pname in ['left_interior_drilling', 'left_exterior_drilling',
                                  'right_interior_drilling', 'right_exterior_drilling',
                                  'left_interior_rabbeting', 'left_exterior_rabbeting',
                                  'right_interior_rabbeting', 'right_exterior_rabbeting']:
                        p = param_mgr_for_sequence.user_parameters.itemByName(pname)
                        if p is not None:
                            stile_design_params[pname] = [p.value, 'number', '']
                setup_sequence = self._build_stile_setup_sequence(
                    stile_design_params, setup_names, comp_id,
                    drilling_paired_data=drilling_paired_data
                )
            elif component_type == ModelManager.PANEL:
                # For panels, the notching flags are DERIVED parameters computed
                # by the Fusion model — not present in the input JSON.
                # Read them from the model's user parameters for feature detection.
                design = self.get_current_design()
                if design:
                    panel_design_params = dict(parameters)  # start with JSON params
                    param_mgr_for_sequence = ParameterManager(design)
                    for pname in ['notching_front_edge_bottom', 'notching_back_edge_bottom',
                                  'notching_front_edge_top', 'notching_back_edge_top',
                                  'cutout_A_width', 'cutout_A_height',
                                  'cutout_B_width', 'cutout_B_height']:
                        p = param_mgr_for_sequence.user_parameters.itemByName(pname)
                        if p is not None:
                            panel_design_params[pname] = [p.value, 'number', '']
                    setup_sequence = self._build_panel_setup_sequence(
                        panel_design_params, setup_names, comp_id
                    )
                else:
                    self.logger.warning(f'{comp_id}: Could not get design for panel setup sequence, falling back to default')
                    setup_sequence = self._build_panel_setup_sequence(
                        parameters, setup_names, comp_id
                    )
            elif component_type == ModelManager.DOOR:
                # For doors, the feature flags (left_interior_rabbeting, etc.) are DERIVED
                # parameters computed by the Fusion model — not present in the input JSON.
                # Read them from the model's user parameters instead of component_params.
                # door_swinging_out is an INPUT parameter that IS in the JSON, so merge both.
                design = self.get_current_design()
                if design:
                    door_design_params = dict(parameters)  # start with JSON params
                    param_mgr_for_sequence = ParameterManager(design)
                    for pname in ['left_interior_rabbeting', 'left_exterior_rabbeting',
                                  'right_interior_rabbeting', 'right_exterior_rabbeting',
                                  'bottom_left_notching', 'bottom_right_notching',
                                  'top_left_notching', 'top_right_notching',
                                  'door_swinging_out']:
                        p = param_mgr_for_sequence.user_parameters.itemByName(pname)
                        if p is not None:
                            door_design_params[pname] = [p.value, 'number', '']
                    setup_sequence = self._build_door_setup_sequence(
                        door_design_params, setup_names, comp_id
                    )
                else:
                    self.logger.warning(f'{comp_id}: Could not get design for door setup sequence, falling back to default')
                    setup_sequence = None
            
            # Determine whether this component is EXPECTED to produce a CAM
            # toolpath, based on its derived model parameters. This is the
            # authoritative check used to validate the actual CAM output below.
            expects_toolpath, feature_summary = self._expects_toolpath(component_type, comp_id)
            self.logger.info(f'{comp_id}: Toolpath expectation: expects={expects_toolpath} (features: {feature_summary})')

            # Whether feature-detection logic decided there are no setups to post
            no_setups_to_post = setup_sequence is not None and len(setup_sequence) == 0
            if no_setups_to_post:
                self.logger.info(f'{comp_id}: Setup sequence empty — no setups to post')

            produced_toolpath = False
            successful_posts = []
            post_msg = ''
            hard_failure = None

            if not no_setups_to_post:
                # Post process setups (with optional sequence for stile handling)
                post_success, post_msg, post_results = post_proc.post_process_all_setups(
                    cam_mgr.cam_product, all_setups, comp_id, order_id,
                    setup_sequence=setup_sequence
                )

                # Log post processing results
                for setup_name, success, msg, file_path in post_results:
                    if success:
                        self.logger.info(f'{comp_id}: Post "{setup_name}": {msg}')
                    else:
                        self.logger.error(f'{comp_id}: Post "{setup_name}": {msg}')

                successful_posts = [r for r in post_results if r[1]]
                produced_toolpath = bool(successful_posts)

                # Distinguish a soft "nothing to post" outcome (all toolpaths
                # suppressed because the piece needs none) from a hard failure
                # (post processor missing, exception, file error, etc.). Only
                # hard failures fail the component irrespective of expectation.
                if not produced_toolpath:
                    soft_markers = ('No setups have valid toolpaths', 'No valid toolpaths',
                                    'No CAM data', 'No output files', 'No setup files were generated')
                    if post_results and not any(m in post_msg for m in soft_markers):
                        hard_failure = post_msg

            # Hard failures fail the component regardless of expectation
            if hard_failure:
                self._record_cam_status(comp_id, component_type, expects_toolpath,
                                        produced_toolpath, feature_summary, 'FAIL',
                                        f'post-processing error: {hard_failure}')
                self.logger.error(f'{comp_id}: Post processing failed: {hard_failure}')
                self._switch_to_design_workspace(comp_id)
                return (False, f'{comp_id}: Post processing failed: {hard_failure}'), (drilling_data, drilling_paired_data)

            # ── Validate actual CAM output against expectation ──
            # not expected + produced  → FAIL (toolpath should not exist)
            if not expects_toolpath and produced_toolpath:
                reason = ('unexpected toolpath generated (model has no rabbeting/notching/cutout '
                          'features but CAM produced G-code)')
                self._record_cam_status(comp_id, component_type, expects_toolpath,
                                        produced_toolpath, feature_summary, 'FAIL', reason)
                self.logger.error(f'{comp_id}: CAM validation failed: {reason}')
                self._switch_to_design_workspace(comp_id)
                return (False, f'{comp_id}: CAM validation failed: {reason}'), (drilling_data, drilling_paired_data)

            # expected + not produced → FAIL (toolpath missing)
            if expects_toolpath and not produced_toolpath:
                reason = (f'expected toolpath for features [{feature_summary}] but no G-code was '
                          'generated (all toolpaths suppressed or missing)')
                self._record_cam_status(comp_id, component_type, expects_toolpath,
                                        produced_toolpath, feature_summary, 'FAIL', reason)
                self.logger.error(f'{comp_id}: CAM validation failed: {reason}')
                self._switch_to_design_workspace(comp_id)
                return (False, f'{comp_id}: CAM validation failed: {reason}'), (drilling_data, drilling_paired_data)

            # not expected + not produced → PASS (correct no-machining case)
            if not expects_toolpath and not produced_toolpath:
                self._record_cam_status(comp_id, component_type, expects_toolpath,
                                        produced_toolpath, feature_summary, 'PASS',
                                        'no machining features; no G-code expected or generated')
                self.logger.info(f'{comp_id}: No machining features — no G-code expected; passing component')
                self._switch_to_design_workspace(comp_id)
                return (True, f'{comp_id}: Complete - No NC files (no machining features)'), (drilling_data, drilling_paired_data)

            # expected + produced → success path
            # VM mode: copy G-code .txt files flat to dedicated Anderson network folder
            from config import RUN_MODE
            if RUN_MODE == 'VM':
                try:
                    from config import OUTPUT_NC_NETWORK
                    import shutil
                    for setup_name, pp_success, pp_msg, nc_path in successful_posts:
                        if nc_path and os.path.exists(nc_path):
                            nc_dest = os.path.join(str(OUTPUT_NC_NETWORK), os.path.basename(nc_path))
                            shutil.copy2(nc_path, nc_dest)
                            self.logger.info(f'{comp_id}: G-code file copied to network: {nc_dest}')
                except Exception as copy_e:
                    self.logger.warning(f'{comp_id}: Failed to copy G-code files to network: {str(copy_e)}')

            # Switch back to Design workspace so next order starts cleanly.
            self._switch_to_design_workspace(comp_id)

            # Success! (drawing_exported was set earlier, before CAM section)
            nc_msg = f'{len(successful_posts)} NC file(s) generated'
            if drawing_exported:
                nc_msg += ', drawing exported'
            self._record_cam_status(comp_id, component_type, expects_toolpath,
                                    produced_toolpath, feature_summary, 'PASS', nc_msg)
            self.logger.info(f'{comp_id}: All operations complete - {nc_msg}')

            return (True, f'{comp_id}: Complete - {nc_msg}'), (drilling_data, drilling_paired_data)
            
        except Exception as e:
            comp_id_fallback = 'unknown'
            try:
                comp_id_data = component.get('id', ['unknown', 'string', ''])
                if isinstance(comp_id_data, list):
                    comp_id_fallback = comp_id_data[0]
                else:
                    comp_id_fallback = comp_id_data
            except Exception:
                pass
            self.logger.exception(f'Component processing failed: {comp_id_fallback}')
            return (False, f'{comp_id_fallback}: Exception: {str(e)}'), (None, None)
    
    def _switch_to_design_workspace(self, comp_id: str) -> None:
        """Switch back to the Design workspace so the next order starts cleanly."""
        try:
            design_workspace = self.app.userInterface.workspaces.itemById('FusionSolidEnvironment')
            if design_workspace:
                design_workspace.activate()
                time.sleep(1.0)
                self.logger.info(f'{comp_id}: Switched back to Design workspace')
        except Exception as ws_err:
            self.logger.warning(f'{comp_id}: Failed to switch back to Design workspace: {ws_err}')

    def _expects_toolpath(self, component_type: str, comp_id: str) -> Tuple[bool, str]:
        """
        Determine whether a component is EXPECTED to produce a CAM toolpath,
        based on its derived model parameters (the authoritative source).

        Doors:  any rabbeting or notching feature active.
        Stiles: any rabbeting feature active.
        Panels: any notching feature active OR any cutout present.

        Returns (expects_toolpath, human_readable_feature_summary).
        """
        try:
            design = self.get_current_design()
            if not design:
                self.logger.warning(f'{comp_id}: Could not access design for toolpath expectation; assuming expected')
                return True, 'unknown (no design access)'

            pm = ParameterManager(design)

            def _num(name):
                p = pm.user_parameters.itemByName(name)
                if p is None:
                    return 0.0
                try:
                    return float(p.value)
                except Exception:
                    return 0.0

            if component_type == ModelManager.DOOR:
                feats = ['left_interior_rabbeting', 'left_exterior_rabbeting',
                         'right_interior_rabbeting', 'right_exterior_rabbeting',
                         'bottom_left_notching', 'bottom_right_notching',
                         'top_left_notching', 'top_right_notching']
                active = [f for f in feats if _num(f) != 0]
                return (len(active) > 0), (', '.join(active) if active else 'none')

            elif component_type == ModelManager.STILE:
                feats = ['left_interior_rabbeting', 'left_exterior_rabbeting',
                         'right_interior_rabbeting', 'right_exterior_rabbeting']
                active = [f for f in feats if _num(f) != 0]
                return (len(active) > 0), (', '.join(active) if active else 'none')

            elif component_type == ModelManager.PANEL:
                notch_feats = ['notching_front_edge_bottom', 'notching_back_edge_bottom',
                               'notching_front_edge_top', 'notching_back_edge_top']
                active = [f for f in notch_feats if _num(f) != 0]
                if _num('cutout_A_width') > 0 and _num('cutout_A_height') > 0:
                    active.append('cutout_A')
                if _num('cutout_B_width') > 0 and _num('cutout_B_height') > 0:
                    active.append('cutout_B')
                
                # Cross-reference: check cutout TEXT params as fallback.
                # If cutout_A text is non-empty but derived dims are zero,
                # still report as expected so validation catches the mismatch.
                if 'cutout_A' not in active:
                    ca = pm.user_parameters.itemByName('cutout_A')
                    if ca:
                        try:
                            ca_expr = ca.expression
                            ca_text = ca_expr[1:-1].strip() if ca_expr.startswith("'") and ca_expr.endswith("'") else ca_expr.strip()
                            if ca_text:
                                active.append('cutout_A(text)')
                                self.logger.warning(f'{comp_id}: _expects_toolpath: cutout_A text="{ca_text}" but derived dims=0')
                        except Exception:
                            pass
                if 'cutout_B' not in active:
                    cb = pm.user_parameters.itemByName('cutout_B')
                    if cb:
                        try:
                            cb_expr = cb.expression
                            cb_text = cb_expr[1:-1].strip() if cb_expr.startswith("'") and cb_expr.endswith("'") else cb_expr.strip()
                            if cb_text:
                                active.append('cutout_B(text)')
                                self.logger.warning(f'{comp_id}: _expects_toolpath: cutout_B text="{cb_text}" but derived dims=0')
                        except Exception:
                            pass
                
                return (len(active) > 0), (', '.join(active) if active else 'none')

            self.logger.warning(f'{comp_id}: Unknown component type "{component_type}" for toolpath expectation; assuming expected')
            return True, 'unknown component type'

        except Exception as e:
            self.logger.warning(f'{comp_id}: _expects_toolpath failed ({e}); assuming toolpath expected')
            return True, f'unknown (error: {e})'

    def _record_cam_status(self, comp_id: str, component_type: str, expects: bool,
                           produced: bool, features: str, result: str, detail: str) -> None:
        """Record a per-component CAM validation result for the end-of-order report."""
        try:
            if not hasattr(self, '_cam_report') or self._cam_report is None:
                self._cam_report = []
            self._cam_report.append({
                'comp_id': comp_id,
                'type': component_type,
                'expects': expects,
                'produced': produced,
                'features': features,
                'result': result,
                'detail': detail,
            })
        except Exception:
            pass

    def _build_cam_report(self) -> str:
        """Build a human-readable CAM validation report for the completed order."""
        report = getattr(self, '_cam_report', None)
        if not report:
            return ''
        passed = [r for r in report if r['result'] == 'PASS']
        failed = [r for r in report if r['result'] == 'FAIL']
        with_gcode = [r for r in passed if r['produced']]

        lines = []
        lines.append('CAM Validation Report:')
        lines.append(f'  {len(passed)}/{len(report)} components passed CAM validation '
                     f'({len(with_gcode)} produced G-code, {len(passed) - len(with_gcode)} correctly had none)')
        if failed:
            lines.append(f'  {len(failed)} component(s) failed CAM validation:')
            for r in failed:
                lines.append(f'    {r["comp_id"]} ({r["type"]}): {r["detail"]} '
                             f'[expected toolpath={r["expects"]}, produced={r["produced"]}, features={r["features"]}]')
        return '\n'.join(lines)

    def _archive_order_outputs(self, order_id: str, timestamp: str) -> None:
        """
        Create timestamped snapshot copies of this order's per-output-type folders.

        The latest files remain in 'base/{order_id}'. In addition, a timestamped
        archive copy is created at 'base/{order_id} {timestamp}' for each output
        type (g-code, drawings, parameters, models), so each run is preserved.
        """
        if not timestamp:
            from datetime import datetime as _dt
            timestamp = _dt.now().strftime('%b %#d %Y - %H%M')
        try:
            import shutil
            from config import OUTPUT_GCODE, OUTPUT_PARAMETERS, OUTPUT_MODELS
            # (base_dir, label). Drawings live under '<gcode>/drawings'.
            output_bases = [
                (str(OUTPUT_GCODE), 'g-code'),
                (os.path.join(str(OUTPUT_GCODE), 'drawings'), 'drawings'),
                (str(OUTPUT_PARAMETERS), 'parameters'),
                (str(OUTPUT_MODELS), 'models'),
            ]
            for base, label in output_bases:
                try:
                    src = os.path.join(base, order_id)
                    if not os.path.isdir(src):
                        continue
                    dest = os.path.join(base, f'{order_id} {timestamp}')
                    if os.path.exists(dest):
                        shutil.rmtree(dest, ignore_errors=True)
                    shutil.copytree(src, dest)
                    self.logger.info(f'Archived {label} output snapshot: {dest}')
                except Exception as e:
                    self.logger.warning(f'Failed to archive {label} output for {order_id}: {e}')
        except Exception as e:
            self.logger.warning(f'Output archiving failed for {order_id}: {e}')

    def _apply_cutout_parameters(self, param_mgr, cutout_value: Optional[str], comp_id: str) -> Tuple[bool, str]:
        """
        Apply cutout values to a panel component by setting the cutout_A and cutout_B
        text parameters on the model.
        
        The input cutout value from JSON can be:
          - None / "null" / "" -> no cutout (both params empty)
          - "B-354"           -> single cutout in cutout_A, cutout_B empty
          - "B-354 & B-386"   -> split into cutout_A="B-354", cutout_B="B-386"
        
        Production uses '&' as separator. Test JSONs may use '+'.
        
        Args:
            param_mgr: ParameterManager instance for the active design
            cutout_value: Raw cutout string from input JSON, or None
            comp_id: Component ID for logging
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Parse the cutout value into up to two parts
            cutout_a = ''
            cutout_b = ''
            
            if cutout_value and cutout_value != 'null' and cutout_value.strip():
                # Production uses '&' as separator, test JSONs may use '+'
                # Try '&' first (production format), fall back to '+'
                if '&' in cutout_value:
                    parts = [p.strip() for p in cutout_value.split('&')]
                elif '+' in cutout_value:
                    parts = [p.strip() for p in cutout_value.split('+')]
                else:
                    parts = [cutout_value.strip()]
                
                # Filter out empty parts
                parts = [p for p in parts if p]
                if len(parts) >= 1:
                    cutout_a = parts[0]
                if len(parts) >= 2:
                    cutout_b = parts[1]
            
            self.logger.info(f'{comp_id}: Setting cutout params: cutout_A="{cutout_a}", cutout_B="{cutout_b}"')
            
            # Set cutout_A text parameter (wrap in single quotes for Fusion text params)
            success1, msg1 = param_mgr.update_parameter('cutout_A', f"'{cutout_a}'")
            if not success1:
                return False, f"Failed to set cutout_A: {msg1}"
            
            # Set cutout_B text parameter
            success2, msg2 = param_mgr.update_parameter('cutout_B', f"'{cutout_b}'")
            if not success2:
                return False, f"Failed to set cutout_B: {msg2}"
            
            if cutout_a or cutout_b:
                applied = ' + '.join(filter(None, [cutout_a, cutout_b]))
                return True, f"Applied cutout parameters: {applied}"
            else:
                return True, "Cleared cutout parameters (no cutout)"
            
        except Exception as e:
            return False, f"Failed to apply cutout parameters: {str(e)}"
    
    def _build_stile_setup_sequence(self, component_params: Dict, setup_names: list, comp_id: str, drilling_paired_data: dict = None) -> Optional[list]:
        """
        Build the Anderson handling setup posting sequence for 3X82/3X86 stiles.
        
        Selects which CAM toolpath setup(s) to post based on the number of doors
        (left/right) and their swing direction (in/out).  The same logic applies
        to both 3082 and 3086 series stiles.
        
        Available CAM setups in the stile model:
          "Left Rabbet - Out G57"
          "Left Rabbet - Out G59"
          "Left Rabbet - In G57"
          "Left Rabbet - In G59"
          "Right Rabbet - Out G57"
          "Right Rabbet - Out G59"
          "Right Rabbet - In G57"
          "Right Rabbet - In G59"
        
        Selection rules:
        
        Single door (left only):
          Out → Left Rabbet - Out G57
          In  → Left Rabbet - In G59
        
        Single door (right only):
          Out → Right Rabbet - Out G59
          In  → Right Rabbet - In G57
        
        Two doors (ordering rules based on drilling):
          1. Rabbeting on both sides, NO drilling → Left side rabbet first
          2. Drilling on ONE side only, rabbeting on both → Side WITH drilling first
          3. Drilling on BOTH sides → Side with FlipRotate=3 (first face at drill machine) first
        
        The setup SELECTION (which setup name) is still determined by swing direction.
        The ordering rules above only determine which side's toolpath comes first in G-code.
        
        Args:
            component_params: The component's parameters dict (JSON + model-derived)
            setup_names: List of CAM setup names currently in the model
            comp_id: Component ID for logging
            drilling_paired_data: Optional drilling output data containing FlipRotate values
            
        Returns:
            Ordered list of setup names to post (1 or 2 entries), or None
            to fall back to default behaviour (post all with toolpaths once).
        """
        try:
            # Helper to extract param value from [value, type, description] format
            def _val(key, default=None):
                data = component_params.get(key)
                if data is None:
                    return default
                return data[0] if isinstance(data, list) else data
            
            # Safe bool conversion: handles bool, int, float, and string "0"/"1"/"true"/"false"
            # (plain bool("0") returns True in Python — this avoids that trap)
            def _to_bool(val):
                if val is None:
                    return False
                if isinstance(val, bool):
                    return val
                if isinstance(val, (int, float)):
                    return val != 0
                s = str(val).strip().lower()
                return s not in ('0', 'false', 'no', 'none', 'null', '')
            
            series_id = str(_val('series_id', ''))
            # Normalize series code: the 2nd digit is a generation indicator
            # (e.g. '3186' -> '3086', '3182' -> '3082') irrelevant to model selection.
            _series_match = re.search(r'(3\d{3})', series_id)
            normalized_code = ''
            if _series_match:
                _code = _series_match.group(1)
                normalized_code = _code[0] + '0' + _code[2:]
            
            is_3082 = normalized_code in ('3082', '3081')
            is_3086 = normalized_code == '3086'
            
            if not is_3082 and not is_3086:
                self.logger.info(f'{comp_id}: Series "{series_id}" (normalized: {normalized_code}) is not 3082/3086, skipping stile sequence logic')
                return None
            
            left_has_door = _to_bool(_val('left_side_door', 0))
            right_has_door = _to_bool(_val('right_side_door', 0))
            num_doors = int(left_has_door) + int(right_has_door)
            
            if num_doors == 0:
                self.logger.info(f'{comp_id}: No doors on stile, no rabbeting needed - skip G-code')
                return []
            
            # Swing direction: O/S=True (outswing), I/S=False (inswing)
            ld_outswing = _to_bool(_val('LD_swinging_out', 0)) if left_has_door else None
            rd_outswing = _to_bool(_val('RD_swinging_out', 0)) if right_has_door else None
            
            # Helper to find exact setup name from model
            def _normalize(s):
                """Collapse '- Out - G57' vs '- Out G57' differences."""
                return re.sub(r'\s*-\s*', ' ', s).lower().strip()
            
            def _find_setup(target_name):
                """Find a setup name matching the target (case-insensitive, dash-tolerant)."""
                target_lower = target_name.lower()
                target_norm = _normalize(target_name)
                for n in setup_names:
                    if n.lower() == target_lower:
                        return n
                # Normalized match (ignores dash differences)
                for n in setup_names:
                    if _normalize(n) == target_norm:
                        return n
                # Fallback: partial match
                for n in setup_names:
                    if target_lower in n.lower():
                        return n
                return None
            
            # --- Toolpath selection logic ---
            if num_doors == 1:
                if left_has_door:
                    if ld_outswing:
                        # Left door only, swinging out
                        sequence = [_find_setup('Left Rabbet - Out G57')]
                    else:
                        # Left door only, swinging in
                        sequence = [_find_setup('Left Rabbet - In G59')]
                else:
                    if rd_outswing:
                        # Right door only, swinging out
                        sequence = [_find_setup('Right Rabbet - Out G59')]
                    else:
                        # Right door only, swinging in
                        sequence = [_find_setup('Right Rabbet - In G57')]
                handling = 'single setup'
                
            elif num_doors == 2:
                # --- Determine which setup each side uses (based on swing direction) ---
                # Left side setup selection
                if ld_outswing:
                    left_setup_g57 = _find_setup('Left Rabbet - Out G57')
                    left_setup_g59 = _find_setup('Left Rabbet - Out G59')
                else:
                    left_setup_g57 = _find_setup('Left Rabbet - In G57')
                    left_setup_g59 = _find_setup('Left Rabbet - In G59')
                
                # Right side setup selection
                if rd_outswing:
                    right_setup_g57 = _find_setup('Right Rabbet - Out G57')
                    right_setup_g59 = _find_setup('Right Rabbet - Out G59')
                else:
                    right_setup_g57 = _find_setup('Right Rabbet - In G57')
                    right_setup_g59 = _find_setup('Right Rabbet - In G59')
                
                # --- Same-face rabbeting (both swing same direction) ---
                # Original ordering: G57 first, Rotate 180°, G59 second
                if ld_outswing == rd_outswing:
                    if not ld_outswing:
                        # Both in-swing (interior rabbeting both sides)
                        # G57 = right rabbet, G59 = left rabbet
                        sequence = [
                            _find_setup('Right Rabbet - In G57'),
                            _find_setup('Left Rabbet - In G59')
                        ]
                        handling = 'both in-swing'
                    else:
                        # Both out-swing (exterior rabbeting both sides)
                        # G57 = left rabbet, G59 = right rabbet
                        sequence = [
                            _find_setup('Left Rabbet - Out G57'),
                            _find_setup('Right Rabbet - Out G59')
                        ]
                        handling = 'both out-swing'
                else:
                    # --- Opposite-face rabbeting (one interior, one exterior) ---
                    # Determine setups and G-code assignment
                    if not ld_outswing and rd_outswing:
                        # Left in, Right out → both at G59
                        left_setup = left_setup_g59
                        right_setup = right_setup_g59
                    else:
                        # Left out, Right in → both at G57
                        left_setup = left_setup_g57
                        right_setup = right_setup_g57
                    
                    # Determine ORDER based on drilling flags
                    li_drilling = _to_bool(_val('left_interior_drilling', 0))
                    le_drilling = _to_bool(_val('left_exterior_drilling', 0))
                    ri_drilling = _to_bool(_val('right_interior_drilling', 0))
                    re_drilling = _to_bool(_val('right_exterior_drilling', 0))
                    
                    left_has_drilling = li_drilling or le_drilling
                    right_has_drilling = ri_drilling or re_drilling
                    
                    self.logger.info(
                        f'{comp_id}: Opposite-face 2-door drilling flags: '
                        f'LI={li_drilling}, LE={le_drilling}, RI={ri_drilling}, RE={re_drilling}, '
                        f'left_has_drilling={left_has_drilling}, right_has_drilling={right_has_drilling}'
                    )
                    
                    if not left_has_drilling and not right_has_drilling:
                        # Case 1: No drilling on either side
                        # 3082 → left side first; 3086 → right side first
                        if is_3086:
                            sequence = [right_setup, left_setup]
                            handling = 'opposite-face no drilling, right first (3086)'
                        else:
                            sequence = [left_setup, right_setup]
                            handling = 'opposite-face no drilling, left first (3082)'
                        
                    elif left_has_drilling and not right_has_drilling:
                        # Case 2: Drilling on left only → left side first
                        sequence = [left_setup, right_setup]
                        handling = 'opposite-face drilling left only, left first'
                        
                    elif right_has_drilling and not left_has_drilling:
                        # Case 2: Drilling on right only → right side first
                        sequence = [right_setup, left_setup]
                        handling = 'opposite-face drilling right only, right first'
                        
                    else:
                        # Case 3: Drilling on BOTH sides → use FlipRotate to determine order
                        # FlipRotate=3 = exterior face = processed FIRST at drill machine
                        # FlipRotate=4 = interior face = processed SECOND
                        left_fr_value = 4 if li_drilling else 3
                        right_fr_value = 4 if ri_drilling else 3
                        
                        self.logger.info(
                            f'{comp_id}: FlipRotate determination: left={left_fr_value}, right={right_fr_value}'
                        )
                        
                        if left_fr_value == 3:
                            left_first = True
                        elif right_fr_value == 3:
                            left_first = False
                        else:
                            self.logger.warning(f'{comp_id}: Both sides have FlipRotate=4, defaulting to left first')
                            left_first = True
                        
                        if left_first:
                            sequence = [left_setup, right_setup]
                            handling = 'opposite-face drilling both, left first (FlipRotate=3 on left)'
                        else:
                            sequence = [right_setup, left_setup]
                            handling = 'opposite-face drilling both, right first (FlipRotate=3 on right)'
            else:
                return None
            
            # Log the decision
            self.logger.info(
                f'{comp_id}: Stile sequence logic: series={series_id}, '
                f'doors={num_doors}, '
                f'LD_swing={"O/S" if ld_outswing else "I/S" if ld_outswing is not None else "N/A"}, '
                f'RD_swing={"O/S" if rd_outswing else "I/S" if rd_outswing is not None else "N/A"}, '
                f'handling={handling}'
            )
            
            # Validate we found all setups we need
            missing = [s for s in sequence if s is None]
            if missing:
                self.logger.warning(f'{comp_id}: Could not find {len(missing)} required setup(s), falling back to default')
                return None
            
            self.logger.info(f'{comp_id}: Anderson handling = {handling}, sequence = {sequence}')
            return sequence if sequence else None
            
        except Exception as e:
            self.logger.warning(f'{comp_id}: Failed to build stile setup sequence: {e}')
            return None
    
    def _build_panel_setup_sequence(self, component_params: Dict, setup_names: list, comp_id: str) -> Optional[list]:
        """
        Determine which CAM setup to post for a panel based on orientation,
        or return [] if no features (notches/cutouts) are present.
        
        Selection rules:
          No features at all → [] (skip G-code entirely)
          Height >= Width → "Setup Back Bottom Corner G58"
          Width  >  Height → "Setup Back Top Corner G58"
        
        Feature detection (from derived model parameters):
          - Notching: notching_front_edge_bottom, notching_back_edge_bottom,
                      notching_front_edge_top, notching_back_edge_top (any != 0)
          - Cutouts: cutout_A_width > 0 AND cutout_A_height > 0 (for A),
                     cutout_B_width > 0 AND cutout_B_height > 0 (for B)
        
        Args:
            component_params: Merged dict of JSON params + derived model params
            setup_names: List of CAM setup names currently in the model
            comp_id: Component ID for logging
            
        Returns:
            List with single setup name, [] if no features, or None to fall back.
        """
        try:
            def _val(key, default=None):
                data = component_params.get(key)
                if data is None:
                    return default
                return data[0] if isinstance(data, list) else data
            
            height = float(_val('component_height', 0))
            width = float(_val('component_width', 0))
            
            if height == 0 and width == 0:
                self.logger.warning(f'{comp_id}: Both height and width are 0, falling back to default')
                return None
            
            # Check if any features (notches or cutouts) are present using
            # the derived parameters read from the Fusion model.
            notch_front_bottom = float(_val('notching_front_edge_bottom', 0)) != 0
            notch_back_bottom = float(_val('notching_back_edge_bottom', 0)) != 0
            notch_front_top = float(_val('notching_front_edge_top', 0)) != 0
            notch_back_top = float(_val('notching_back_edge_top', 0)) != 0
            has_notching = notch_front_bottom or notch_back_bottom or notch_front_top or notch_back_top
            
            cutout_a_w = float(_val('cutout_A_width', 0))
            cutout_a_h = float(_val('cutout_A_height', 0))
            cutout_b_w = float(_val('cutout_B_width', 0))
            cutout_b_h = float(_val('cutout_B_height', 0))
            has_cutout_a = cutout_a_w > 0 and cutout_a_h > 0
            has_cutout_b = cutout_b_w > 0 and cutout_b_h > 0
            
            # Cross-reference: check cutout TEXT parameters as a fallback.
            # If the input JSON had a cutout (stored as cutout_A/cutout_B text
            # params on the model) but derived dimensions are zero, the model's
            # derivation failed to update. In that case, still treat the cutout
            # as present so we don't skip G-code for a panel that has cutout geometry.
            try:
                design = self.get_current_design()
                if design and not has_cutout_a:
                    ca_param = design.userParameters.itemByName('cutout_A')
                    if ca_param:
                        ca_expr = ca_param.expression
                        ca_text = ca_expr[1:-1].strip() if ca_expr.startswith("'") and ca_expr.endswith("'") else ca_expr.strip()
                        if ca_text:
                            self.logger.warning(f'{comp_id}: cutout_A text="{ca_text}" but derived dims=0 — forcing has_cutout_a=True')
                            has_cutout_a = True
                if design and not has_cutout_b:
                    cb_param = design.userParameters.itemByName('cutout_B')
                    if cb_param:
                        cb_expr = cb_param.expression
                        cb_text = cb_expr[1:-1].strip() if cb_expr.startswith("'") and cb_expr.endswith("'") else cb_expr.strip()
                        if cb_text:
                            self.logger.warning(f'{comp_id}: cutout_B text="{cb_text}" but derived dims=0 — forcing has_cutout_b=True')
                            has_cutout_b = True
            except Exception as e:
                self.logger.warning(f'{comp_id}: cutout text cross-reference failed: {e}')
            
            has_cutouts = has_cutout_a or has_cutout_b
            
            self.logger.info(f'{comp_id}: Panel features: notching={has_notching} '
                           f'(FB={notch_front_bottom}, BB={notch_back_bottom}, '
                           f'FT={notch_front_top}, BT={notch_back_top}), '
                           f'cutouts={has_cutouts} (A={has_cutout_a} [{cutout_a_w}x{cutout_a_h}], '
                           f'B={has_cutout_b} [{cutout_b_w}x{cutout_b_h}])')
            
            if not has_notching and not has_cutouts:
                self.logger.info(f'{comp_id}: No panel features (no notching, no cutouts), skipping G-code')
                return []
            
            def _find_setup(target_name):
                target_lower = target_name.lower()
                for n in setup_names:
                    if n.lower() == target_lower:
                        return n
                for n in setup_names:
                    if target_lower in n.lower():
                        return n
                return None
            
            if height >= width:
                setup_name = 'Setup Back Bottom Corner G58'
                orientation = f'height ({height}) >= width ({width})'
            else:
                setup_name = 'Setup Back Top Corner G58'
                orientation = f'width ({width}) > height ({height})'
            
            found = _find_setup(setup_name)
            if found is None:
                self.logger.warning(f'{comp_id}: Could not find setup "{setup_name}", falling back to default')
                return None
            
            self.logger.info(f'{comp_id}: Panel setup selection: {orientation} -> {found}')
            return [found]
            
        except Exception as e:
            self.logger.warning(f'{comp_id}: Failed to build panel setup sequence: {e}')
            return None
    
    def _build_door_setup_sequence(self, component_params: Dict, setup_names: list, comp_id: str) -> Optional[list]:
        """
        Determine which CAM setups to post for a door based on feature flags.
        
        The door model has 8 setups:
          Setup 1 - G57: Left Interior Rabbet, Left Bottom Notch, Left Top Notch
          Setup 2 - G59: Left Interior Rabbet, Left Bottom Notch, Left Top Notch
          Setup 3 - G57: Left Exterior Rabbet, Left Bottom Notch, Left Top Notch
          Setup 4 - G59: Left Exterior Rabbet, Left Bottom Notch, Left Top Notch
          Setup 5 - G57: Right Interior Rabbet, Right Bottom Notch, Right Top Notch
          Setup 6 - G59: Right Interior Rabbet, Right Bottom Notch, Right Top Notch
          Setup 7 - G57: Right Exterior Rabbet, Right Bottom Notch, Right Top Notch
          Setup 8 - G59: Right Exterior Rabbet, Right Bottom Notch, Right Top Notch
        
        Selection rules based on door_swinging_out:
        
        door_swinging_out == 1:
          Right only  → right side setup at G57
          Left only   → left side setup at G59
          Both sides  → left at G59, then right at G57
          
        door_swinging_out == 0:
          Right only  → right side setup at G59
          Left only   → left side setup at G57
          Both sides  → left at G57, then right at G59
        
        Within each side, the specific setup is chosen based on which rabbeting
        type is active (interior vs exterior). If no rabbet is active but notches
        are, the interior rabbet setup is used (notch toolpaths are the same in
        both interior and exterior setups for a given side+G-code).
        
        If no features are present on either side, returns [] to skip G-code.
        
        Args:
            component_params: The component's parameters dict from the order JSON
            setup_names: List of CAM setup names currently in the model
            comp_id: Component ID for logging
            
        Returns:
            Ordered list of setup names to post, [] if no features, or None to fall back.
        """
        try:
            def _val(key, default=None):
                data = component_params.get(key)
                if data is None:
                    return default
                return data[0] if isinstance(data, list) else data
            
            def _to_bool(val):
                if val is None:
                    return False
                if isinstance(val, bool):
                    return val
                if isinstance(val, (int, float)):
                    return val != 0
                s = str(val).strip().lower()
                return s not in ('0', 'false', 'no', 'none', 'null', '')
            
            door_swinging_out = _to_bool(_val('door_swinging_out', 0))
            
            left_int_rabbet = _to_bool(_val('left_interior_rabbeting', 0))
            left_ext_rabbet = _to_bool(_val('left_exterior_rabbeting', 0))
            right_int_rabbet = _to_bool(_val('right_interior_rabbeting', 0))
            right_ext_rabbet = _to_bool(_val('right_exterior_rabbeting', 0))
            bottom_left_notch = _to_bool(_val('bottom_left_notching', 0))
            bottom_right_notch = _to_bool(_val('bottom_right_notching', 0))
            top_left_notch = _to_bool(_val('top_left_notching', 0))
            top_right_notch = _to_bool(_val('top_right_notching', 0))
            
            # Determine which sides have any features
            left_has_features = left_int_rabbet or left_ext_rabbet or bottom_left_notch or top_left_notch
            right_has_features = right_int_rabbet or right_ext_rabbet or bottom_right_notch or top_right_notch
            
            self.logger.info(
                f'{comp_id}: Door features: swing_out={door_swinging_out}, '
                f'left=[int_rab={left_int_rabbet}, ext_rab={left_ext_rabbet}, '
                f'bot_notch={bottom_left_notch}, top_notch={top_left_notch}], '
                f'right=[int_rab={right_int_rabbet}, ext_rab={right_ext_rabbet}, '
                f'bot_notch={bottom_right_notch}, top_notch={top_right_notch}]'
            )
            
            if not left_has_features and not right_has_features:
                self.logger.info(f'{comp_id}: No door features present, skipping G-code')
                return []
            
            def _find_setup(target_name):
                target_lower = target_name.lower()
                for n in setup_names:
                    if n.lower() == target_lower:
                        return n
                for n in setup_names:
                    if target_lower in n.lower():
                        return n
                return None
            
            # Determine which setup to use for each side based on rabbet type.
            # If only notches (no rabbet), use interior setup (notches are same in both).
            def _get_left_setup(g_code: str) -> Optional[str]:
                if left_ext_rabbet:
                    if g_code == 'G57':
                        return _find_setup('Setup 3 - G57')
                    else:
                        return _find_setup('Setup 4 - G59')
                else:
                    # Interior rabbet, or notch-only (use interior setup)
                    if g_code == 'G57':
                        return _find_setup('Setup 1 - G57')
                    else:
                        return _find_setup('Setup 2 - G59')
            
            def _get_right_setup(g_code: str) -> Optional[str]:
                if right_ext_rabbet:
                    if g_code == 'G57':
                        return _find_setup('Setup 7 - G57')
                    else:
                        return _find_setup('Setup 8 - G59')
                else:
                    # Interior rabbet, or notch-only (use interior setup)
                    if g_code == 'G57':
                        return _find_setup('Setup 5 - G57')
                    else:
                        return _find_setup('Setup 6 - G59')
            
            sequence = []
            
            if door_swinging_out:
                # Swinging out: left at G59, right at G57
                if left_has_features and not right_has_features:
                    # Left only at G59
                    sequence = [_get_left_setup('G59')]
                    handling = 'swing out, left only G59'
                elif right_has_features and not left_has_features:
                    # Right only at G57
                    sequence = [_get_right_setup('G57')]
                    handling = 'swing out, right only G57'
                else:
                    # Both sides: left G59 first, then right G57
                    sequence = [_get_left_setup('G59'), _get_right_setup('G57')]
                    handling = 'swing out, both sides (left G59 + right G57)'
            else:
                # Swinging in: left at G57, right at G59
                if left_has_features and not right_has_features:
                    # Left only at G57
                    sequence = [_get_left_setup('G57')]
                    handling = 'swing in, left only G57'
                elif right_has_features and not left_has_features:
                    # Right only at G59
                    sequence = [_get_right_setup('G59')]
                    handling = 'swing in, right only G59'
                else:
                    # Both sides: left G57 first, then right G59
                    sequence = [_get_left_setup('G57'), _get_right_setup('G59')]
                    handling = 'swing in, both sides (left G57 + right G59)'
            
            # Validate all setups found
            missing = [s for s in sequence if s is None]
            if missing:
                self.logger.warning(f'{comp_id}: Could not find {len(missing)} required door setup(s), falling back to default')
                return None
            
            self.logger.info(f'{comp_id}: Door setup selection: {handling}, sequence = {sequence}')
            return sequence
            
        except Exception as e:
            self.logger.warning(f'{comp_id}: Failed to build door setup sequence: {e}')
            return None
    
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
            
        except Exception:
            return None
