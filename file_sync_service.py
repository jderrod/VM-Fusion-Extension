"""
File Sync Service
Mirrors the pipeline's local output folders to the network shares.

Why this exists
---------------
Fusion used to copy each artifact straight to its network share the moment it
was produced. That copy happened inline, on Fusion's thread, so every order
paid the network cost before the next component could start -- and a machine
controller watching the share could see a half-written .nc file.

This service moves that work out of Fusion entirely. The add-in writes only
to local disk (see src/config.py); this process watches those folders and
copies to the shares in the background. Fusion starts the next order
immediately while the previous order's files are still going over the wire.

It is deliberately independent of Fusion: it runs as its own Scheduled Task,
survives Fusion crashes and the pipeline's self-restart cycle, and picks up
any backlog when it starts.

Behaviour
---------
* Local files are never modified or deleted. Local disk is the archive of
  record; a sync_state.json records what has already been copied so nothing
  is sent twice. A file is re-copied only if its size or mtime changes.
* Whether a file already exists at the destination is deliberately NOT
  checked. The machine controllers consume files out of the drop folders,
  so "missing at the destination" is the normal end state, not a gap to
  repair -- re-copying on absence would resend every consumed file forever.
  If a share genuinely needs rebuilding, use --resync.
* A file is only copied once it has been unmodified for --settle seconds, so
  a file Fusion is still writing is never picked up mid-write.
* Copies land on a .syncpart temp name in the destination folder and are then
  atomically renamed, so a machine controller never sees a partial file.
  ("*.nc" does not match "foo.nc.syncpart".)
* If a share is unreachable the affected files simply stay unsynced and are
  retried next cycle. Other shares keep working.

Usage
-----
    python file_sync_service.py                  # run forever, mode from autostart_config.json
    python file_sync_service.py --once           # single pass, then exit (useful for testing)
    python file_sync_service.py --mode LOCAL     # force a mode
    python file_sync_service.py --interval 10    # seconds between passes (default 15)
    python file_sync_service.py --verbose        # log every skip decision

Register it to run at VM boot with setup_sync_task.ps1.
"""

import argparse
import json
import logging
import os
import shutil
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

# The service ships inside the add-in package, next to src/config.py, so the
# path mapping always comes from the same config the add-in itself uses.
_ADDIN_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ADDIN_ROOT / 'src'))

import config  # noqa: E402

TEMP_SUFFIX = '.syncpart'
DEFAULT_INTERVAL = 15
DEFAULT_SETTLE = 5

logger = logging.getLogger('file_sync')

_shutdown = False


def _request_shutdown(signum, frame):
    """Finish the current file, then exit cleanly."""
    global _shutdown
    _shutdown = True
    logger.info('Shutdown requested (signal %s); finishing current pass', signum)


def resolve_run_mode(override=None) -> str:
    """Mode from --mode, else autostart_config.json, else VM.

    Defaulting to VM matters: this service only has a job to do in
    production, and on the VM it starts before anyone edits a config.
    """
    if override:
        return override.upper()
    try:
        # utf-8-sig: the packaged config may carry a BOM (see package_for_vm.ps1)
        with open(_ADDIN_ROOT / 'autostart_config.json', 'r', encoding='utf-8-sig') as f:
            mode = str(json.load(f).get('run_mode', '')).strip().upper()
        if mode in ('LOCAL', 'VM'):
            return mode
    except Exception:
        pass
    return 'VM'


def setup_logging(verbose=False):
    """Log to <local_base>/sync_logs/file_sync_<date>.log and stdout.

    Deliberately NOT under output/logs: that folder is mirrored, so every
    line this service logged would dirty the log, forcing a re-copy on the
    next pass, which would log another line. The service would never go
    quiet. sync_logs/ sits outside every sync source, so it stays local.
    """
    log_dir = Path(config.NETWORK_BASE) / 'sync_logs'
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f'file_sync_{datetime.now().strftime("%Y%m%d")}.log'
        handlers = [logging.FileHandler(log_file, encoding='utf-8'),
                    logging.StreamHandler(sys.stdout)]
    except OSError:
        # Never let a logging problem stop the service from syncing.
        handlers = [logging.StreamHandler(sys.stdout)]

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers,
    )


class SyncState:
    """Record of what has already been copied, keyed by pair + relative path.

    An entry stores the source file's size and mtime, so a file that is later
    rewritten or appended to (the rolling logs, mainly) is re-copied, while
    an untouched file is skipped forever.
    """

    def __init__(self, path: Path):
        self.path = path
        self.entries = {}
        self.dirty = False
        self._load()

    def _load(self):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                self.entries = json.load(f)
            logger.info('Loaded sync state: %d entries from %s',
                        len(self.entries), self.path)
        except FileNotFoundError:
            logger.info('No existing sync state; starting fresh at %s', self.path)
        except Exception as e:
            # A corrupt state file must not wedge the service. Worst case we
            # re-copy files that were already there, which is harmless.
            logger.warning('Could not read sync state (%s); starting fresh', e)
            self.entries = {}

    def is_synced(self, key: str, stat_result) -> bool:
        entry = self.entries.get(key)
        return (entry is not None
                and entry.get('size') == stat_result.st_size
                and entry.get('mtime_ns') == stat_result.st_mtime_ns)

    def mark(self, key: str, stat_result):
        self.entries[key] = {
            'size': stat_result.st_size,
            'mtime_ns': stat_result.st_mtime_ns,
            'synced_at': datetime.now().isoformat(timespec='seconds'),
        }
        self.dirty = True

    def prune(self, live_keys: set):
        """Drop entries for files that no longer exist locally."""
        stale = set(self.entries) - live_keys
        for key in stale:
            del self.entries[key]
        if stale:
            self.dirty = True
            logger.debug('Pruned %d stale state entries', len(stale))

    def save(self):
        if not self.dirty:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.json.tmp')
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.entries, f, indent=1)
            os.replace(tmp, self.path)
            self.dirty = False
        except Exception as e:
            logger.warning('Could not save sync state: %s', e)


