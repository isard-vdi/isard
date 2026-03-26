# SPDX-License-Identifier: AGPL-3.0-or-later

import sys
import time
from pathlib import Path

from .formatting import format_size, log

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
    """Get all file paths in the volatile directory.

    Excludes the to_delete subdirectory (used by cleanup --move).
    """
    volatile = Path(base_path) / "volatile"
    if not volatile.is_dir():
        return []
    return [
        str(f)
        for f in volatile.rglob("*")
        if f.is_file() and "/to_delete/" not in str(f)
    ]


def count_templates(file_list):
    """Count files in /isard/templates directory."""
    return len([f for f in file_list if "/isard/templates" in str(f)])
