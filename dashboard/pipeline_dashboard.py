"""
Fusion Manufacturing Pipeline Dashboard

Standalone web dashboard (Python 3 standard library only — no pip installs)
meant to run ON THE VM. Shows live pipeline status and order/component
statistics, and can start or restart Fusion with the extension auto-resuming.

Data sources (written by the add-in, see src/pipeline_stats.py):
- <data-dir>/pipeline_status.json  — heartbeat, overwritten every ~15 s
- <data-dir>/order_ledger.jsonl    — one line per finished order

Start/Restart mechanics: the dashboard writes restart_state.json into the
add-in folder (same schema as src/process_health.py) and launches Fusion; on
load the add-in sees the fresh state file and auto-resumes monitoring with no
dialogs ("runOnStartup" must be true in the manifest — it is since v2.5.0).

Usage (on the VM):
    python pipeline_dashboard.py
    python pipeline_dashboard.py --host 127.0.0.1 --port 8765
Then open http://localhost:8765 (or http://<vm-ip>:8765 from another machine).
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ─── Configuration (overridable via CLI args) ────────────────────────────────
DEFAULT_DATA_DIR = r'\\ddc-mefs\Fusion\Fusion Folders\output\dashboard'
DEFAULT_DROPBOX_DIR = r'\\ddc-mefs\iBob-Export\S2S_Export'  # the order queue
DEFAULT_ADDIN_DIR = os.path.expandvars(
    r'%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\FusionManufacturingPipeline')
FUSION_PROCESS_NAME = 'Fusion360.exe'
FUSION_DATA_DIR = Path(os.path.expandvars(
    r'%LOCALAPPDATA%\Autodesk\Autodesk Fusion 360'))
HEARTBEAT_FRESH_SECONDS = 45     # heartbeat younger than this = live
HEARTBEAT_STALE_SECONDS = 180    # older than this (with Fusion up) = hung
GRACEFUL_CLOSE_TIMEOUT_SECONDS = 120
# Crash auto-recovery: if Fusion dies unexpectedly (spontaneous crash, not a
# deliberate stop), relaunch it so monitoring auto-resumes. Bounded so a
# crash-on-startup loop can't relaunch forever.
CRASH_CHECK_INTERVAL_SECONDS = 20
CRASH_RECOVERY_COOLDOWN_SECONDS = 240   # min gap between relaunch attempts
CRASH_RECOVERY_MAX_ATTEMPTS = 5         # consecutive; reset once healthy again
# Window titles (case-insensitive substrings) of the document-recovery prompt.
RECOVERY_TITLE_HINTS = ('recover',)
WM_CLOSE = 0x0010

DATA_DIR = Path(DEFAULT_DATA_DIR)
DROPBOX_DIR = Path(DEFAULT_DROPBOX_DIR)
ADDIN_DIR = Path(DEFAULT_ADDIN_DIR)
ACTIONS_ENABLED = True  # --no-actions makes start/restart buttons inert (safe for dev)

# Cache the queue scan (reads every queued JSON over the network) so the 5s
# status poll doesn't hammer the share.
_queue_cache = {'time': 0.0, 'data': []}
_QUEUE_CACHE_TTL = 15.0


# ─── Fusion process helpers ──────────────────────────────────────────────────

def find_fusion_pids() -> list:
    """PIDs of running Fusion processes via tasklist (no external deps)."""
    try:
        out = subprocess.run(
            ['tasklist', '/FI', f'IMAGENAME eq {FUSION_PROCESS_NAME}', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, timeout=15)
        pids = []
        for line in out.stdout.splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) >= 2 and parts[0].lower() == FUSION_PROCESS_NAME.lower():
                try:
                    pids.append(int(parts[1]))
                except ValueError:
                    pass
        return pids
    except Exception:
        return []


def find_fusion_exe() -> str:
    """Newest Fusion360.exe under the webdeploy production folder ('' if none)."""
    try:
        base = Path(os.path.expandvars(r'%LOCALAPPDATA%\Autodesk\webdeploy\production'))
        candidates = list(base.glob(r'*\Fusion360.exe'))
        if not candidates:
            return ''
        newest = max(candidates, key=lambda p: p.stat().st_mtime)
        return str(newest)
    except Exception:
        return ''


def clear_crash_recovery() -> int:
    """Empty Fusion's CrashRecovery folders so no recovery prompt appears.

    Called right before we launch/relaunch Fusion. On the VM every model is a
    cloud document saved after each order, so crash-recovery residue (left by
    our own force-kills) is never wanted — declining it is always correct.
    Returns the number of entries removed. Best-effort; never raises.

    The prompt is a modal shown DURING Fusion startup, before the add-in
    loads — so it cannot be dismissed from inside Fusion. Clearing the data
    beforehand prevents it at the source; close_recovery_windows() is the
    backstop for anything that still slips through.
    """
    removed = 0
    try:
        # Two locations: the top-level one and the per-user-hash one.
        targets = [FUSION_DATA_DIR / 'CrashRecovery']
        targets += list(FUSION_DATA_DIR.glob('*/CrashRecovery'))
        for folder in targets:
            if not folder.is_dir():
                continue
            for child in folder.iterdir():
                try:
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                    else:
                        child.unlink()
                    removed += 1
                except Exception:
                    pass
    except Exception:
        pass
    return removed


def _enum_windows_by_pids(pids: set):
    """Yield (hwnd, title) for visible top-level windows owned by these PIDs."""
    user32 = ctypes.windll.user32
    results = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def _cb(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in pids:
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


def close_recovery_windows() -> int:
    """Post WM_CLOSE to any Fusion-owned 'Recovered Documents'-style window.

    WM_CLOSE == clicking the X == DECLINE recovery (never accepts). Scoped to
    Fusion's own process IDs so it can only ever hit a Fusion dialog.
    """
    pids = set(find_fusion_pids())
    if not pids:
        return 0
    user32 = ctypes.windll.user32
    closed = 0
    for hwnd, title in _enum_windows_by_pids(pids):
        low = (title or '').lower()
        if any(h in low for h in RECOVERY_TITLE_HINTS):
            try:
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                closed += 1
            except Exception:
                pass
    return closed


def recovery_watcher_loop():
    """Background thread: continuously dismiss the recovery prompt.

    Runs for the dashboard's lifetime so it catches the modal whenever Fusion
    shows it — including launches the dashboard didn't initiate (boot, manual).
    """
    while True:
        try:
            close_recovery_windows()
        except Exception:
            pass
        time.sleep(2.0)


def write_restart_state(reason: str):
    """Same schema as src/process_health.py so the add-in auto-resumes."""
    state = {
        'run_mode': 'VM',
        'skip_cam': False,
        'skip_drawing': False,
        'reason': reason,
        'thread_count': -1,
        'requested_at': time.time(),
        'requested_at_human': datetime.now().isoformat(timespec='seconds'),
    }
    ADDIN_DIR.mkdir(parents=True, exist_ok=True)
    (ADDIN_DIR / 'restart_state.json').write_text(
        json.dumps(state, indent=2), encoding='utf-8')


def launch_fusion() -> str:
    """Launch Fusion detached. Returns an error message or '' on success."""
    exe = find_fusion_exe()
    if not exe:
        return 'Fusion360.exe not found under %LOCALAPPDATA%\\Autodesk\\webdeploy\\production'
    # Clear crash-recovery residue so no modal recovery prompt blocks startup.
    clear_crash_recovery()
    DETACHED_PROCESS = 0x00000008
    CREATE_NO_WINDOW = 0x08000000
    subprocess.Popen([exe], creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
                     close_fds=True)
    return ''


def spawn_kill_and_relaunch(pid: int) -> str:
    """Detached PowerShell: graceful close -> force kill -> relaunch Fusion.
    Same flow as the add-in's self-restart helper."""
    exe = find_fusion_exe()
    if not exe:
        return 'Fusion360.exe not found — cannot relaunch'
    script = rf"""
$fusionPid = {pid}
$exe = '{exe}'
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
# Clear crash-recovery residue so the relaunch shows no recovery prompt.
$fusionData = Join-Path $env:LOCALAPPDATA 'Autodesk\Autodesk Fusion 360'
Get-ChildItem -Path $fusionData -Filter CrashRecovery -Recurse -Directory -ErrorAction SilentlyContinue | ForEach-Object {{
    Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}}
Start-Process -FilePath $exe
"""
    import tempfile
    script_path = Path(tempfile.gettempdir()) / f'dashboard_restart_{pid}.ps1'
    script_path.write_text(script, encoding='utf-8-sig')
    DETACHED_PROCESS = 0x00000008
    CREATE_NO_WINDOW = 0x08000000
    subprocess.Popen(
        ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
         '-File', str(script_path)],
        creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW, close_fds=True)
    return ''