def iter_source_files(source: Path, recursive: bool):
    """Yield (file_path, relative_path) for candidate files under source."""
    if not source.exists():
        return
    walker = source.rglob('*') if recursive else source.glob('*')
    for item in walker:
        try:
            if not item.is_file():
                continue
        except OSError:
            continue
        if item.name.endswith(TEMP_SUFFIX):
            continue
        yield item, item.relative_to(source)


def copy_atomic(src: Path, dest: Path):
    """Copy to a temp name in the destination folder, then rename into place.

    The rename is what makes this safe for the machine drops: a controller
    polling the share sees the file appear complete or not at all.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + TEMP_SUFFIX)
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dest)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def sync_pair(pair, state, settle_seconds, now):
    """Copy everything new under one source folder. Returns (copied, failed, keys)."""
    name = pair['name']
    source = Path(pair['source'])
    dest_root = Path(pair['dest'])
    copied = failed = 0
    keys = set()

    for src_file, rel in iter_source_files(source, pair['recursive']):
        if _shutdown:
            break
        try:
            st = src_file.stat()
        except OSError:
            continue

        key = f'{name}|{rel.as_posix()}'
        keys.add(key)

        if state.is_synced(key, st):
            continue

        # Still being written? Leave it for a later pass.
        age = now - st.st_mtime
        if age < settle_seconds:
            logger.debug('%s: %s still settling (%.1fs old)', name, rel, age)
            keys.discard(key)  # not a live key yet; don't let prune act on it
            continue

        dest_file = dest_root / rel
        try:
            copy_atomic(src_file, dest_file)
            state.mark(key, st)
            copied += 1
            logger.info('%s: copied %s -> %s', name, rel, dest_file)
        except Exception as e:
            failed += 1
            logger.warning('%s: FAILED %s -> %s (%s)', name, rel, dest_file, e)

    return copied, failed, keys


def run_pass(pairs, state, settle_seconds):
    """One full sweep across all configured pairs."""
    now = time.time()
    total_copied = total_failed = 0
    live_keys = set()

    for pair in pairs:
        if _shutdown:
            break
        copied, failed, keys = sync_pair(pair, state, settle_seconds, now)
        total_copied += copied
        total_failed += failed
        live_keys |= keys

    if not _shutdown:
        state.prune(live_keys)
    state.save()

    if total_copied or total_failed:
        logger.info('Pass complete: %d copied, %d failed', total_copied, total_failed)
    return total_copied, total_failed


def acquire_single_instance_lock(base: Path):
    """Best-effort guard against two copies of the service running at once.

    Two instances would not corrupt anything -- the atomic rename and the
    state file both tolerate it -- but they would fight over sync_state.json
    and double the network traffic.
    """
    try:
        import msvcrt
    except ImportError:
        return None
    try:
        base.mkdir(parents=True, exist_ok=True)
        handle = open(base / 'file_sync.lock', 'a+')
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return handle
    except OSError:
        return False
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mode', choices=['LOCAL', 'VM', 'local', 'vm'],
                        help='Override run mode (default: read autostart_config.json)')
    parser.add_argument('--interval', type=int, default=DEFAULT_INTERVAL,
                        help=f'Seconds between passes (default {DEFAULT_INTERVAL})')
    parser.add_argument('--settle', type=int, default=DEFAULT_SETTLE,
                        help=f'Seconds a file must be unmodified before copying '
                             f'(default {DEFAULT_SETTLE})')
    parser.add_argument('--once', action='store_true',
                        help='Run a single pass and exit')
    parser.add_argument('--resync', action='store_true',
                        help='Forget what has been copied and re-send every local '
                             'file. Use after rebuilding a share; it will resend '
                             'files the machines have already consumed.')
    parser.add_argument('--verbose', action='store_true',
                        help='Log skip decisions as well as copies')
    args = parser.parse_args()

    mode = resolve_run_mode(args.mode)
    config.set_run_mode(mode)

    setup_logging(args.verbose)

    base = Path(config.NETWORK_BASE)
    lock = acquire_single_instance_lock(base)
    if lock is False:
        logger.error('Another file sync service is already running; exiting')
        return 1

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)

    pairs = config.get_sync_pairs()
    state = SyncState(config.get_sync_state_file())

    if args.resync:
        logger.warning('--resync: clearing %d state entries; every local file '
                       'will be re-sent', len(state.entries))
        state.entries = {}
        state.dirty = True

    logger.info('=' * 60)
    logger.info('File Sync Service starting  (mode=%s, interval=%ds, settle=%ds)',
                mode, args.interval, args.settle)
    logger.info('Local base: %s', base)
    for pair in pairs:
        logger.info('  %-16s %s  ->  %s', pair['name'], pair['source'], pair['dest'])
    logger.info('=' * 60)

    if args.once:
        run_pass(pairs, state, args.settle)
        return 0

    while not _shutdown:
        try:
            run_pass(pairs, state, args.settle)
        except Exception as e:
            # Never let one bad pass kill the service; the VM has no one
            # watching to restart it.
            logger.exception('Unexpected error during sync pass: %s', e)

        for _ in range(args.interval):
            if _shutdown:
                break
            time.sleep(1)

    logger.info('File Sync Service stopped')
    return 0


if __name__ == '__main__':
    sys.exit(main())
