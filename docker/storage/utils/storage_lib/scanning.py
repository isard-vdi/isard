# SPDX-License-Identifier: AGPL-3.0-or-later

import sys
import time
from pathlib import Path

from .formatting import format_size, log
from .qcow import is_file_in_use

ISARD_DIRS = ["groups", "templates", "volatile", "storage_pools"]


def scan_files(scan_path, extension="qcow2", progress_interval=10):
    """Scan a directory recursively for files matching extension.

    Args:
        scan_path: Directory to scan.
        extension: File extension to filter (None or "all" for no filter).
        progress_interval: Seconds between progress log messages.

    Returns:
        List of Path objects for matching files.
    """
    path = Path(scan_path)
    if not path.is_dir():
        print(f"Error: {scan_path} is not a directory", file=sys.stderr)
        sys.exit(1)

    if extension and extension != "all":
        pattern = f"*.{extension}"
    else:
        pattern = "*"

    log(f"Counting files in {scan_path} (pattern: {pattern})...")
    start = time.time()
    all_files = [f for f in path.rglob(pattern) if f.is_file()]
    log(f"Found {len(all_files)} files ({time.time() - start:.1f}s)")
    return all_files


def scan_isard_dirs(base_path="/isard"):
    """Scan standard IsardVDI directories and return all file paths as strings.

    Scans: groups, templates, volatile, storage_pools
    """
    all_files = []
    base = Path(base_path)

    for dirname in ISARD_DIRS:
        dirpath = base / dirname
        if dirpath.is_dir():
            log(f"  Scanning {dirname} directory...")
            all_files.extend(
                str(f)
                for f in dirpath.rglob("*")
                if f.is_file() and "/to_delete/" not in str(f)
            )

    return all_files


def get_volatile_storages(base_path="/isard"):
    """Get file paths in the volatile directory that are safe to delete.

    Excludes:
      - the to_delete subdirectory (used by cleanup --move)
      - any .qcow2 file currently locked by a running hypervisor (live
        desktop). The volatile dir holds per-domain ephemeral state; while
        a desktop is running, the canonical qemu-img write lock is held
        on its volatile qcow2 and the file MUST NOT be removed.

    Non-qcow2 files are returned without a lock check (qemu-img's lock
    test only meaningfully applies to qcow2).
    """
    volatile = Path(base_path) / "volatile"
    if not volatile.is_dir():
        return []

    safe = []
    skipped_in_use = []
    for f in volatile.rglob("*"):
        if not f.is_file() or "/to_delete/" in str(f):
            continue
        f_str = str(f)
        if f.suffix == ".qcow2":
            in_use, _ = is_file_in_use(f_str)
            if in_use:
                skipped_in_use.append(f_str)
                continue
        safe.append(f_str)

    if skipped_in_use:
        log(
            f"  get_volatile_storages: skipped {len(skipped_in_use)} "
            f"qcow2 file(s) currently locked by a running hypervisor"
        )
        for path in skipped_in_use:
            log(f"    in-use: {path}")

    return safe


def count_templates(file_list):
    """Count files in /isard/templates directory."""
    return len([f for f in file_list if "/isard/templates" in str(f)])
