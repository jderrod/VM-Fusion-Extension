"""
Per-order component checkpoint for mid-order restart/resume.

A large order (many panels/doors/stiles) can accumulate enough leaked GPU
threads to need a restart BEFORE it finishes. Re-running the whole order after
a restart would loop forever on any order bigger than the thread budget, so
instead we checkpoint each component as it completes. On resume, already-done
components are skipped and the order continues — guaranteeing forward progress
(a 90-component order finishes in a few restart cycles instead of never).

Each component is self-contained (it applies its own parameters to the shared
model and exports its own outputs), so skipping completed components and
resuming at the next one is safe — no cross-component model state to preserve.
The only cross-component output is the compiled drilling file (built from every
component at order-end), so we store each component's drilling payload in the
checkpoint and restore it on resume to keep that file complete.

Checkpoints live on the network (survive a Fusion restart), keyed by the order
file's stem (stable across the re-queue cycle; only the final archived copy
gets a timestamped name). The checkpoint is deleted when the order fully
completes.
"""
import json
import os
from pathlib import Path


def _checkpoint_dir() -> Path:
    from config import OUTPUT_BASE
    d = Path(OUTPUT_BASE) / 'checkpoints'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(order_stem: str) -> Path:
    return _checkpoint_dir() / f'{order_stem}.checkpoint.json'


def read(order_stem: str) -> dict:
    """Return {comp_id: payload} for components already completed this order.

    payload holds {'json_key', 'drilling_paired_data'} so the compiled drilling
    output can be rebuilt on resume. Empty dict if no checkpoint.
    """
    try:
        p = _path(order_stem)
        if not p.exists():
            return {}
        data = json.loads(p.read_text(encoding='utf-8'))
        return data.get('components', {})
    except Exception:
        return {}


def mark_completed(order_stem: str, comp_id: str, json_key: str = None,
                   drilling_paired_data=None):
    """Record that a component finished, with the data needed to rebuild the
    compiled drilling file on resume. Written incrementally (after every
    component) so a crash mid-order still leaves prior progress checkpointed."""
    try:
        comps = read(order_stem)
        comps[comp_id] = {'json_key': json_key,
                          'drilling_paired_data': drilling_paired_data}
        p = _path(order_stem)
        tmp = p.with_suffix('.json.tmp')
        tmp.write_text(json.dumps({'order': order_stem, 'components': comps}, indent=2),
                       encoding='utf-8')
        os.replace(str(tmp), str(p))
    except Exception:
        pass


def clear(order_stem: str):
    """Delete the checkpoint (call when the order fully completes)."""
    try:
        _path(order_stem).unlink(missing_ok=True)
    except Exception:
        pass
