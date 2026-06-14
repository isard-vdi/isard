"""Materialise fake qcow2 backing chains and zero-byte ISO placeholders so the
engine can exercise start/stop/template flows against an anonymized DB.

All filesystem ops run inside a docker container (default `isard-storage`)
that has `qemu-img` and the same `/isard` mount the engine sees.
"""

from __future__ import annotations

import logging
import subprocess
import time
from collections import Counter, deque
from pathlib import PurePosixPath

from .progress import fmt_dur

log = logging.getLogger(__name__)

DEFAULT_VIRTUAL_SIZE = 10 * 1024 * 1024 * 1024  # 10 GiB


def _docker_run(
    container: str, *args: str, check: bool = True
) -> subprocess.CompletedProcess:
    cmd = ["docker", "exec", container, *args]
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def container_running(container: str) -> bool:
    try:
        out = subprocess.check_output(
            ["docker", "inspect", "-f", "{{.State.Running}}", container],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out == "true"
    except Exception:
        return False


def storage_path(row: dict) -> str:
    """Mirror engine's join: directory_path / "<id>.<type>"."""
    return str(
        PurePosixPath(row["directory_path"]) / f"{row['id']}.{row.get('type', 'qcow2')}"
    )


def topo_sort_storages(rows: list[dict]) -> list[dict]:
    """Return rows in parents-first order. Drops orphans, cycle members, and
    rows missing required fields (id, directory_path).
    """
    # Drop rows lacking the fields we need to materialise a qcow2 on disk.
    # Their children become orphans and are dropped by the existing FK check.
    valid = [r for r in rows if r.get("id") and r.get("directory_path")]
    dropped_invalid = len(rows) - len(valid)
    if dropped_invalid:
        missing = [r.get("id", "<no-id>") for r in rows if not r.get("directory_path")][
            :3
        ]
        log.warning(
            "dropping %d storage rows missing id/directory_path (e.g. %s)",
            dropped_invalid,
            missing,
        )
    by_id = {r["id"]: r for r in valid}
    indeg: dict[str, int] = {}
    children: dict[str, list[str]] = {rid: [] for rid in by_id}
    dropped_orphans: list[str] = []
    for r in valid:
        rid = r["id"]
        parent = (r.get("parent") or "").strip()
        if not parent:
            indeg[rid] = 0
        elif parent in by_id:
            indeg[rid] = 1
            children[parent].append(rid)
        else:
            dropped_orphans.append(rid)
    if dropped_orphans:
        log.warning(
            "dropping %d storage rows with missing parent (e.g. %s)",
            len(dropped_orphans),
            dropped_orphans[:3],
        )
    queue = deque([rid for rid, d in indeg.items() if d == 0])
    ordered: list[dict] = []
    while queue:
        rid = queue.popleft()
        ordered.append(by_id[rid])
        for c in children.get(rid, []):
            indeg[c] -= 1
            if indeg[c] == 0:
                queue.append(c)
    if len(ordered) != len(indeg):
        stuck = sorted(set(indeg) - {r["id"] for r in ordered})
        log.warning(
            "dropping %d storage rows stuck in parent FK cycle (e.g. %s)",
            len(stuck),
            stuck[:5],
        )
    return ordered


def _virtual_size(row: dict) -> int:
    qi = row.get("qemu-img-info") or row.get("qemu_img_info") or {}
    return int(qi.get("virtual-size") or DEFAULT_VIRTUAL_SIZE)


def _exists(container: str, path: str) -> bool:
    res = _docker_run(container, "test", "-e", path, check=False)
    return res.returncode == 0


def materialise_storage(
    rows: list[dict], container: str, force: bool = False
) -> Counter:
    """Create qcow2 files for `rows` (already topologically sorted). Returns counts."""
    counts: Counter = Counter()
    by_id = {r["id"]: r for r in rows}
    dirs_made: set[str] = set()
    total = len(rows)
    t0 = time.monotonic()
    every = max(1, total // 50)  # ~2% increments
    for idx, r in enumerate(rows, 1):
        if idx == 1 or idx == total or idx % every == 0:
            el = time.monotonic() - t0
            eta = el / idx * (total - idx) if idx else 0
            log.info(
                "  qcow2 [%5d/%5d] %3.0f%%  %s elapsed  ~%s left  "
                "(created %d skipped %d failed %d)",
                idx,
                total,
                idx / total * 100 if total else 100,
                fmt_dur(el),
                fmt_dur(eta),
                counts["created"],
                counts["skipped"],
                counts["failed"],
            )
        target = storage_path(r)
        # mkdir the parent of the actual target file, not directory_path: legacy
        # storage ids can contain '/' (e.g. "default/.../template_name"), nesting
        # the qcow2 below directory_path, so directory_path alone is not enough.
        directory = str(PurePosixPath(target).parent)
        if directory not in dirs_made:
            _docker_run(container, "mkdir", "-p", directory)
            dirs_made.add(directory)
        if _exists(container, target):
            if not force:
                counts["skipped"] += 1
                continue
            _docker_run(container, "rm", "-f", target)
            counts["replaced"] += 1
        size = str(_virtual_size(r))
        parent_id = (r.get("parent") or "").strip()
        cmd = ["qemu-img", "create", "-f", "qcow2"]
        if parent_id:
            parent_row = by_id.get(parent_id)
            if not parent_row:
                log.warning(
                    "parent %s missing for %s; creating without backing",
                    parent_id,
                    r["id"],
                )
            else:
                parent_target = storage_path(parent_row)
                cmd += ["-F", "qcow2", "-b", parent_target]
                counts["children"] += 1
        else:
            counts["roots"] += 1
        cmd += [target, size]
        try:
            _docker_run(container, *cmd)
            counts["created"] += 1
        except subprocess.CalledProcessError as e:
            log.error("qemu-img failed for %s: %s", r["id"], e.stderr.strip())
            counts["failed"] += 1
    return counts


def materialise_media(rows: list[dict], container: str, force: bool = False) -> Counter:
    counts: Counter = Counter()
    dirs_made: set[str] = set()
    total = len(rows)
    t0 = time.monotonic()
    every = max(1, total // 50)
    for idx, r in enumerate(rows, 1):
        if idx == 1 or idx == total or idx % every == 0:
            el = time.monotonic() - t0
            eta = el / idx * (total - idx) if idx else 0
            log.info(
                "  iso   [%5d/%5d] %3.0f%%  %s elapsed  ~%s left  "
                "(created %d skipped %d failed %d)",
                idx,
                total,
                idx / total * 100 if total else 100,
                fmt_dur(el),
                fmt_dur(eta),
                counts["created"],
                counts["skipped"],
                counts["failed"],
            )
        path = r.get("path_downloaded")
        if not path:
            counts["skipped_no_path"] += 1
            continue
        directory = str(PurePosixPath(path).parent)
        if directory not in dirs_made:
            _docker_run(container, "mkdir", "-p", directory)
            dirs_made.add(directory)
        if _exists(container, path) and not force:
            counts["skipped"] += 1
            continue
        try:
            _docker_run(container, "truncate", "-s", "0", path)
            counts["created"] += 1
        except subprocess.CalledProcessError as e:
            log.error("truncate failed for %s: %s", path, e.stderr.strip())
            counts["failed"] += 1
    return counts


def verify_chains(rows: list[dict], container: str, sample: int = 5) -> list[str]:
    """Run `qemu-img info --backing-chain` on a sample of leaves; return failures."""
    parent_ids = {(r.get("parent") or "").strip() for r in rows}
    parent_ids.discard("")
    leaves = [r for r in rows if r["id"] not in parent_ids]
    failures: list[str] = []
    for leaf in leaves[:sample]:
        target = storage_path(leaf)
        res = _docker_run(
            container, "qemu-img", "info", "--backing-chain", target, check=False
        )
        if res.returncode != 0:
            failures.append(f"{leaf['id']}: {res.stderr.strip()}")
    return failures