# ─── Data readers ────────────────────────────────────────────────────────────

def read_heartbeat():
    try:
        path = DATA_DIR / 'pipeline_status.json'
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def read_ledger() -> list:
    records = []
    try:
        path = DATA_DIR / 'order_ledger.jsonl'
        if not path.exists():
            return records
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        pass
    return records


def aggregate_stats(records: list) -> dict:
    today = date.today()

    def is_today(r):
        try:
            return date.fromtimestamp(r.get('timestamp', 0)) == today
        except Exception:
            return False

    def bucket(rs):
        ok = [r for r in rs if r.get('success')]
        return {
            'orders_total': len(rs),
            'orders_completed': len(ok),
            'orders_failed': len(rs) - len(ok),
            'panels': sum(r.get('panels', 0) for r in ok),
            'doors': sum(r.get('doors', 0) for r in ok),
            'stiles': sum(r.get('stiles', 0) for r in ok),
        }

    recent = sorted(records, key=lambda r: r.get('timestamp', 0), reverse=True)[:25]
    return {
        'all_time': bucket(records),
        'today': bucket([r for r in records if is_today(r)]),
        'recent': recent,
    }


# ─── Per-component time estimates + queue ────────────────────────────────────

def _solve3(A, c):
    """Solve the 3x3 system A x = c by Cramer's rule; None if near-singular."""
    def det3(m):
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    D = det3(A)
    if abs(D) < 1e-6:
        return None
    out = []
    for col in range(3):
        M = [row[:] for row in A]
        for r in range(3):
            M[r][col] = c[r]
        out.append(det3(M) / D)
    return out


