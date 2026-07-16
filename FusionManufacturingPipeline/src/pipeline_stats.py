"""
Pipeline status heartbeat + order ledger for the external dashboard.

Written from inside Fusion (folder_monitor); read by
dashboard/pipeline_dashboard.py running outside Fusion. Files live under
OUTPUT_BASE/dashboard/ so the dashboard can reach them over the network share:

- pipeline_status.json — overwritten every ~15 s and on order events
- order_ledger.jsonl   — one JSON line appended per finished order

All writes are best-effort and swallow errors: a dashboard/share hiccup must
never break order processing.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import process_health


def dashboard_dir() -> Path:
    from config import OUTPUT_BASE
    return Path(OUTPUT_BASE) / 'dashboard'


def write_heartbeat(state: str, version: str, queue_size: int = 0,
                    current_order: str = None, session_completed: int = 0,
                    session_failed: int = 0):
    """Overwrite the status file. state: monitoring|processing|stopped|restarting.

    Atomic-ish (temp file + os.replace) so the dashboard never reads a
    half-written JSON.
    """
    try:
        from config import RUN_MODE
        d = dashboard_dir()
        d.mkdir(parents=True, exist_ok=True)
        payload = {
            'state': state,
            'version': version,
            'run_mode': RUN_MODE,
            'pid': os.getpid(),
            'timestamp': time.time(),
            'timestamp_human': datetime.now().isoformat(timespec='seconds'),
            'current_order': current_order,
            'queue_size': queue_size,
            'thread_count': process_health.get_thread_count(),
            'thread_restart_threshold': process_health.THREAD_RESTART_THRESHOLD,
            'memory_mb': round(process_health.get_process_working_set_mb()),
            'memory_restart_threshold_mb': process_health.MEMORY_RESTART_THRESHOLD_MB,
            'session_completed': session_completed,
            'session_failed': session_failed,
            'progress': _read_progress(),
        }
        target = d / 'pipeline_status.json'
        tmp = d / 'pipeline_status.json.tmp'
        tmp.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        os.replace(str(tmp), str(target))
    except Exception:
        pass


def _progress_path():
    return dashboard_dir() / 'current_progress.json'


def write_progress(order_id: str, component: str, index: int, total: int, step: str):
    """Record where the current order is (which component + step) for the
    dashboard's in-order progress bar. Called from order_processor as it works."""
    try:
        d = dashboard_dir()
        d.mkdir(parents=True, exist_ok=True)
        payload = {
            'order_id': order_id,
            'component': component,
            'index': index,
            'total': total,
            'step': step,
            'timestamp': time.time(),
        }
        p = _progress_path()
        tmp = p.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(payload), encoding='utf-8')
        os.replace(str(tmp), str(p))
    except Exception:
        pass


def clear_progress():
    """Remove the in-order progress (called when idle / between orders)."""
    try:
        _progress_path().unlink(missing_ok=True)
    except Exception:
        pass


def _read_progress():
    try:
        return json.loads(_progress_path().read_text(encoding='utf-8'))
    except Exception:
        return None


def append_order_record(order_id: str, success: bool, component_counts: dict,
                        duration_seconds: float, message: str = ''):
    """Append one finished order to the ledger (component counts from the
    order JSON — panels/doors/stiles attempted in that order)."""
    try:
        d = dashboard_dir()
        d.mkdir(parents=True, exist_ok=True)
        record = {
            'timestamp': time.time(),
            'timestamp_human': datetime.now().isoformat(timespec='seconds'),
            'order_id': order_id,
            'success': bool(success),
            'panels': int(component_counts.get('panels', 0)),
            'doors': int(component_counts.get('doors', 0)),
            'stiles': int(component_counts.get('stiles', 0)),
            'duration_seconds': round(float(duration_seconds), 1),
            'message': str(message)[:300],
        }
        with open(d / 'order_ledger.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')
    except Exception:
        pass
