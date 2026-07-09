"""
Drawing Exporter for Fusion 360 Manufacturing Pipeline
Handles exporting drawings to PDF for door components.
"""

import adsk.core
import adsk.drawing
import os
import time
import threading
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Tuple
from logger import get_logger


class DrawingExporter:
    """Manages drawing export operations for door components"""
    
    def __init__(self, app: adsk.core.Application, output_base_dir: str = None):
        """
        Initialize drawing exporter.
        
        Args:
            app: Fusion Application object
            output_base_dir: Base directory for output (defaults to network OUTPUT_BASE from config)
        """
        self.app = app
        self.ui = app.userInterface
        self.logger = get_logger()
        self._drawing_opened_once = False  # Track if we've done the initial close/reopen
        
        # Set up output directory
        if output_base_dir is None:
            from config import OUTPUT_BASE
            output_base_dir = str(OUTPUT_BASE)
        
        self.output_base_dir = Path(output_base_dir)
        
        # Create drawings subfolder
        self.drawings_dir = self.output_base_dir / 'drawings'
        self.drawings_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache for drawing document reference
        self._drawing_doc = None
        self._drawing_data_file = None
        self._drawing_name = None  # Name of last opened drawing for re-finding
        self._consecutive_open_failures = 0
        self._max_consecutive_failures = 2  # Skip drawings after this many consecutive open failures
        
        self.logger.info(f'DrawingExporter initialized. Output: {self.drawings_dir}')
    
    def _reactivate_drawing(self) -> bool:
        """Re-find and activate the drawing document by name from app.documents.
        
        After doEvents() pumping, self._drawing_doc can become invalid because
        Fusion internally closes the drawing when switching back to Design workspace.
        This method scans open documents to find the drawing by name and re-activates it.
        
        Returns:
            True if drawing was found and activated, False otherwise
        """
        # First try the cached reference
        if self._drawing_doc:
            try:
                if self._drawing_doc.isValid:
                    self.logger.info(f'_reactivate_drawing: cached doc is valid, activating: {self._drawing_doc.name}')
                    self._drawing_doc.activate()
                    time.sleep(2.0)
                    return True
            except Exception:
                self.logger.info(f'_reactivate_drawing: cached doc invalid or error')
        
        # Cached ref is stale — scan app.documents by name
        if not self._drawing_name:
            self.logger.info(f'_reactivate_drawing: no drawing name cached, cannot re-find')
            return False
        
        self.logger.info(f'_reactivate_drawing: scanning documents for "{self._drawing_name}"...')
        for doc in self.app.documents:
            try:
                if doc.isValid and doc.name == self._drawing_name:
                    self.logger.info(f'_reactivate_drawing: found "{doc.name}", activating...')
                    doc.activate()
                    time.sleep(2.0)
                    # Update cached reference
                    self._drawing_doc = doc
                    return True
            except Exception as e:
                self.logger.info(f'_reactivate_drawing: error checking doc: {e}')
                continue
        
        self.logger.warning(f'_reactivate_drawing: drawing "{self._drawing_name}" not found in open documents')
        return False
    
    def find_drawing_in_hub(self, drawing_name: str, project_name: str = None, folder_name: str = "Assets") -> Optional[adsk.core.DataFile]:
        """
        Find a drawing document in Fusion Hub by name.
        
        Args:
            drawing_name: Name of the drawing (e.g., "3X8X-Door Drawing")
            project_name: Project name to search in (None = search all projects)
            folder_name: Folder name to search in (default: "Assets")
            
        Returns:
            DataFile object if found, None otherwise
        """
        try:
            data = self.app.data
            
            # Search through projects
            for proj in data.dataProjects.asArray():
                if project_name and proj.name != project_name:
                    continue
                
                self.logger.info(f'Searching project: {proj.name}')
                
                # Search root folder
                found = self._search_folder_for_drawing(proj.rootFolder, drawing_name)
                if found:
                    return found
                
                # Search subfolders
                for folder in proj.rootFolder.dataFolders.asArray():
                    if folder_name and folder.name != folder_name:
                        continue
                    
                    self.logger.info(f'Searching folder: {folder.name}')
                    found = self._search_folder_for_drawing(folder, drawing_name)
                    if found:
                        return found
                    
                    # Search nested folders
                    for subfolder in folder.dataFolders.asArray():
                        found = self._search_folder_for_drawing(subfolder, drawing_name)
                        if found:
                            return found
            
            self.logger.warning(f'Drawing not found: {drawing_name}')
            return None
            
        except Exception as e:
            self.logger.error(f'Error searching for drawing: {str(e)}')
            return None
    
    def _search_folder_for_drawing(self, folder: adsk.core.DataFolder, drawing_name: str) -> Optional[adsk.core.DataFile]:
        """Search a specific folder for a drawing by name."""
        try:
            for file in folder.dataFiles.asArray():
                # Check if file name matches (with or without "Drawing" suffix)
                if file.name == drawing_name or file.name.startswith(drawing_name):
                    # Verify it's a drawing file
                    if file.fileExtension == 'f2d' or 'Drawing' in file.name:
                        self.logger.info(f'Found drawing: {file.name} in {folder.name}')
                        return file
            return None
        except Exception as e:
            self.logger.warning(f'Error searching folder {folder.name}: {str(e)}')
            return None
    
    def open_drawing(self, data_file: adsk.core.DataFile, pre_opened_doc=None) -> Tuple[bool, Optional[adsk.drawing.DrawingDocument], str]:
        """
        Open a drawing document from Fusion Hub.
        
        Args:
            data_file: DataFile object for the drawing
            pre_opened_doc: Optional pre-opened Document (from startup cache).
                           If provided, activates it directly instead of calling
                           documents.open() which can hang on cloud drawings.
            
        Returns:
            Tuple of (success, DrawingDocument, message)
        """
        try:
            self.logger.info(f'=== open_drawing: {data_file.name} ===')
            self.logger.info(f'  data_file.id: {data_file.id}')
            try:
                self.logger.info(f'  data_file.versionNumber: {data_file.versionNumber}')
                self.logger.info(f'  data_file.fileExtension: {data_file.fileExtension}')
            except Exception as pex:
                self.logger.info(f'  (could not read DataFile props: {pex})')
            self.logger.info(f'  pre_opened_doc: {pre_opened_doc is not None}')
            self.logger.info(f'  documents.count: {self.app.documents.count}')
            self.logger.info(f'  consecutive_open_failures: {self._consecutive_open_failures}')
            
            # --- Fast path: use pre-opened document from startup cache ---
            if pre_opened_doc and pre_opened_doc.isValid:
                self.logger.info(f'Using pre-opened drawing document: {pre_opened_doc.name} (isValid={pre_opened_doc.isValid})')
                pre_opened_doc.activate()
                # Give Fusion time to transition to Drawing workspace (NO doEvents)
                time.sleep(3.0)
                
                # Verify the document is now active
                try:
                    active_name = self.app.activeDocument.name if self.app.activeDocument else 'None'
                    self.logger.info(f'Active document after activate: {active_name}')
                except Exception:
                    pass
                
                drawing_doc = adsk.drawing.DrawingDocument.cast(pre_opened_doc)
                if not drawing_doc:
                    self.logger.warning(f'Pre-opened document is not a DrawingDocument: {pre_opened_doc.name}')
                    self._drawing_doc = pre_opened_doc
                    self._drawing_name = data_file.name
                    self._drawing_data_file = data_file
                    return True, pre_opened_doc, f'Opened (not DrawingDocument): {data_file.name}'
                
                self._drawing_doc = drawing_doc
                self._drawing_name = data_file.name
                self._drawing_data_file = data_file
                self._consecutive_open_failures = 0
                self.logger.info(f'Pre-opened drawing activated: {data_file.name}')
                return True, drawing_doc, f'Drawing activated (pre-opened): {data_file.name}'
            
            # Check if drawing is already open in Fusion
            self.logger.info(f'Scanning {self.app.documents.count} open documents for drawing...')
            for i, doc in enumerate(self.app.documents):
                try:
                    doc_name = doc.name if doc.isValid else '(invalid)'
                    doc_id = doc.dataFile.id if (hasattr(doc, 'dataFile') and doc.dataFile) else 'no-dataFile'
                    self.logger.info(f'  doc[{i}]: name={doc_name}, id={doc_id}')
                except Exception:
                    self.logger.info(f'  doc[{i}]: (error reading properties)')
                if doc.name == data_file.name or (hasattr(doc, 'dataFile') and doc.dataFile and doc.dataFile.id == data_file.id):
                    self.logger.info(f'Drawing already open: {doc.name}')
                    
                    # Cast to DrawingDocument for access to drawing-specific API
                    drawing_doc = adsk.drawing.DrawingDocument.cast(doc)
                    if not drawing_doc:
                        self.logger.warning(f'Document {doc.name} is not a DrawingDocument, closing and reopening')
                        doc.close(False)
                        time.sleep(2.0)
                        break
                    
                    drawing_doc.activate()
                    time.sleep(0.5)
                    self._drawing_doc = drawing_doc
                    self._drawing_name = data_file.name
                    self._drawing_data_file = data_file
                    return True, drawing_doc, f'Drawing already open: {data_file.name}'
            
            # Check if we've had too many consecutive open failures (likely Fusion hang issue)
            if self._consecutive_open_failures >= self._max_consecutive_failures:
                self.logger.warning(
                    f'Skipping drawing open — {self._consecutive_open_failures} consecutive failures. '
                    f'Cloud drawing opens are hanging. Will retry on next order.'
                )
                return False, None, f'Skipping drawing (consecutive open failures: {self._consecutive_open_failures})'
            
            # DO NOT close cloud documents before opening the drawing.
            # Closing heavily-versioned cloud docs triggers internal
            # preDocumentClose/removeCollaborator events that poison Fusion's
            # state and cause subsequent documents.open() to hang indefinitely.
            # Multiple clean cloud docs can safely coexist.
            self.logger.info(f'Skipping doc cleanup — cloud docs stay open to avoid poisoning Fusion state')
            
            # Log detailed state right before the open call
            try:
                docs_before = self.app.documents.count
                self.logger.info(f'=== PRE-OPEN STATE ===')
                self.logger.info(f'  documents.count: {docs_before}')
                for di in range(docs_before):
                    try:
                        d = self.app.documents.item(di)
                        d_name = d.name if d.isValid else '(invalid)'
                        d_type = d.objectType if hasattr(d, 'objectType') else 'unknown'
                        self.logger.info(f'  doc[{di}]: {d_name} type={d_type}')
                    except Exception as de:
                        self.logger.info(f'  doc[{di}]: error={de}')
                try:
                    act_doc = self.app.activeDocument
                    self.logger.info(f'  activeDocument: {act_doc.name if act_doc else "None"}')
                    self.logger.info(f'  activeProduct: {self.app.activeProduct.objectType if self.app.activeProduct else "None"}')
                except Exception as ae:
                    self.logger.info(f'  active state error: {ae}')
                self.logger.info(f'  data_file to open: {data_file.name} (id={data_file.id})')
                self.logger.info(f'=== CALLING documents.open() NOW ===')
            except Exception as pre_e:
                self.logger.info(f'Pre-open state logging error: {pre_e}')
            
            # Open drawing on UI thread — synchronous call.
            # WARNING: On the VM, documents.open() for .f2d cloud drawings can
            # hang indefinitely due to Fusion's Drawing workspace subprocess.
            # If it hangs, the user must restart Fusion. The consecutive failure
            # counter will then skip drawing export for subsequent orders.
            # To avoid the hang entirely, open the drawing manually in Fusion
            # before starting the monitor — the scan above will detect it.
            open_start = time.time()
            
            try:
                doc = self.app.documents.open(data_file)
            except Exception as e:
                open_elapsed = time.time() - open_start
                self.logger.error(f'documents.open() raised after {open_elapsed:.1f}s: {e}')
                self._consecutive_open_failures += 1
                return False, None, f'documents.open() failed: {e}'
            
            open_elapsed = time.time() - open_start
            self.logger.info(f'documents.open() returned ({open_elapsed:.1f}s), docs after: {self.app.documents.count}')
            
            if not doc:
                self._consecutive_open_failures += 1
                self.logger.error(f'documents.open() returned None')
                return False, None, f'Failed to open drawing: {data_file.name}'
            
            self.logger.info(f'Returned doc: name={doc.name}, isValid={doc.isValid}')
            
            # Settle time — Fusion needs time to transition to Drawing workspace.
            # DO NOT call doEvents() here — it triggers Fusion's broken Drawing
            # subprocess to crash and close the drawing document.
            self.logger.info(f'Settling drawing after open (sleep only, no doEvents)...')
            time.sleep(5.0)
            self.logger.info(f'Settle-open complete')
            
            # Activate the drawing document
            self.logger.info(f'Activating drawing document...')
            doc.activate()
            self.logger.info(f'doc.activate() returned')
            
            # More settle time after activate for workspace transition.
            # NO doEvents() — just sleep.
            time.sleep(5.0)
            self.logger.info(f'Settle-activate complete')
            
            try:
                active_name = self.app.activeDocument.name if self.app.activeDocument else 'None'
                active_product = self.app.activeProduct.objectType if self.app.activeProduct else 'None'
                self.logger.info(f'After settle: activeDoc={active_name}, activeProduct={active_product}')
            except Exception as state_e:
                self.logger.info(f'After settle: could not read state: {state_e}')
            
            # Retry DrawingDocument cast with polling — workspace transition can
            # take additional time on the VM
            drawing_doc = None
            cast_timeout = 30
            cast_start = time.time()
            while time.time() - cast_start < cast_timeout:
                drawing_doc = adsk.drawing.DrawingDocument.cast(doc)
                if drawing_doc:
                    self.logger.info(f'DrawingDocument cast succeeded ({time.time()-cast_start:.1f}s)')
                    break
                # Also try casting activeProduct as a Drawing
                try:
                    active_drawing = adsk.drawing.Drawing.cast(self.app.activeProduct)
                    if active_drawing:
                        self.logger.info(f'activeProduct is a Drawing ({time.time()-cast_start:.1f}s)')
                        break
                except Exception:
                    pass
                # NO doEvents() — just sleep between retries
                time.sleep(2.0)
                self.logger.info(f'DrawingDocument cast retry ({time.time()-cast_start:.1f}s)...')
            
            if not drawing_doc:
                self.logger.warning(f'DrawingDocument cast failed after {cast_timeout}s — doc type: {doc.objectType if hasattr(doc, "objectType") else "unknown"}')
                # Still cache the doc — export_drawing_to_pdf uses activeProduct cast
                # which may succeed even if DrawingDocument cast on the doc fails
                self._drawing_doc = doc
                self._drawing_name = data_file.name
                self._drawing_data_file = data_file
                self._consecutive_open_failures = 0
                return True, doc, f'Opened (cast pending): {data_file.name}'
            
            self._drawing_doc = drawing_doc
            self._drawing_name = data_file.name
            self._drawing_data_file = data_file
            self._consecutive_open_failures = 0
            
            self.logger.info(f'Drawing opened successfully: {data_file.name} ({open_elapsed:.1f}s)')
            return True, drawing_doc, f'Opened drawing: {data_file.name}'
            
        except Exception as e:
            self.logger.error(f'Error opening drawing: {str(e)}')
            return False, None, f'Error opening drawing: {str(e)}'
    
    def _try_execute_update_command(self, wait_seconds: float = 10.0) -> bool:
        """
        Try to execute the drawing update/reference manager button by its command definition ID.
        Uses command IDs discovered from diagnostic logging of the Fusion 360 UI.
        Returns True if any command executed successfully.
        """
        ui = self.app.userInterface
        cmd_defs = ui.commandDefinitions
        
        # Command IDs discovered from diagnostic logging of Fusion 360 UI:
        # ReferenceManagerCmd = "Update Referenced model" button in QAT toolbar (THE button)
        # FusionDocUpdateCommand = "Get Latest" button in QAT toolbar
        candidate_ids = [
            'ReferenceManagerCmd',
            'FusionDocUpdateCommand',
            'PLM360DeepRefreshDocumentCommand',
            'GetAllLatestCmd',
            'UpdateAllLatestCmd',
        ]
        
        for cmd_id in candidate_ids:
            try:
                cmd_def = cmd_defs.itemById(cmd_id)
                if cmd_def:
                    self.logger.info(f'Found command: "{cmd_id}" ("{cmd_def.name}") - executing...')
                    cmd_def.execute()
                    # Wait for the command to complete (NO doEvents)
                    time.sleep(wait_seconds)
                    self.logger.info(f'Command "{cmd_id}" executed, waited {wait_seconds}s')
                    return True
            except Exception as e:
                self.logger.info(f'Command "{cmd_id}" failed: {str(e)}')
                continue
        
        return False
    
    def update_drawing_references(self, max_wait_seconds: int = 60) -> Tuple[bool, str]:
        """
        Update the drawing to reflect the latest model changes.
        
        Strategy:
        - FIRST call: Close and reopen the drawing to establish the correct
          reference to the in-memory model. This is needed because the cloud
          translation for the current save hasn't completed yet.
        - SUBSEQUENT calls: Just call updateAllReferences() on the already-open
          drawing. Since the model document is open in the same session with
          current parameters applied, Fusion picks up the in-memory geometry.
          This avoids the expensive close/reopen cycle that can trigger BREP
          entity errors and destabilize Fusion when done repeatedly.
        
        Args:
            max_wait_seconds: Maximum seconds to wait for the update to complete
        
        Returns:
            Tuple of (success, message)
        """
        try:
            # --- Fast path: drawing already open from a previous call ---
            if self._drawing_opened_once and self._drawing_doc:
                drawing_doc = adsk.drawing.DrawingDocument.cast(self._drawing_doc)
                if drawing_doc:
                    self.logger.info('Drawing already open from previous order, calling updateAllReferences()...')
                    return self._do_update_all_references(drawing_doc)
                else:
                    self.logger.warning('Cached drawing doc is no longer a valid DrawingDocument, will reopen')
                    self._drawing_opened_once = False
            
            if not self._drawing_data_file:
                if not self._drawing_doc:
                    return False, 'No drawing document or data file available'
                # If we have a doc but no data file, we can't close/reopen
                # Fall back to updateAllReferences on the open doc
                drawing_doc = adsk.drawing.DrawingDocument.cast(self._drawing_doc)
                if drawing_doc:
                    self.logger.info('No data file for close/reopen, using updateAllReferences...')
                    return self._do_update_all_references(drawing_doc)
                return False, 'Cannot update drawing without data file'
            
            # --- First-time update path ---
            # Previously this did a close/reopen cycle, but that calls
            # documents.open() which blocks 10+ minutes for cloud drawings.
            # updateAllReferences() alone works correctly — the model document
            # is already open in the same session with current parameters,
            # so Fusion picks up the in-memory geometry.
            if not self._drawing_doc:
                return False, 'No drawing document available for update'
            
            drawing_doc = adsk.drawing.DrawingDocument.cast(self._drawing_doc)
            if not drawing_doc:
                return False, 'Drawing document is not a valid DrawingDocument'
            
            self.logger.info('First drawing update: using updateAllReferences() (no close/reopen)...')
            self._log_reference_info(drawing_doc)
            self._drawing_opened_once = True
            return self._do_update_all_references(drawing_doc)
            
        except Exception as e:
            self.logger.error(f'Error updating drawing references: {str(e)}')
            return False, f'Error updating references: {str(e)}'
    
    def _do_update_all_references(self, drawing_doc) -> Tuple[bool, str]:
        """Call updateAllReferences() and wait for views to regenerate."""
        try:
            # Ensure drawing is the active document and workspace is ready
            try:
                if self.app.activeDocument != drawing_doc:
                    self.logger.info('Drawing not active, activating before updateAllReferences...')
                    drawing_doc.activate()
                    time.sleep(2.0)
            except Exception:
                pass
            
            # Brief pause to let Fusion finalize any pending workspace transition
            # NO doEvents() — it can kill the drawing document
            time.sleep(1.0)
            
            self.logger.info('Calling updateAllReferences()...')
            drawing_doc.updateAllReferences()
            
            # Poll doEvents to let Fusion regenerate drawing views.
            self.logger.info('Waiting for drawing views to regenerate...')
            for i in range(15):  # Up to ~15 seconds
                time.sleep(1.0)
                # NO doEvents() — just poll isUpToDate with sleep
                try:
                    if drawing_doc.isUpToDate:
                        self.logger.info(f'Drawing views regenerated after {i+1}s')
                        break
                except Exception:
                    pass
            
            self.logger.info('updateAllReferences() completed')
            self._log_reference_info(drawing_doc)
            
        except Exception as e:
            self.logger.warning(f'updateAllReferences() raised: {str(e)}')
        
        # Log final state
        try:
            is_up_to_date = drawing_doc.isUpToDate
            self.logger.info(f'Drawing isUpToDate after update: {is_up_to_date}')
        except Exception:
            pass
        
        return True, 'Drawing updated via updateAllReferences()'
    
    def _log_reference_info(self, drawing_doc):
        """Log drawing reference details for debugging."""
        try:
            refs = drawing_doc.documentReferences
            if refs:
                self.logger.info(f'Drawing references ({refs.count}):')
                for i in range(refs.count):
                    ref = refs.item(i)
                    ref_info = f'name={ref.name}' if hasattr(ref, 'name') else 'unknown'
                    try:
                        if hasattr(ref, 'isOutOfDate'):
                            ref_info += f', isOutOfDate={ref.isOutOfDate}'
                        if hasattr(ref, 'referencedDocument') and ref.referencedDocument:
                            ref_info += f', refDoc={ref.referencedDocument.name}'
                        if hasattr(ref, 'dataFile') and ref.dataFile:
                            ref_info += f', version=v{ref.dataFile.versionNumber}'
                        # Try to get latest version info
                        if hasattr(ref, 'dataFile') and ref.dataFile:
                            try:
                                latest = ref.dataFile.latestVersionNumber if hasattr(ref.dataFile, 'latestVersionNumber') else 'N/A'
                                ref_info += f', latestVersion={latest}'
                            except Exception:
                                pass
                        # Check all available properties/methods on the reference
                        ref_attrs = [a for a in dir(ref) if not a.startswith('_')]
                        ref_info += f', attrs={ref_attrs}'
                    except Exception as e:
                        ref_info += f', error={str(e)}'
                    self.logger.info(f'  Ref[{i}]: {ref_info}')
        except Exception as e:
            self.logger.info(f'Could not enumerate references: {str(e)}')
    
    def export_drawing_to_pdf(self, output_filename: str, order_folder: str = None) -> Tuple[bool, str, Optional[str]]:
        """
        Export the current drawing to PDF.
        
        Args:
            output_filename: Name for the output file (e.g., "1-D1-IBUS366574-drawing.pdf")
            order_folder: Optional subfolder within drawings dir for this order
            
        Returns:
            Tuple of (success, message, file_path)
        """
        try:
            # Re-activate drawing doc to ensure we're in Drawing workspace.
            # doEvents() calls during settle/update can switch active doc back
            # to the design model AND invalidate self._drawing_doc.
            # _reactivate_drawing() handles both cases by falling back to
            # scanning app.documents by name.
            self.logger.info(f'export_drawing_to_pdf: re-activating drawing...')
            self._reactivate_drawing()
            
            # Get the active drawing
            try:
                active_prod_type = self.app.activeProduct.objectType if self.app.activeProduct else 'None'
                active_doc_name = self.app.activeDocument.name if self.app.activeDocument else 'None'
                self.logger.info(f'export_drawing_to_pdf: activeProduct={active_prod_type}, activeDoc={active_doc_name}')
            except Exception:
                pass
            
            drawing = adsk.drawing.Drawing.cast(self.app.activeProduct)
            
            if not drawing:
                # One more attempt — re-activate by name and wait longer
                self.logger.warning('No active drawing on first check, re-activating and retrying...')
                self._reactivate_drawing()
                time.sleep(3.0)
                drawing = adsk.drawing.Drawing.cast(self.app.activeProduct)
            
            if not drawing:
                return False, 'No active drawing - cannot export PDF', None
            
            # Determine output path
            if order_folder:
                output_dir = self.drawings_dir / order_folder
                output_dir.mkdir(parents=True, exist_ok=True)
            else:
                output_dir = self.drawings_dir
            
            # Ensure filename has .pdf extension
            if not output_filename.lower().endswith('.pdf'):
                output_filename += '.pdf'
            
            output_path = output_dir / output_filename
            
            self.logger.info(f'Exporting drawing to PDF: {output_path}')
            
            # Get export manager
            export_mgr = drawing.exportManager
            
            # Fusion Drawings can crash when exporting directly to a UNC
            # network path. Export to a local temp file first, then copy.
            is_network_path = str(output_path).startswith('\\\\')
            if is_network_path:
                temp_dir = tempfile.mkdtemp(prefix='fusion_drawing_')
                local_export_path = Path(temp_dir) / output_filename
                self.logger.info(f'Network path detected — exporting to local temp: {local_export_path}')
            else:
                local_export_path = output_path
                temp_dir = None
            
            # Create PDF export options (always use local path)
            export_options = export_mgr.createPDFExportOptions(str(local_export_path))
            export_options.sheetsToExport = adsk.drawing.PDFSheetsExport.AllPDFSheetsExport
            export_options.useLineWeights = True
            
            # Execute export — wrap in try/except + retry because Fusion can
            # crash internally if drawing views aren't fully rendered yet
            self.logger.info('Executing PDF export...')
            try:
                export_mgr.execute(export_options)
            except Exception as export_err:
                self.logger.warning(f'PDF export failed on first attempt: {export_err}, retrying after settling...')
                # Wait longer to let drawing fully stabilize (NO doEvents)
                time.sleep(5.0)
                # Re-acquire export manager and options in case state was invalidated
                drawing = adsk.drawing.Drawing.cast(self.app.activeProduct)
                if not drawing:
                    if temp_dir:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    return False, f'Drawing lost after failed export: {export_err}', None
                export_mgr = drawing.exportManager
                export_options = export_mgr.createPDFExportOptions(str(local_export_path))
                export_options.sheetsToExport = adsk.drawing.PDFSheetsExport.AllPDFSheetsExport
                export_options.useLineWeights = True
                export_mgr.execute(export_options)
            
            # Verify file was created locally
            if not local_export_path.exists():
                if temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                return False, f'PDF export completed but file not found: {local_export_path}', None
            
            file_size = local_export_path.stat().st_size
            self.logger.info(f'PDF exported locally: {output_filename} ({file_size} bytes)')
            
            # Copy to network destination if needed
            if is_network_path:
                try:
                    shutil.copy2(str(local_export_path), str(output_path))
                    self.logger.info(f'PDF copied to network: {output_path}')
                except Exception as copy_err:
                    self.logger.error(f'Failed to copy PDF to network: {copy_err}')
                    # Return the local path so the file isn't lost
                    return True, f'Exported locally but network copy failed: {copy_err}', str(local_export_path)
                finally:
                    shutil.rmtree(temp_dir, ignore_errors=True)
            
            self.logger.info(f'Drawing exported: {output_filename} ({file_size} bytes)')
            return True, f'Exported drawing to {output_filename} ({file_size} bytes)', str(output_path)
            
        except Exception as e:
            return False, f'Error exporting drawing to PDF: {str(e)}', None
    
    def export_door_drawing(self, component_id: str, order_id: str, drawing_data_file: adsk.core.DataFile = None, pre_opened_doc=None) -> Tuple[bool, str, Optional[str]]:
        """
        Complete workflow to export a door drawing to PDF.
        Opens the drawing, updates references, and exports to PDF.
        
        Args:
            component_id: Component ID (e.g., "D1")
            order_id: Order ID (e.g., "IBUS366574")
            drawing_data_file: DataFile for the drawing (if None, will search for it)
            pre_opened_doc: Optional pre-opened Document from startup cache
            
        Returns:
            Tuple of (success, message, file_path)
        """
        try:
            # Find drawing if not provided
            if not drawing_data_file:
                drawing_data_file = self.find_drawing_in_hub("3X8X_Door_branch_B Drawing")
                if not drawing_data_file:
                    return False, 'Could not find door drawing in Fusion Hub', None
            
            # Open the drawing
            success, doc, msg = self.open_drawing(drawing_data_file, pre_opened_doc)
            if not success:
                return False, msg, None
            
            # Update references to get latest model changes
            success, msg = self.update_drawing_references()
            if not success:
                self.logger.warning(f'Reference update warning: {msg}')
                # Continue anyway - the drawing may still be usable
            
            # Let Fusion fully render the drawing views before exporting.
            # NO doEvents() — it kills the drawing document on the VM.
            self.logger.info('Settling before PDF export (sleep only)...')
            time.sleep(5.0)
            self.logger.info('Settle complete')
            
            self.logger.info('Starting PDF export (door)')
            
            # Export to PDF
            output_filename = f'1-{component_id}-{order_id}-drawing.pdf'
            success, msg, file_path = self.export_drawing_to_pdf(output_filename, order_id)
            
            return success, msg, file_path
            
        except Exception as e:
            return False, f'Error in door drawing export workflow: {str(e)}', None
    
    def export_stile_drawing(self, component_id: str, order_id: str, drawing_data_file: adsk.core.DataFile, pre_opened_doc=None) -> Tuple[bool, str, Optional[str]]:
        """
        Complete workflow to export a stile drawing to PDF.
        Opens the drawing, updates references, and exports to PDF.
        
        Unlike door drawings, stile drawings skip the close/reopen cycle
        to avoid pumping doEvents() which triggers PLM360 crash on dirty
        cloud documents. Instead, we just call updateAllReferences()
        directly on the already-open drawing.
        
        Args:
            component_id: Component ID (e.g., "S1")
            order_id: Order ID (e.g., "3X82_SV_0043")
            drawing_data_file: DataFile for the stile drawing
            pre_opened_doc: Optional pre-opened Document from startup cache
            
        Returns:
            Tuple of (success, message, file_path)
        """
        try:
            if not drawing_data_file:
                return False, 'No stile drawing DataFile provided', None
            
            # Open the drawing
            success, doc, msg = self.open_drawing(drawing_data_file, pre_opened_doc)
            if not success:
                return False, msg, None
            
            # Mark as already opened so update_drawing_references uses the
            # fast path (just updateAllReferences, no close/reopen cycle).
            # The close/reopen cycle calls documents.open() again which hangs
            # indefinitely for cloud drawings. updateAllReferences works because
            # the model doc is open in the same session with current params.
            self._drawing_opened_once = True
            
            # Update references to get latest model changes (fast path only)
            success, msg = self.update_drawing_references()
            if not success:
                self.logger.warning(f'Reference update warning: {msg}')
                # Continue anyway - the drawing may still be usable
            
            # Let Fusion fully render the drawing views before exporting.
            # NO doEvents() — it kills the drawing document on the VM.
            self.logger.info('Settling before PDF export (sleep only)...')
            time.sleep(5.0)
            self.logger.info('Settle complete')
            
            self.logger.info('Starting PDF export (stile)')
            
            # Export to PDF
            output_filename = f'1-{component_id}-{order_id}-drawing.pdf'
            success, msg, file_path = self.export_drawing_to_pdf(output_filename, order_id)
            
            return success, msg, file_path
            
        except Exception as e:
            return False, f'Error in stile drawing export workflow: {str(e)}', None
    
    def export_panel_drawing(self, component_id: str, order_id: str, drawing_data_file: adsk.core.DataFile, pre_opened_doc=None) -> Tuple[bool, str, Optional[str]]:
        """
        Complete workflow to export a panel drawing to PDF.
        Opens the drawing, updates references, and exports to PDF.
        
        Args:
            component_id: Component ID (e.g., "P1")
            order_id: Order ID (e.g., "XX8X_PV_0009")
            drawing_data_file: DataFile for the panel drawing
            pre_opened_doc: Optional pre-opened Document from startup cache
            
        Returns:
            Tuple of (success, message, file_path)
        """
        try:
            if not drawing_data_file:
                return False, 'No panel drawing DataFile provided', None
            
            # Open the drawing
            success, doc, msg = self.open_drawing(drawing_data_file, pre_opened_doc)
            if not success:
                return False, msg, None
            
            # Mark as already opened so update_drawing_references uses the
            # fast path (just updateAllReferences, no close/reopen cycle).
            self._drawing_opened_once = True
            
            # Update references to get latest model changes (fast path only)
            success, msg = self.update_drawing_references()
            if not success:
                self.logger.warning(f'Reference update warning: {msg}')
            
            # Let Fusion fully render the drawing views before exporting.
            # NO doEvents() — it kills the drawing document on the VM.
            self.logger.info('Settling before PDF export (sleep only)...')
            time.sleep(5.0)
            self.logger.info('Settle complete')
            
            self.logger.info('Starting PDF export (panel)')
            
            # Export to PDF
            output_filename = f'1-{component_id}-{order_id}-drawing.pdf'
            success, msg, file_path = self.export_drawing_to_pdf(output_filename, order_id)
            
            return success, msg, file_path
            
        except Exception as e:
            return False, f'Error in panel drawing export workflow: {str(e)}', None
    
    def close_drawing(self, save: bool = False) -> Tuple[bool, str]:
        """
        Close the current drawing document.
        
        Args:
            save: Whether to save before closing
            
        Returns:
            Tuple of (success, message)
        """
        try:
            if self._drawing_doc and self._drawing_doc.isValid:
                self._drawing_doc.close(save)
                self._drawing_doc = None
                self._drawing_data_file = None
                return True, 'Drawing closed'
            return True, 'No drawing to close'
        except Exception as e:
            return False, f'Error closing drawing: {str(e)}'
    
    def get_drawings_output_dir(self) -> str:
        """Get the drawings output directory path."""
        return str(self.drawings_dir)
