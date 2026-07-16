"""
Auto-dismiss Fusion's "recoverable documents" prompt on unattended startup.

When Fusion is force-killed (our self-restart's fallback) or crashes, the next
launch shows a document-recovery prompt and waits for a human. On the VM there
is no human, so this watcher runs on a daemon thread, finds any top-level
window owned by THIS Fusion process whose title mentions recovery, and posts
WM_CLOSE to it — the exact equivalent of clicking the X, which DECLINES
recovery (it never accepts). Pure Win32 via ctypes; it never calls the Fusion
API, so it is safe to run off the UI thread.

Only started on unattended paths (autostart / self-restart). Interactive dev
sessions keep the normal prompt so a developer can choose to recover.
"""

import ctypes
import ctypes.wintypes as wt
import os
import threading
import time

WM_CLOSE = 0x0010

# Case-insensitive substrings that identify the recovery prompt. Kept broad
# because the exact title varies by Fusion build; scoped to this process's own
# windows so it can only ever hit a Fusion-owned dialog.
_RECOVERY_TITLE_HINTS = ('recover',)


def _enum_process_windows():
    """Yield (hwnd, title) for visible top-level windows of this process."""
    user32 = ctypes.windll.user32
    results = []
    my_pid = os.getpid()

    EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def _cb(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != my_pid:
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            results.append((hwnd, buf.value))
        except Exception:
            pass
        return True

    user32.EnumWindows(EnumWindowsProc(_cb), 0)
    return results


def _dismiss_recovery_windows(logger) -> int:
    user32 = ctypes.windll.user32
    closed = 0
    for hwnd, title in _enum_process_windows():
        low = (title or '').lower()
        if any(hint in low for hint in _RECOVERY_TITLE_HINTS):
            try:
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                closed += 1
                if logger:
                    logger.info(f"dialog_watcher: closed recovery prompt (title={title!r})")
            except Exception as e:
                if logger:
                    logger.warning(f"dialog_watcher: failed to close {title!r}: {e}")
    return closed


def start_recovery_dialog_watcher(logger=None, duration_seconds: int = 180,
                                  poll_seconds: float = 1.0):
    """Watch for and close the recovery prompt for up to duration_seconds.

    Keeps polling for the whole window (the prompt can appear seconds after
    the add-in loads, and Fusion may re-raise it), so a single early miss
    does not leave the pipeline stuck behind a modal.
    """
    def _run():
        deadline = time.time() + duration_seconds
        total = 0
        while time.time() < deadline:
            try:
                total += _dismiss_recovery_windows(logger)
            except Exception:
                pass
            time.sleep(poll_seconds)
        if logger and total:
            logger.info(f"dialog_watcher: finished, dismissed {total} recovery prompt(s)")

    t = threading.Thread(target=_run, name='RecoveryDialogWatcher', daemon=True)
    t.start()
    return t
