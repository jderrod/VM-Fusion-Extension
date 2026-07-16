"""
Process health monitoring and controlled self-restart.

Fusion leaks NVIDIA display-driver worker threads (~200 per processed order
on the VM, measured 2026-07-12: 27 orders -> ~5,800 leaked nvwgf2umx threads)
that survive every document close and cleanup pass the add-in can perform.
Near ~6,000 threads the process dies with an access violation inside Fusion's
own serializer (observed in Ns::ZipFolder::_findPart during a cloud save).

Since the leak is inside Fusion/the display driver, it cannot be freed from
add-in code. The reliable mitigation is a controlled restart of Fusion
between orders, well before the exhaustion point:

1. folder_monitor checks get_thread_count() after each order.
2. Past THREAD_RESTART_THRESHOLD it writes a restart-state file (run mode +
   skip flags), spawns a detached PowerShell helper, and stops taking orders.
3. The helper closes Fusion gracefully (taskkill -> WM_CLOSE), force-kills it
   only if the graceful close hangs, then relaunches the same Fusion exe.
4. On the next add-in load, FusionManufacturingPipeline.run() finds the fresh
   restart-state file and auto-resumes monitoring without any dialogs.
   Requires "runOnStartup": true in the manifest.
"""

import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

# Restart between orders once the process crosses this many threads.
# This is a LAST RESORT, not routine hygiene: the observed crash was at
# 6,200 threads and one order adds ~200, so 4,500 leaves roughly 8 orders
# of margin while letting ~20 orders run per Fusion session. Prefer fixing
# the leak rate (see log_thread_count instrumentation) over lowering this.
THREAD_RESTART_THRESHOLD = 4500

# Restart when the Fusion process working set (physical RAM) crosses this, as a
# backstop to the thread trigger. Fusion's memory (thread stacks, GPU/driver
# contexts, and the growing local cloud-document cache) accumulates over a
# session and is only reclaimed when the process closes — observed ~20 GB at
# 15k threads. Restarting reclaims it. 12 GB keeps a wide margin under the VM's
# 64 GB while letting a big multi-panel order finish. Whichever trigger (this or
# threads) fires first requests the restart.
MEMORY_RESTART_THRESHOLD_MB = 12000

# A restart-state file older than this is ignored (likely a manual relaunch
# long after a failed restart, or a leftover from a crashed helper).
STATE_MAX_AGE_SECONDS = 30 * 60

# Seconds the helper waits for a graceful close before force-killing Fusion.
GRACEFUL_CLOSE_TIMEOUT_SECONDS = 120


def _state_path() -> Path:
    """Restart-state file lives next to the add-in (repo/add-in root)."""
    return Path(__file__).parent.parent / 'restart_state.json'


def get_thread_count() -> int:
    """Thread count of the current (Fusion) process, or -1 on failure.

    Uses a Toolhelp32 process snapshot (PROCESSENTRY32W.cntThreads) so it
    needs no external packages inside Fusion's embedded Python.
    """
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ('dwSize', wt.DWORD),
            ('cntUsage', wt.DWORD),
            ('th32ProcessID', wt.DWORD),
            ('th32DefaultHeapID', ctypes.c_size_t),
            ('th32ModuleID', wt.DWORD),
            ('cntThreads', wt.DWORD),
            ('th32ParentProcessID', wt.DWORD),
            ('pcPriClassBase', wt.LONG),
            ('dwFlags', wt.DWORD),
            ('szExeFile', ctypes.c_wchar * 260),
        ]

    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
        kernel32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        kernel32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]

        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snapshot or snapshot == wt.HANDLE(-1).value:
            return -1

        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        pid = os.getpid()
        count = -1
        try:
            if kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                while True:
                    if entry.th32ProcessID == pid:
                        count = int(entry.cntThreads)
                        break
                    if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                        break
        finally:
            kernel32.CloseHandle(snapshot)
        return count
    except Exception:
        return -1


def get_process_working_set_mb() -> float:
    """Working set (physical RAM in use) of the current process in MB, -1 on failure.

    Uses GetProcessMemoryInfo (psapi) — no external packages. This is the memory
    that is reclaimed when Fusion closes, so it is the right signal for the
    restart backstop.
    """
    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ('cb', wt.DWORD),
            ('PageFaultCount', wt.DWORD),
            ('PeakWorkingSetSize', ctypes.c_size_t),
            ('WorkingSetSize', ctypes.c_size_t),
            ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
            ('QuotaPagedPoolUsage', ctypes.c_size_t),
            ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
            ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
            ('PagefileUsage', ctypes.c_size_t),
            ('PeakPagefileUsage', ctypes.c_size_t),
        ]

    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wt.HANDLE
        # GetProcessMemoryInfo lives in psapi.dll, but is also exported from
        # kernel32 as K32GetProcessMemoryInfo on modern Windows.
        fn = None
        try:
            fn = ctypes.windll.psapi.GetProcessMemoryInfo
        except Exception:
            fn = getattr(kernel32, 'K32GetProcessMemoryInfo', None)
        if fn is None:
            return -1.0
        fn.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wt.DWORD]
        fn.restype = wt.BOOL

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        handle = kernel32.GetCurrentProcess()  # pseudo-handle, no close needed
        if fn(handle, ctypes.byref(counters), counters.cb):
            return counters.WorkingSetSize / (1024.0 * 1024.0)
        return -1.0
    except Exception:
        return -1.0


