"""
Fusion 360 Manufacturing Pipeline Add-in
Entry point file - must match the manifest name exactly.
"""

import adsk.core
import adsk.fusion
import traceback
import threading
import json
import sys
import os

# Add src directory to path
_src_path = os.path.join(os.path.dirname(__file__), 'src')
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

# Global references
_app = None
_ui = None
_handlers = []

# Auto-resume after a pipeline self-restart (see src/process_health.py).
# Monitoring can't start directly inside run(): Fusion is still initializing
# cloud services at add-in load, so we wait, then hop back onto the UI thread
# via a custom event (Fusion API calls are only safe there). If the first
# attempt fails (cloud data layer not ready yet on a slow cold boot), it
# retries a few times before falling back to a visible error dialog.
_AUTO_RESUME_EVENT_ID = 'PipelineAutoResumeEvent'
_AUTO_RESUME_DELAY_SECONDS = 90
_AUTO_RESUME_RETRY_DELAY_SECONDS = 120
_AUTO_RESUME_MAX_ATTEMPTS = 4
_auto_resume_state = None
_auto_resume_event = None
_auto_resume_attempts = 0


class _AutoResumeHandler(adsk.core.CustomEventHandler):
    """Resumes folder monitoring on the UI thread after a self-restart."""

    def notify(self, args):
        global _auto_resume_attempts
        _auto_resume_attempts += 1
        monitor = None
        try:
            monitor = _do_auto_resume()
        except Exception:
            pass  # fall through to retry logic below

        if monitor is not None and monitor.is_running:
            return  # resumed successfully

        if _auto_resume_attempts < _AUTO_RESUME_MAX_ATTEMPTS:
            _fire_auto_resume_later(_AUTO_RESUME_RETRY_DELAY_SECONDS)
            return

        if _ui:
            _ui.messageBox(
                'Failed to auto-resume folder monitoring after '
                f'{_auto_resume_attempts} attempts.\n\n'
                'Start it manually via the "Specs to Machine" button.',
                'Auto-Resume Failed'
            )


def _start_recovery_watcher():
    """Auto-dismiss Fusion's document-recovery prompt (unattended paths only)."""
    try:
        import dialog_watcher
        from logger import get_logger
        dialog_watcher.start_recovery_dialog_watcher(get_logger())
    except Exception:
        pass


def _do_auto_resume():
    """Attempt to start monitoring from the saved state. Returns the monitor."""
    import process_health
    from logger import get_logger
    from config import set_run_mode
    from folder_monitor import get_monitor

    state = _auto_resume_state
    # One-shot: clear before starting so a failure can't loop restarts.
    process_health.clear_restart_state()

    logger = get_logger()
    logger.info("=" * 80)
    logger.info(
        f"AUTO-RESUME attempt {_auto_resume_attempts}/{_AUTO_RESUME_MAX_ATTEMPTS} "
        f"(reason={state.get('reason')}, "
        f"thread_count={state.get('thread_count')}, "
        f"requested_at={state.get('requested_at_human')})"
    )
    logger.info("=" * 80)

    set_run_mode(state.get('run_mode', 'VM'))
    monitor = get_monitor(_app)
    if not monitor.is_running:
        monitor.start(
            skip_cam=state.get('skip_cam', False),
            skip_drawing=state.get('skip_drawing', False),
            auto_resume=True,
        )
    return monitor


def _fire_auto_resume_later(delay_seconds):
    timer = threading.Timer(
        delay_seconds,
        lambda: _app.fireCustomEvent(_AUTO_RESUME_EVENT_ID)
    )
    timer.daemon = True
    timer.start()


def _schedule_auto_resume(state):
    global _auto_resume_state, _auto_resume_event
    _auto_resume_state = state

    # Clean slate in case a previous session left the event registered
    try:
        _app.unregisterCustomEvent(_AUTO_RESUME_EVENT_ID)
    except Exception:
        pass
    _auto_resume_event = _app.registerCustomEvent(_AUTO_RESUME_EVENT_ID)
    handler = _AutoResumeHandler()
    _auto_resume_event.add(handler)
    _handlers.append(handler)

    _fire_auto_resume_later(_AUTO_RESUME_DELAY_SECONDS)


def _read_autostart_config() -> dict:
    """Load autostart_config.json from the add-in root ({} if absent/invalid).

    When present with "enabled": true, every Fusion startup goes straight to
    folder monitoring with the saved settings and NO dialogs. The repo/dev
    copy ships with enabled=false so a dev machine never auto-starts
    production monitoring; the VM's deployed copy has enabled=true.
    """
    try:
        path = os.path.join(os.path.dirname(__file__), 'autostart_config.json')
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def run(context):
    """Called when add-in is started"""
    global _app, _ui

    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        # Import after setting up path
        import app
        import process_health

        # Register the command
        app.register_command(_ui, _handlers)

        # If Fusion was relaunched by the pipeline's own restart helper,
        # resume monitoring automatically with the saved settings.
        restart_state = process_health.read_restart_state()
        if restart_state:
            _start_recovery_watcher()
            _schedule_auto_resume(restart_state)
            return

        # Unattended VM: start monitoring on every Fusion launch, no dialogs.
        autostart = _read_autostart_config()
        if autostart.get('enabled'):
            _start_recovery_watcher()
            _schedule_auto_resume({
                'run_mode': autostart.get('run_mode', 'VM'),
                'skip_cam': bool(autostart.get('skip_cam', False)),
                'skip_drawing': bool(autostart.get('skip_drawing', False)),
                'reason': 'fusion_startup_autostart',
                'thread_count': -1,
                'requested_at_human': 'fusion startup',
            })
            return

        # Interactive (dev) mode: show where the button lives.
        # Folder paths are configured later when the user picks Local/VM mode.
        _ui.messageBox(
            'Specs to Machine loaded successfully!\n\n'
            'Button Location:\n'
            '  → Design workspace\n'
            '  → SOLID toolbar panel\n'
            '  → Look for "Specs to Machine" button with Bobrick logo\n\n'
            'Click the button to choose Local/VM mode and start processing.',
            'Specs to Machine - Ready'
        )

    except:
        if _ui:
            _ui.messageBox('Failed to initialize add-in:\n{}'.format(traceback.format_exc()))

def stop(context):
    """Called when add-in is stopped"""
    global _ui, _handlers, _app

    try:
        # Stop folder monitor if running
        try:
            from folder_monitor import get_monitor
            monitor = get_monitor(_app)
            if monitor.is_running:
                monitor.stop()
        except:
            pass

        try:
            _app.unregisterCustomEvent(_AUTO_RESUME_EVENT_ID)
        except:
            pass

        if _ui:
            # Import after setting up path
            import app

            # Unregister the command
            app.unregister_command(_ui)

            # No "unloaded" messageBox here: Fusion calls stop() during app
            # shutdown, and a modal dialog blocks the graceful close that the
            # self-restart and dashboard-restart flows rely on.

        # Clean up handlers
        _handlers.clear()

    except:
        if _ui:
            _ui.messageBox('Failed to clean up add-in:\n{}'.format(traceback.format_exc()))
