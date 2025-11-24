"""
Progress Dialog for Order Processing
Shows real-time progress with a clean UI
"""

import adsk.core
import adsk.fusion
from typing import Optional


class ProgressDialog:
    """Custom progress dialog with status updates"""
    
    def __init__(self, app: adsk.core.Application, title: str = "Processing Order"):
        """Initialize progress dialog"""
        self.app = app
        self.ui = app.userInterface
        self.title = title
        self.progress_dialog = None
        
    def show(self, message: str = "Starting..."):
        """Show the progress dialog"""
        self.progress_dialog = self.ui.createProgressDialog()
        self.progress_dialog.cancelButtonText = ''  # Hide cancel button
        self.progress_dialog.isBackgroundTranslucent = False
        self.progress_dialog.isCancelButtonShown = False
        self.progress_dialog.show(self.title, message, 0, 100, 0)
        
    def update(self, message: str, progress_value: int = -1):
        """
        Update progress dialog message and value
        
        Args:
            message: Status message to display
            progress_value: Progress value 0-100, or -1 to not change
        """
        if self.progress_dialog and not self.progress_dialog.wasCancelled:
            self.progress_dialog.message = message
            if progress_value >= 0:
                self.progress_dialog.progressValue = progress_value
    
    def hide(self):
        """Hide the progress dialog"""
        if self.progress_dialog:
            self.progress_dialog.hide()
            self.progress_dialog = None
    
    def is_cancelled(self) -> bool:
        """Check if user cancelled the operation"""
        if self.progress_dialog:
            return self.progress_dialog.wasCancelled
        return False


class ProgressTracker:
    """Tracks progress across multiple components"""
    
    def __init__(self, dialog: ProgressDialog, total_components: int):
        """
        Initialize progress tracker
        
        Args:
            dialog: ProgressDialog instance
            total_components: Total number of components to process
        """
        self.dialog = dialog
        self.total_components = total_components
        self.completed_components = 0
        self.current_component = ""
        self.current_step = ""
        
    def start_component(self, component_id: str, component_type: str):
        """Start processing a new component"""
        self.current_component = f"{component_type}: {component_id}"
        self.current_step = "Opening model..."
        self._update()
    
    def update_step(self, step: str):
        """Update current processing step"""
        self.current_step = step
        self._update()
    
    def complete_component(self, success: bool):
        """Mark current component as complete"""
        self.completed_components += 1
        status = "✓" if success else "✗"
        self.current_step = f"{status} Complete"
        self._update()
    
    def _update(self):
        """Update the progress dialog"""
        progress_pct = int((self.completed_components / self.total_components) * 100)
        message = f"{self.current_component}\n{self.current_step}\n\nProgress: {self.completed_components}/{self.total_components} components"
        self.dialog.update(message, progress_pct)
    
    def finish(self, success_count: int, fail_count: int):
        """Show final results"""
        total = success_count + fail_count
        message = f"Processing Complete!\n\n✓ Successful: {success_count}/{total}\n✗ Failed: {fail_count}/{total}"
        self.dialog.update(message, 100)