def estimate_component_times(records):
    """Estimate average seconds per panel/door/stile from finished orders.

    Uses least-squares on order-level data (duration ≈ p*panels + d*doors +
    s*stiles). Falls back to a flat per-component average when there isn't
    enough varied data or the fit is degenerate/negative.
    """
    data = [(r.get('panels', 0), r.get('doors', 0), r.get('stiles', 0),
             r.get('duration_seconds', 0))
            for r in records
            if r.get('success') and r.get('duration_seconds', 0) > 0]
    if len(data) >= 4:
        A = [[0.0] * 3 for _ in range(3)]
        c = [0.0] * 3
        for p, d, s, y in data:
            x = (p, d, s)
            for i in range(3):
                c[i] += x[i] * y
                for j in range(3):
                    A[i][j] += x[i] * x[j]
        est = _solve3(A, c)
        if est and all(v > 1 for v in est):  # all positive & sane (>1s each)
            return {'panel': est[0], 'door': est[1], 'stile': est[2],
                    'method': 'regression', 'n': len(data)}
    # Fallback: flat per-component average.
    tot_dur = sum(d[3] for d in data)
    tot_comp = sum(d[0] + d[1] + d[2] for d in data)
    flat = (tot_dur / tot_comp) if tot_comp else 0
    return {'panel': flat, 'door': flat, 'stile': flat,
            'method': 'flat' if flat else 'none', 'n': len(data)}


def _count_order_components(path):
    try:
        d = json.loads(path.read_text(encoding='utf-8'))
        return (len(d.get('panels', []) or []),
                len(d.get('doors', []) or []),
                len(d.get('stiles', []) or []))
    except Exception:
        return (0, 0, 0)


def scan_queue(est):
    """Return upcoming orders (dropbox *.json, in processing order) with per-order
    time estimates. Cached for _QUEUE_CACHE_TTL to spare the network share."""
    now = time.time()
    if now - _queue_cache['time'] < _QUEUE_CACHE_TTL:
        return _queue_cache['data']
    out = []
    try:
        files = sorted(DROPBOX_DIR.glob('*.json'))[:60]
        for f in files:
            p, d, s = _count_order_components(f)
            secs = p * est['panel'] + d * est['door'] + s * est['stile']
            out.append({'name': f.stem, 'panels': p, 'doors': d, 'stiles': s,
                        'est_minutes': round(secs / 60.0, 1)})
    except Exception:
        pass
    _queue_cache['time'] = now
    _queue_cache['data'] = out
    return out


def pending_start_age():
    """Seconds since a not-yet-consumed restart_state.json was written, or None."""
    try:
        state = json.loads((ADDIN_DIR / 'restart_state.json').read_text(encoding='utf-8'))
        return time.time() - float(state.get('requested_at', 0))
    except Exception:
        return None