_last_logged_thread_count = None


def log_thread_count(logger, label: str):
    """Log the process thread count and the delta since the previous call.

    Sprinkled at pipeline milestones (STEP export, drawing export, CAM,
    workspace switch) to attribute the GPU-driver thread leak to a specific
    step, so the leak rate itself can be attacked instead of relying on
    restarts. Silent no-op if the count is unavailable.
    """
    global _last_logged_thread_count
    count = get_thread_count()
    if count < 0:
        return
    if _last_logged_thread_count is None:
        logger.info(f"[threads] {label}: {count}")
    else:
        delta = count - _last_logged_thread_count
        logger.info(f"[threads] {label}: {count} ({delta:+d})")
    _last_logged_thread_count = count


def get_fusion_exe_path() -> str:
    """Full path of the running Fusion executable ('' on failure)."""
    try:
        buf = ctypes.create_unicode_buffer(4096)
        n = ctypes.windll.kernel32.GetModuleFileNameW(None, buf, 4096)
        return buf.value if n else ''
    except Exception:
        return ''


def write_restart_state(run_mode: str, skip_cam: bool, skip_drawing: bool,
                        reason: str, thread_count: int):
    """Persist monitor settings so the relaunched add-in can auto-resume."""
    state = {
        'run_mode': run_mode,
        'skip_cam': bool(skip_cam),
        'skip_drawing': bool(skip_drawing),
        'reason': reason,
        'thread_count': thread_count,
        'requested_at': time.time(),
        'requested_at_human': datetime.now().isoformat(timespec='seconds'),
    }
    _state_path().write_text(json.dumps(state, indent=2), encoding='utf-8')


def read_restart_state():
    """Return the pending restart state, or None if absent/stale/corrupt.

    Stale and corrupt files are deleted so they can never trigger a
    surprise auto-resume days later.
    """
    path = _state_path()
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
        age = time.time() - float(state.get('requested_at', 0))
    except Exception:
        clear_restart_state()
        return None
    if age < 0 or age > STATE_MAX_AGE_SECONDS:
        clear_restart_state()
        return None
    return state


def clear_restart_state():
    try:
        _state_path().unlink(missing_ok=True)
    except Exception:
        pass


def spawn_restart_helper() -> bool:
    """Spawn a detached PowerShell that closes and relaunches Fusion.

    Returns True if the helper process was launched. The helper:
    - waits 5s so the add-in can finish logging,
    - asks Fusion to close gracefully (taskkill without /F sends WM_CLOSE;
      all documents are saved between orders so no prompt is expected),
    - force-kills only if Fusion is still alive after the graceful timeout,
    - relaunches the same executable after a settling delay.
    """
    exe = get_fusion_exe_path()
    if not exe or not Path(exe).exists():
        return False
    pid = os.getpid()

    script = rf"""
$fusionPid = {pid}
$exe = '{exe}'
Start-Sleep -Seconds 5
taskkill /PID $fusionPid | Out-Null
$deadline = (Get-Date).AddSeconds({GRACEFUL_CLOSE_TIMEOUT_SECONDS})
while ((Get-Date) -lt $deadline -and (Get-Process -Id $fusionPid -ErrorAction SilentlyContinue)) {{
    Start-Sleep -Seconds 2
}}
if (Get-Process -Id $fusionPid -ErrorAction SilentlyContinue) {{
    taskkill /F /PID $fusionPid | Out-Null
    Start-Sleep -Seconds 5
}}
while (Get-Process -Id $fusionPid -ErrorAction SilentlyContinue) {{
    Start-Sleep -Seconds 2
}}
Start-Sleep -Seconds 15
# Clear crash-recovery residue so the relaunch shows no recovery prompt
# (the prompt is modal and precedes add-in load, so it must be prevented
# here rather than dismissed from inside Fusion).
$fusionData = Join-Path $env:LOCALAPPDATA 'Autodesk\Autodesk Fusion 360'
Get-ChildItem -Path $fusionData -Filter CrashRecovery -Recurse -Directory -ErrorAction SilentlyContinue | ForEach-Object {{
    Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}}
Start-Process -FilePath $exe
"""
    script_path = Path(tempfile.gettempdir()) / f'fusion_pipeline_restart_{pid}.ps1'
    script_path.write_text(script, encoding='utf-8-sig')

    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008
    subprocess.Popen(
        ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
         '-File', str(script_path)],
        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
        close_fds=True,
    )
    return True
