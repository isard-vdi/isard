#!/usr/bin/env python3
"""Resolve category storage-pool disk dirs for backup from apiv4, never RethinkDB."""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import stat as stat_mod
import sys
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

ISARD_ROOT = "/isard"
HOST_ROOT = "/opt/isard"
POOLS_ROOT = ISARD_ROOT + "/storage_pools"

DEFAULT_EXCLUDES = ["*/volatile*"]

# Non-zero never means "no pools": the job must tell empty-stdout+0 from a fault.
EXIT_OK = 0
EXIT_API_ERROR = 3
EXIT_GUARD_FATAL = 4


@dataclass
class PoolResolution:
    kept: List[str] = field(default_factory=list)
    missing: List[Tuple[str, str]] = field(default_factory=list)


def _norm(path: str) -> str:
    """Strip surrounding whitespace and any trailing slashes (keep root '/')."""
    path = path.strip()
    if len(path) > 1:
        path = path.rstrip("/")
    return path


def map_prefixes(
    prefixes: Sequence[str],
    *,
    isard_root: Optional[str] = None,
    host_root: Optional[str] = None,
    pools_root: Optional[str] = None,
) -> List[str]:
    """Keep prefixes under /isard/storage_pools/, remap /isard -> /opt/isard, sort."""
    isard_root = (isard_root if isard_root is not None else ISARD_ROOT).rstrip("/")
    host_root = (host_root if host_root is not None else HOST_ROOT).rstrip("/")
    pools_root = (pools_root if pools_root is not None else POOLS_ROOT).rstrip("/")

    out = set()
    for raw in prefixes:
        p = _norm(raw)
        if not p or not p.startswith(pools_root + "/"):
            continue
        out.add(host_root + p[len(isard_root) :])
    return sorted(out)


def parse_excludes(raw: Optional[str]) -> List[str]:
    """Parse BACKUP_POOLS_EXCLUDE fnmatch patterns; unset -> default, "" -> none."""
    if raw is None:
        return list(DEFAULT_EXCLUDES)
    return [p for p in re.split(r"[,\s]+", raw.strip()) if p]


def apply_excludes(paths: Sequence[str], patterns: Sequence[str]) -> List[str]:
    """Drop paths matching any fnmatch pattern (patterns match the full path)."""
    return [p for p in paths if not any(fnmatch.fnmatch(p, pat) for pat in patterns)]


def drop_contained(paths: Sequence[str]) -> List[str]:
    """Drop directories nested inside another kept directory (keep the ancestor)."""
    norm = sorted({_norm(p) for p in paths})
    kept = []
    for p in norm:
        if any(q != p and p.startswith(q + "/") for q in norm):
            continue
        kept.append(p)
    return kept


def has_regular_file(path: str, *, walk: Callable = os.walk) -> bool:
    """True if the dir holds >=1 regular file; an unmounted pool mount is empty."""
    if not os.path.isdir(path):
        return False
    for root, _dirs, files in walk(path):
        for name in files:
            try:
                if stat_mod.S_ISREG(os.stat(os.path.join(root, name)).st_mode):
                    return True
            except OSError:
                continue
    return False


def dedupe_by_inode(paths: Sequence[str], *, stat: Callable = os.stat) -> List[str]:
    """Collapse same-inode paths (bind mounts/symlinks) to the shortest one."""
    seen = {}
    kept = []
    for p in sorted(set(paths), key=lambda x: (len(x), x)):
        try:
            st = stat(p)
        except OSError:
            kept.append(p)
            continue
        key = (st.st_dev, st.st_ino)
        if key in seen:
            continue
        seen[key] = p
        kept.append(p)
    return sorted(kept)


def resolve(prefixes: Sequence[str], *, excludes: Sequence[str]) -> PoolResolution:
    """Full pipeline from API prefixes to a guarded, de-duplicated dir list."""
    mapped = map_prefixes(prefixes)
    mapped = apply_excludes(mapped, excludes)
    mapped = drop_contained(mapped)
    mapped = dedupe_by_inode(mapped)

    result = PoolResolution()
    for p in mapped:
        if not os.path.isdir(p):
            result.missing.append((p, "missing: not a directory"))
        elif not has_regular_file(p):
            result.missing.append(
                (p, "empty: no regular files (pool filesystem not mounted?)")
            )
        else:
            result.kept.append(p)
    result.kept.sort()
    return result


def fetch_prefixes(service: str = "isard-backupninja") -> List[str]:
    """Fetch distinct ready-disk directory_path values from apiv4; raises on error."""
    from isardvdi_apiv4_client.api.role_admin import (
        admin_storage_migration_path_prefixes,
    )
    from isardvdi_apiv4_client.types import UNSET
    from isardvdi_apiv4_client_auth import build_client, raise_for_status

    with build_client(service) as client:
        resp = admin_storage_migration_path_prefixes.sync_detailed(client=client)
        raise_for_status(resp)
        parsed = resp.parsed

    prefixes = getattr(parsed, "prefixes", None)
    if prefixes is None or prefixes is UNSET:
        return []
    return list(prefixes)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve the host directories holding category storage-pool disks "
            "for the backupninja pools job."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print how many pool directories hold ready disks and exit.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    excludes = parse_excludes(os.environ.get("BACKUP_POOLS_EXCLUDE"))

    try:
        prefixes = fetch_prefixes()
    except Exception as e:  # noqa: BLE001 - any failure must be a clear non-zero
        print(
            f"ERROR: cannot fetch storage pool paths from apiv4: {e}",
            file=sys.stderr,
        )
        return EXIT_API_ERROR

    result = resolve(prefixes, excludes=excludes)

    if args.check:
        # an unmounted pool lands in `missing` and must still be counted
        total = len(result.kept) + len(result.missing)
        print(total)
        if result.missing:
            print(
                f"WARNING: {len(result.missing)} of {total} storage pool "
                "directories are unusable (missing/empty; filesystem not mounted?)",
                file=sys.stderr,
            )
        return EXIT_OK

    if result.missing:
        for path, reason in result.missing:
            print(f"FATAL: storage pool directory {path}: {reason}", file=sys.stderr)
        noun = "directory" if len(result.missing) == 1 else "directories"
        print(
            f"FATAL: {len(result.missing)} storage pool {noun} unusable; "
            "refusing to archive or prune the pools repo",
            file=sys.stderr,
        )
        return EXIT_GUARD_FATAL

    for path in result.kept:
        print(path)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