def derive_state(heartbeat, fusion_up: bool) -> str:
    """One-word pipeline state for the UI badge."""
    hb_age = (time.time() - heartbeat.get('timestamp', 0)) if heartbeat else None
    hb_fresh = hb_age is not None and hb_age <= HEARTBEAT_FRESH_SECONDS
    # A restart_state file the add-in hasn't consumed yet = launch in progress
    # (the add-in deletes it when monitoring resumes, ~2-3 min after launch).
    start_age = pending_start_age()
    if start_age is not None and 0 <= start_age <= 600 and not hb_fresh:
        return 'starting'
    if heartbeat:
        age = time.time() - heartbeat.get('timestamp', 0)
        state = heartbeat.get('state', '')
        if age <= HEARTBEAT_FRESH_SECONDS and state in ('monitoring', 'processing'):
            return state
        if state == 'restarting' and age <= 300:
            return 'restarting'
        if state == 'stopped' and not fusion_up:
            return 'offline'
        if state == 'stopped':
            return 'stopped'
        if fusion_up and age > HEARTBEAT_STALE_SECONDS:
            return 'hung'
        if fusion_up:
            return 'stale'
        # Heartbeat says it was working, but the Fusion process is gone and
        # the heartbeat is stale — that's a spontaneous crash.
        if state in ('monitoring', 'processing'):
            return 'crashed'
    return 'running-no-monitor' if fusion_up else 'offline'


def decide_crash_recovery(fusion_up, hb_state, hb_age, start_age,
                          attempts, since_last_attempt) -> str:
    """Pure decision for the crash-recovery loop: 'recover' or 'skip'.

    Recover only when Fusion's process is gone, its last heartbeat showed it
    actively working (not a deliberate stop or an in-progress restart), no
    launch is already pending, and the cooldown / max-attempt guards allow it.
    """
    if fusion_up:
        return 'skip'                     # process alive — nothing to recover
    if hb_state is None:
        return 'skip'                     # never ran here — don't auto-launch
    if hb_state == 'stopped':
        return 'skip'                     # user stopped it deliberately
    if hb_state == 'restarting':
        return 'skip'                     # self-restart already relaunching
    if start_age is not None and 0 <= start_age <= 600:
        return 'skip'                     # a launch is already in flight
    if hb_age is not None and hb_age <= HEARTBEAT_FRESH_SECONDS:
        return 'skip'                     # heartbeat still fresh — not dead yet
    if attempts >= CRASH_RECOVERY_MAX_ATTEMPTS:
        return 'skip'                     # crash loop — give up, surface it
    if since_last_attempt < CRASH_RECOVERY_COOLDOWN_SECONDS:
        return 'skip'                     # too soon since the last relaunch
    return 'recover'


_crash_recovery = {'attempts': 0, 'last_attempt': 0.0}


def crash_recovery_loop():
    """Relaunch Fusion after a spontaneous crash so monitoring auto-resumes.

    Fusion can die inside its own cloud-save serializer at any order (a
    Fusion-internal fault, unrelated to the thread-pressure self-restart).
    Without this the pipeline would sit dead until someone clicks Start.
    """
    time.sleep(45)  # let the initial launch settle before watching
    while True:
        try:
            hb = read_heartbeat()
            pids = find_fusion_pids()
            hb_state = hb.get('state') if hb else None
            hb_age = (time.time() - hb.get('timestamp', 0)) if hb else None
            now = time.time()
            # Reset the attempt counter once we see a healthy session again.
            if pids and hb and hb_age is not None and hb_age <= HEARTBEAT_FRESH_SECONDS \
                    and hb_state in ('monitoring', 'processing'):
                _crash_recovery['attempts'] = 0
            decision = decide_crash_recovery(
                fusion_up=bool(pids), hb_state=hb_state, hb_age=hb_age,
                start_age=pending_start_age(), attempts=_crash_recovery['attempts'],
                since_last_attempt=now - _crash_recovery['last_attempt'])
            if decision == 'recover':
                _crash_recovery['attempts'] += 1
                _crash_recovery['last_attempt'] = now
                print(f'[crash-recovery] Fusion is down (last state={hb_state}); '
                      f'relaunching, attempt {_crash_recovery["attempts"]}/'
                      f'{CRASH_RECOVERY_MAX_ATTEMPTS}')
                write_restart_state('crash_recovery')
                launch_fusion()  # clears crash-recovery residue internally
        except Exception:
            pass
        time.sleep(CRASH_CHECK_INTERVAL_SECONDS)


# ─── Actions ─────────────────────────────────────────────────────────────────

