# SPDX-License-Identifier: AGPL-3.0-or-later
"""Persistent cache for expensive qemu-img chain inspection.

The chain analyzer runs `qemu-img info -U --backing-chain` once per qcow2
file, which dominates cleanup runtime when the storage tree has tens of
thousands of disks. Output of that subprocess depends only on the file's
on-disk content; for an unchanged file (same mtime + size) the result is
guaranteed identical.

This module persists per-file results to a single JSON file so the next
run can skip the subprocess for any file that hasn't changed since the
previous run. The cleanup CLI's `--rescan` flag bypasses the read side
but the writer always runs so future runs benefit.

Cache shape:

    {
        "version": 1,
        "entries": {
            "/isard/groups/abc.qcow2": {
                "mtime": 1746780123.45,
                "size": 4836884480,
                "broken": false,
                "backing": "/isard/templates/parent.qcow2"
            },
            ...
        }
    }

Only fields actually consumed by analyze_integrity_and_dependencies are
stored (broken flag + immediate backing path). The full chain JSON is
not cached — it's never read after analysis and would balloon the file.
"""

import json
from pathlib import Path

from .formatting import log

CACHE_VERSION = 1
DEFAULT_CACHE_PATH = Path("/logs/analyze/_cache/qcow_chain_info.json")


def load_qcow_cache(cache_path=DEFAULT_CACHE_PATH):
    """Load the qcow chain cache from disk.

    Returns dict keyed by absolute file path. Empty dict on any failure
    (missing file, unreadable, wrong schema version, malformed JSON).
    """
    cache_path = Path(cache_path)
    if not cache_path.exists():
        log(f"  No qcow cache at {cache_path} — full scan this run.")
        return {}

    try:
        with open(cache_path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log(f"  WARNING: could not read qcow cache {cache_path}: {e}")
        return {}

    if not isinstance(data, dict) or data.get("version") != CACHE_VERSION:
        log(
            f"  WARNING: qcow cache at {cache_path} has unknown schema"
            f" (version={data.get('version') if isinstance(data, dict) else '?'},"
            f" expected {CACHE_VERSION}) — discarding."
        )
        return {}

    entries = data.get("entries", {})
    if not isinstance(entries, dict):
        return {}
    log(f"  Loaded qcow cache: {len(entries)} entries from {cache_path}")
    return entries


def save_qcow_cache(entries, cache_path=DEFAULT_CACHE_PATH):
    """Persist the qcow chain cache to disk.

    Only entries passed in are written — entries from the previous cache
    that no longer exist on disk are dropped by virtue of not appearing
    in `entries` (callers populate it only with files seen this run).

    Writes atomically via tmp + rename so a crash mid-write doesn't leave
    a corrupt cache.
    """
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {"version": CACHE_VERSION, "entries": entries}
    tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    try:
        with open(tmp, "w") as f:
            json.dump(payload, f)
        tmp.replace(cache_path)
    except OSError as e:
        log(f"  WARNING: could not write qcow cache {cache_path}: {e}")
        return

    log(f"  Saved qcow cache: {len(entries)} entries to {cache_path}")