def action_start() -> dict:
    heartbeat = read_heartbeat()
    pids = find_fusion_pids()
    state = derive_state(heartbeat, bool(pids))
    if state in ('monitoring', 'processing'):
        return {'ok': True, 'message': 'Pipeline is already running.'}
    if state == 'starting':
        return {'ok': True, 'message': 'Fusion is already starting — the extension will '
                                       'auto-resume in ~2-3 minutes.'}
    if state == 'restarting':
        return {'ok': True, 'message': 'Pipeline is restarting itself — give it ~2 minutes.'}
    if pids:
        return {'ok': False,
                'message': f'Fusion is running (pid {pids[0]}) but the monitor is not responding '
                           f'(state: {state}). Use "Restart Fusion" to recover.'}
    write_restart_state('dashboard_start')
    err = launch_fusion()
    if err:
        return {'ok': False, 'message': err}
    return {'ok': True,
            'message': 'Fusion launching — the extension will auto-resume monitoring '
                       'in ~2-3 minutes.'}


def action_restart() -> dict:
    pids = find_fusion_pids()
    write_restart_state('dashboard_restart')
    if not pids:
        err = launch_fusion()
        if err:
            return {'ok': False, 'message': err}
        return {'ok': True, 'message': 'Fusion was not running — launching fresh.'}
    err = spawn_kill_and_relaunch(pids[0])
    if err:
        return {'ok': False, 'message': err}
    return {'ok': True,
            'message': 'Restart initiated — Fusion will close, relaunch, and auto-resume '
                       'monitoring (~3-4 minutes).'}


# ─── HTTP server ─────────────────────────────────────────────────────────────

class DashboardHandler(BaseHTTPRequestHandler):

    def _send(self, code: int, body: bytes, content_type: str):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload, code: int = 200):
        self._send(code, json.dumps(payload).encode('utf-8'), 'application/json')

    def do_GET(self):
        if self.path == '/' or self.path.startswith('/index'):
            self._send(200, PAGE_HTML.encode('utf-8'), 'text/html; charset=utf-8')
        elif self.path == '/api/status':
            heartbeat = read_heartbeat()
            fusion_pids = find_fusion_pids()
            ledger = read_ledger()
            estimates = estimate_component_times(ledger)
            self._send_json({
                'state': derive_state(heartbeat, bool(fusion_pids)),
                'fusion_running': bool(fusion_pids),
                'heartbeat': heartbeat,
                'heartbeat_age': (round(time.time() - heartbeat['timestamp'], 1)
                                  if heartbeat and heartbeat.get('timestamp') else None),
                'stats': aggregate_stats(ledger),
                'estimates': {
                    'panel': round(estimates['panel'] / 60.0, 2),
                    'door': round(estimates['door'] / 60.0, 2),
                    'stile': round(estimates['stile'] / 60.0, 2),
                    'method': estimates['method'],
                    'n': estimates['n'],
                },
                'queue': scan_queue(estimates),
                'server_time': datetime.now().isoformat(timespec='seconds'),
            })
        else:
            self._send_json({'error': 'not found'}, 404)

    def do_POST(self):
        if not ACTIONS_ENABLED:
            self._send_json({'ok': False,
                             'message': 'Actions disabled (--no-actions). This instance is view-only.'})
            return
        if self.path == '/api/start':
            self._send_json(action_start())
        elif self.path == '/api/restart':
            self._send_json(action_restart())
        else:
            self._send_json({'error': 'not found'}, 404)

    def log_message(self, fmt, *args):
        pass  # keep the console quiet


PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fusion Pipeline Dashboard</title>
<style>
  :root {
    --bg: #10141a; --card: #1a2027; --border: #2a3340; --text: #e6ebf1;
    --muted: #8b98a8; --green: #34c07a; --red: #e5534b; --amber: #e3a008;
    --blue: #4a9eda;
  }
  * { box-sizing: border-box; margin: 0; }
  body { background: var(--bg); color: var(--text); font: 15px/1.45 "Segoe UI", system-ui, sans-serif; padding: 24px; }
  .wrap { max-width: 1060px; margin: 0 auto; }
  h1 { font-size: 21px; font-weight: 600; }
  .sub { color: var(--muted); font-size: 13px; margin-top: 2px; }
  header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }
  .badge { padding: 5px 14px; border-radius: 999px; font-weight: 600; font-size: 14px; }
  .badge.monitoring   { background: #14351f; color: var(--green); }
  .badge.processing   { background: #10304a; color: var(--blue); }
  .badge.restarting, .badge.starting { background: #3a2f10; color: var(--amber); }
  .badge.stale, .badge.hung, .badge.running-no-monitor { background: #3a2f10; color: var(--amber); }
  .badge.stopped, .badge.offline, .badge.crashed { background: #3a1715; color: var(--red); }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 20px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
  .card .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }
  .card .value { font-size: 26px; font-weight: 650; margin-top: 4px; overflow-wrap: anywhere; line-height: 1.15; }
  .card .value.sm { font-size: 19px; }
  .card .hint { color: var(--muted); font-size: 12px; margin-top: 2px; }
  .value.warn { color: var(--amber); } .value.bad { color: var(--red); } .value.good { color: var(--green); }
  /* current-order progress panel */
  #progress-panel { margin-bottom: 20px; }
  .prog { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 15px 18px; }
  .prog .top { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
  .prog .oid { font-family: ui-monospace, monospace; font-size: 20px; font-weight: 650; }
  .prog .comp { color: var(--blue); font-weight: 600; }
  .prog .step { color: var(--muted); }
  .prog .eta { margin-left: auto; color: var(--muted); font-size: 13px; }
  .bar { height: 12px; background: #12181f; border: 1px solid var(--border); border-radius: 6px; margin-top: 12px; overflow: hidden; }
  .bar > span { display: block; height: 100%; background: var(--blue); border-radius: 6px; transition: width .4s; }
  .bar-lbl { color: var(--muted); font-size: 12px; margin-top: 5px; }
  /* queue */
  .qrow { display: flex; align-items: center; gap: 12px; background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 8px 14px; margin-bottom: 5px; }
  .qrow .qn { color: var(--muted); width: 22px; text-align: right; }
  .qrow .qid { font-family: ui-monospace, monospace; font-weight: 600; min-width: 130px; }
  .qrow .qc { color: var(--muted); font-size: 13px; flex: 1; }
  .qrow .qt { color: var(--text); font-variant-numeric: tabular-nums; }
  .controls { display: flex; gap: 10px; margin-bottom: 20px; align-items: center; flex-wrap: wrap; }
  button { border: 0; border-radius: 8px; padding: 10px 18px; font-size: 14px; font-weight: 600; cursor: pointer; }
  #btn-start { background: var(--green); color: #08130c; }
  #btn-restart { background: #333d49; color: var(--text); }
  button:disabled { opacity: .5; cursor: wait; }
  #action-msg { font-size: 13px; color: var(--muted); }
  h2 { font-size: 15px; font-weight: 600; color: var(--muted); margin: 22px 0 10px; }
  table { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
  th, td { text-align: left; padding: 8px 12px; font-size: 13.5px; }
  th { color: var(--muted); font-weight: 600; background: #151b22; }
  tr + tr td { border-top: 1px solid var(--border); }
  td.ok { color: var(--green); } td.fail { color: var(--red); }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  footer { color: var(--muted); font-size: 12px; margin-top: 18px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>Fusion Manufacturing Pipeline</h1>
      <div class="sub" id="meta">connecting&hellip;</div>
    </div>
    <span class="badge offline" id="state">&hellip;</span>
  </header>

  <div class="controls">
    <button id="btn-start">&#9654;&nbsp; Start / Ensure Running</button>
    <button id="btn-restart">&#8635;&nbsp; Restart Fusion</button>
    <span id="action-msg"></span>
  </div>

  <div class="grid" id="live-cards"></div>

  <div id="progress-panel"></div>

  <h2>Queue <span id="queue-sub" style="color:var(--muted);font-weight:400;text-transform:none;letter-spacing:0"></span></h2>
  <div id="queue"></div>

  <h2>Production totals</h2>
  <div class="grid" id="stat-cards"></div>

  <h2>Recent orders</h2>
  <table>
    <thead><tr>
      <th>Time</th><th>Order</th><th class="num">Panels</th><th class="num">Doors</th>
      <th class="num">Stiles</th><th class="num">Duration</th><th>Result</th>
    </tr></thead>
    <tbody id="recent"></tbody>
  </table>

  <footer id="footer"></footer>
</div>
<script>
const STATE_LABEL = {
  monitoring: 'MONITORING', processing: 'PROCESSING ORDER', restarting: 'RESTARTING',
  starting: 'STARTING UP',
  stale: 'STALE HEARTBEAT', hung: 'NOT RESPONDING', stopped: 'MONITOR STOPPED',
  offline: 'OFFLINE', 'running-no-monitor': 'FUSION UP, MONITOR OFF',
  crashed: 'CRASHED — RECOVERING'
};

function card(label, value, hint, cls) {
  return `<div class="card"><div class="label">${label}</div>` +
         `<div class="value ${cls||''}">${value}</div>` +
         (hint ? `<div class="hint">${hint}</div>` : '') + `</div>`;
}

function fmtDur(s) {
  if (s == null) return '';
  s = Math.round(s);
  return s >= 60 ? `${Math.floor(s/60)}m ${s%60}s` : `${s}s`;
}

async function refresh() {
  let r;
  try { r = await (await fetch('/api/status')).json(); }
  catch (e) {
    document.getElementById('state').textContent = 'DASHBOARD OFFLINE';
    return;
  }
  const hb = r.heartbeat || {};
  const badge = document.getElementById('state');
  badge.textContent = STATE_LABEL[r.state] || r.state.toUpperCase();
  badge.className = 'badge ' + r.state;

  document.getElementById('meta').textContent =
    `v${hb.version || '?'} · mode ${hb.run_mode || '?'} · Fusion process ${r.fusion_running ? 'running' : 'not running'}`;

  const threads = hb.thread_count ?? null;
  const threshold = hb.thread_restart_threshold || 4500;
  const threadCls = threads == null ? '' : threads >= threshold ? 'bad' : threads >= threshold * 0.7 ? 'warn' : 'good';

  const mem = hb.memory_mb ?? null;
  const memLimit = hb.memory_restart_threshold_mb || 12000;
  const memCls = mem == null || mem < 0 ? '' : mem >= memLimit ? 'bad' : mem >= memLimit * 0.7 ? 'warn' : 'good';
  const memTxt = mem == null || mem < 0 ? '—' : (mem >= 1024 ? (mem/1024).toFixed(1) + ' GB' : mem + ' MB');

  const q = r.queue || [];
  document.getElementById('live-cards').innerHTML =
    card('Queue', q.length || (hb.queue_size ?? 0), 'orders waiting') +
    card('Session orders', `${hb.session_completed ?? 0} / ${(hb.session_completed ?? 0) + (hb.session_failed ?? 0)}`, 'completed / total this session') +
    card('Fusion threads', threads ?? '—', `restarts at ${threshold}`, threadCls) +
    card('Fusion memory', memTxt, `restarts at ${(memLimit/1024).toFixed(0)} GB`, memCls) +
    card('Heartbeat age', r.heartbeat_age != null ? fmtDur(r.heartbeat_age) : '—', hb.timestamp_human || '');

  // Current-order progress panel
  const pr = hb.progress;
  const est = r.estimates || {};
  const avgMin = (['panel','door','stile'].map(k=>est[k]||0).reduce((a,b)=>a+b,0) / 3) || 0;
  const pp = document.getElementById('progress-panel');
  if (pr && pr.order_id) {
    const idx = pr.index || 0, tot = pr.total || 0;
    const pct = tot ? Math.min(100, Math.round(100*idx/tot)) : 0;
    const remain = Math.max(0, tot - idx);
    const eta = avgMin ? `~${(remain*avgMin).toFixed(0)} min left` : '';
    pp.innerHTML = `<div class="prog">
      <div class="top">
        <span class="oid">${pr.order_id || ''}</span>
        <span class="comp">${pr.component || ''}</span>
        <span class="step">${pr.step || ''}</span>
        <span class="eta">${eta}</span>
      </div>
      <div class="bar"><span style="width:${pct}%"></span></div>
      <div class="bar-lbl">component ${idx} of ${tot} · ${pct}%</div>
    </div>`;
  } else {
    pp.innerHTML = '';
  }

  // Queue with per-order time estimates
  const totalMin = q.reduce((a,o)=>a+(o.est_minutes||0), 0);
  const em = est.method === 'regression'
    ? `panel ${est.panel}m · door ${est.door}m · stile ${est.stile}m (from ${est.n} orders)`
    : (est.method === 'flat' ? `~${est.panel}m/component (from ${est.n} orders)` : 'not enough data yet');
  document.getElementById('queue-sub').textContent =
    q.length ? `— ${q.length} waiting · est ${totalMin.toFixed(0)} min total · avg ${em}` : `— empty · avg ${em}`;
  document.getElementById('queue').innerHTML = q.length ? q.map((o,i)=>{
    const parts = [];
    if (o.panels) parts.push(`${o.panels}P`);
    if (o.doors) parts.push(`${o.doors}D`);
    if (o.stiles) parts.push(`${o.stiles}S`);
    return `<div class="qrow"><span class="qn">${i+1}</span><span class="qid">${o.name}</span>` +
           `<span class="qc">${parts.join(' · ') || '—'}</span><span class="qt">~${o.est_minutes}m</span></div>`;
  }).join('') : '<div style="color:var(--muted);padding:4px 2px">Queue is empty.</div>';

  const at = r.stats.all_time, td = r.stats.today;
  document.getElementById('stat-cards').innerHTML =
    card('Orders completed', at.orders_completed, `today: ${td.orders_completed}`, 'good') +
    card('Orders failed', at.orders_failed, `today: ${td.orders_failed}`, at.orders_failed ? 'bad' : '') +
    card('Panels', at.panels, `today: ${td.panels}`) +
    card('Doors', at.doors, `today: ${td.doors}`) +
    card('Stiles', at.stiles, `today: ${td.stiles}`);

  document.getElementById('recent').innerHTML = (r.stats.recent || []).map(o => {
    const t = (o.timestamp_human || '').replace('T', ' ');
    return `<tr><td>${t}</td><td>${o.order_id}</td>` +
      `<td class="num">${o.panels}</td><td class="num">${o.doors}</td><td class="num">${o.stiles}</td>` +
      `<td class="num">${fmtDur(o.duration_seconds)}</td>` +
      `<td class="${o.success ? 'ok' : 'fail'}">${o.success ? '✓ completed' : '✗ ' + (o.message || 'failed')}</td></tr>`;
  }).join('') || '<tr><td colspan="7" style="color:var(--muted)">No orders recorded yet</td></tr>';

  document.getElementById('footer').textContent = `Last refresh ${r.server_time.replace('T',' ')} · auto-refreshes every 5 s`;
}

async function act(path, confirmMsg) {
  if (confirmMsg && !confirm(confirmMsg)) return;
  const msg = document.getElementById('action-msg');
  const btns = document.querySelectorAll('button');
  btns.forEach(b => b.disabled = true);
  msg.textContent = 'working…';
  try {
    const r = await (await fetch(path, {method: 'POST'})).json();
    msg.textContent = r.message;
  } catch (e) {
    msg.textContent = 'Request failed: ' + e;
  }
  btns.forEach(b => b.disabled = false);
  refresh();
}

document.getElementById('btn-start').onclick = () => act('/api/start');
document.getElementById('btn-restart').onclick = () =>
  act('/api/restart', 'Restart Fusion? Any order currently processing will be interrupted and its file left in order_processing.');

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


def main():
    global DATA_DIR, ADDIN_DIR, DROPBOX_DIR
    parser = argparse.ArgumentParser(description='Fusion pipeline dashboard')
    parser.add_argument('--host', default='0.0.0.0',
                        help='Bind address (default 0.0.0.0 = reachable on the LAN)')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data-dir', default=DEFAULT_DATA_DIR,
                        help='Folder containing pipeline_status.json / order_ledger.jsonl')
    parser.add_argument('--addin-dir', default=DEFAULT_ADDIN_DIR,
                        help='Fusion add-in folder (where restart_state.json is written)')
    parser.add_argument('--dropbox-dir', default=DEFAULT_DROPBOX_DIR,
                        help='Order dropbox folder (the queue of pending *.json orders)')
    parser.add_argument('--no-actions', action='store_true',
                        help='View-only: disable the start/restart buttons '
                             '(use when running anywhere other than the VM)')
    args = parser.parse_args()

    global ACTIONS_ENABLED
    DATA_DIR = Path(args.data_dir)
    ADDIN_DIR = Path(args.addin_dir)
    DROPBOX_DIR = Path(args.dropbox_dir)
    ACTIONS_ENABLED = not args.no_actions

    # On the VM (actions enabled), continuously auto-dismiss Fusion's
    # document-recovery prompt — it appears before the add-in loads, so it
    # can only be closed from an external process like this one.
    if ACTIONS_ENABLED:
        threading.Thread(target=recovery_watcher_loop,
                         name='RecoveryWatcher', daemon=True).start()
        threading.Thread(target=crash_recovery_loop,
                         name='CrashRecovery', daemon=True).start()

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f'Fusion Pipeline Dashboard')
    print(f'  data dir : {DATA_DIR}')
    print(f'  add-in   : {ADDIN_DIR}')
    print(f'  recovery : auto-dismiss {"ON" if ACTIONS_ENABLED else "OFF (view-only)"}')
    print(f'  serving  : http://localhost:{args.port}  (Ctrl+C to stop)')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
