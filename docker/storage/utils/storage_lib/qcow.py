# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import os
import re
import subprocess
from pathlib import Path
from time import time

from .formatting import format_time_remaining, log

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def uuid_from_path(path):
    """Extract UUID from a filename. Returns UUID string or None."""
    if not path:
        return None
    m = _UUID_RE.search(Path(path).name)
    return m.group(0) if m else None


def qemu_img_info(file_path):
    """Run qemu-img info -U --output=json on a file (non-invasive, no lock).

    Returns parsed json dict or None if the file is corrupted/invalid.
    """
    try:
        result = subprocess.run(
            ["qemu-img", "info", "-U", "--output=json", str(file_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=30,
        )
        return json.loads(result.stdout)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
    ):
        return None


def qemu_img_check(file_path):
    """Run qemu-img check -U on a qcow2 file (non-invasive, no lock).

    Returns True iff the file exists, qemu-img succeeded with returncode 0
    AND its stdout reports "No errors were found on the image". Any other
    outcome (file missing, returncode!=0, stderr error, leak warnings) is
    treated as "not safely intact" and returns False.

    Used as a pre-flight before classifying a `*.sparsify-backup` (or any
    other recovery copy) as deletable: if the canonical qcow2 partner is
    not provably clean, we must keep the backup.
    """
    try:
        result = subprocess.run(
            ["qemu-img", "check", "-U", str(file_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
    if result.returncode != 0:
        return False
    return "No errors were found on the image" in (result.stdout or "")


def qemu_img_chain_info(file_path):
    """Run qemu-img info -U --backing-chain --output=json on a file.

    Returns the parsed JSON list (head element is the queried file, followed
    by each ancestor in chain order), or None if the chain cannot be fully
    walked — i.e. any link is missing or unreadable.
    """
    try:
        result = subprocess.run(
            [
                "qemu-img",
                "info",
                "-U",
                "--backing-chain",
                "--output=json",
                str(file_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=60,
        )
        data = json.loads(result.stdout)
        return data if isinstance(data, list) else None
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
    ):
        return None


def get_backing_file(file_path):
    """Get the backing file path from a qcow2 image.

    Uses full-backing-filename (resolved absolute path) when available,
    falls back to backing-filename.
    Returns None if no backing file or file is corrupted.
    """
    info = qemu_img_info(file_path)
    if info is None:
        return None
    return info.get("full-backing-filename") or info.get("backing-filename") or None


def get_backing_chain(file_path):
    """Get the full backing chain output for a qcow2 image.

    Returns stdout string or None if the chain is broken/corrupted.
    """
    try:
        result = subprocess.run(
            ["qemu-img", "info", "-U", "--backing-chain", str(file_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=60,
        )
        return result.stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def get_full_info(file_path):
    """Get complete qcow2 metadata including actual-size, virtual-size, backing-filename."""
    info = qemu_img_info(file_path)
    if info is None:
        return None
    return {
        "actual-size": info.get("actual-size", 0),
        "virtual-size": info.get("virtual-size", 0),
        "backing-filename": info.get("backing-filename"),
        "full-backing-filename": info.get("full-backing-filename"),
    }


def analyze_integrity(qcow_files):
    """Check backing chain integrity for a list of qcow2 files.

    Returns list of files with broken backing chains.
    """
    broken = []
    total = len(qcow_files)
    processed = 0
    start_time = time()

    for qcow in qcow_files:
        if get_backing_chain(qcow) is None:
            broken.append(qcow)
        processed += 1

        if processed % 50 == 0 or processed == total:
            elapsed = time() - start_time
            if 0 < processed < total:
                avg = elapsed / processed
                remaining = avg * (total - processed)
                pct = (processed / total) * 100
                log(
                    f"  Checking integrity: {processed}/{total} ({pct:.1f}%)"
                    f" - Est. {format_time_remaining(remaining)} remaining"
                )
            elif processed == total:
                log(f"  Checking integrity: {processed}/{total} (100.0%) - Done")

    return broken


def analyze_dependencies(qcow_files):
    """Analyze backing file dependencies and categorize files.

    Returns dict with:
        wo_backing: files with no backing file (root images)
        wo_derivatives: files that no other file depends on (leaf images)
        dependency_map: {file: backing_file}
        reverse_map: {backing_file: [derivatives]}
    """
    dependency_map = {}
    reverse_map = {}
    total = len(qcow_files)
    processed = 0
    start_time = time()

    for qcow in qcow_files:
        backing_file = get_backing_file(qcow)
        dependency_map[qcow] = backing_file

        if backing_file:
            reverse_map.setdefault(backing_file, []).append(qcow)

        processed += 1
        if processed % 50 == 0 or processed == total:
            elapsed = time() - start_time
            if 0 < processed < total:
                avg = elapsed / processed
                remaining = avg * (total - processed)
                pct = (processed / total) * 100
                log(
                    f"  Analyzing dependencies: {processed}/{total} ({pct:.1f}%)"
                    f" - Est. {format_time_remaining(remaining)} remaining"
                )
            elif processed == total:
                log(f"  Analyzing dependencies: {processed}/{total} (100.0%) - Done")

    wo_backing = [f for f, b in dependency_map.items() if b is None]
    wo_derivatives = [f for f in qcow_files if f not in reverse_map]

    return {
        "wo_backing": wo_backing,
        "wo_derivatives": wo_derivatives,
        "dependency_map": dependency_map,
        "reverse_map": reverse_map,
    }


def analyze_integrity_and_dependencies(qcow_files, cache=None):
    """Single-pass integrity + dependency analysis with optional cache.

    Issues one `qemu-img info -U --backing-chain --output=json` per file
    and derives both broken-chain detection and immediate-backing-file
    mapping from the same result. For files whose chain cannot be walked,
    falls back to a metadata-only `qemu-img info` to recover the immediate
    backing reference, so the dependency graph stays accurate even when
    upstream ancestors are broken.

    When `cache` is provided (dict from storage_lib.cache.load_qcow_cache),
    each file's (mtime, size) are stat'd and compared with the cached
    entry. On a hit, the cached `broken` flag and `backing` path are
    reused and the qemu-img subprocess is skipped. On a miss (or when
    cache is None/empty), the subprocess runs as before.

    Returns (broken, deps, fresh_entries):
        broken         — list of files with broken backing chains
        deps           — same dict shape as analyze_dependencies()
        fresh_entries  — dict {path: {mtime, size, broken, backing}} for
                         every file scanned this run, ready to be passed
                         to storage_lib.cache.save_qcow_cache()
    """
    cache = cache or {}
    broken = []
    dependency_map = {}
    reverse_map = {}
    fresh_entries = {}
    cache_hits = 0
    total = len(qcow_files)
    processed = 0
    start_time = time()

    for qcow in qcow_files:
        try:
            st = os.stat(qcow)
            mtime = st.st_mtime
            size = st.st_size
        except OSError:
            mtime = None
            size = None

        cached = cache.get(qcow)
        use_cache = (
            cached is not None
            and mtime is not None
            and cached.get("mtime") == mtime
            and cached.get("size") == size
        )

        if use_cache:
            is_broken = bool(cached.get("broken"))
            backing_file = cached.get("backing")
            cache_hits += 1
        else:
            chain = qemu_img_chain_info(qcow)
            if chain is None:
                is_broken = True
                backing_file = get_backing_file(qcow)
            else:
                is_broken = False
                head = chain[0] if chain else {}
                backing_file = (
                    head.get("full-backing-filename")
                    or head.get("backing-filename")
                    or None
                )

        if mtime is not None:
            fresh_entries[qcow] = {
                "mtime": mtime,
                "size": size,
                "broken": is_broken,
                "backing": backing_file,
            }

        if is_broken:
            broken.append(qcow)
        dependency_map[qcow] = backing_file
        if backing_file:
            reverse_map.setdefault(backing_file, []).append(qcow)

        processed += 1
        if processed % 50 == 0 or processed == total:
            elapsed = time() - start_time
            if 0 < processed < total:
                avg = elapsed / processed
                remaining = avg * (total - processed)
                pct = (processed / total) * 100
                log(
                    f"  Analyzing integrity + dependencies:"
                    f" {processed}/{total} ({pct:.1f}%)"
                    f" - Est. {format_time_remaining(remaining)} remaining"
                )
            elif processed == total:
                log(
                    f"  Analyzing integrity + dependencies:"
                    f" {processed}/{total} (100.0%) - Done"
                    f" (cache hits: {cache_hits}/{total})"
                )

    wo_backing = [f for f, b in dependency_map.items() if b is None]
    wo_derivatives = [f for f in qcow_files if f not in reverse_map]

    return (
        broken,
        {
            "wo_backing": wo_backing,
            "wo_derivatives": wo_derivatives,
            "dependency_map": dependency_map,
            "reverse_map": reverse_map,
        },
        fresh_entries,
    )


def _build_uuid_index(search_dirs):
    """Build a dict mapping UUID -> file path for all qcow2 files in search_dirs."""
    index = {}
    for d in search_dirs:
        p = Path(d)
        if not p.is_dir():
            continue
        for f in p.rglob("*.qcow2"):
            uid = uuid_from_path(str(f))
            if uid and uid not in index:
                index[uid] = str(f)
    return index


def _walk_chain_to_break(file_path, max_depth=50):
    """Walk the backing chain from file_path until we find the broken link.

    Returns (broken_link, missing_path, missing_uuid) where:
        broken_link: the file whose backing reference points to a missing file
        missing_path: the path that doesn't exist
        missing_uuid: the UUID extracted from missing_path
    Or (file_path, None, None) if the file itself is corrupt (qemu-img fails).
    """
    current = str(file_path)
    visited = set()

    for _ in range(max_depth):
        if current in visited:
            return current, None, None  # circular reference
        visited.add(current)

        info = qemu_img_info(current)
        if info is None:
            # File is corrupt — qemu-img can't read it at all
            return current, None, None

        backing = info.get("full-backing-filename") or info.get("backing-filename")
        if not backing:
            # Root image — no backing file, shouldn't be in broken list
            return current, None, None

        if not Path(backing).exists():
            # Found the break: current references backing, which doesn't exist
            return current, backing, uuid_from_path(backing)

        # Backing exists — continue walking up the chain
        current = backing

    return current, None, None  # max depth reached


def diagnose_broken_chains(broken_files, search_dirs=None):
    """Diagnose each broken chain file: find what's missing and search for it.

    For each broken file:
    1. Walk the chain to find the exact broken link
    2. Extract the UUID of the missing backing file
    3. Search all search_dirs for that UUID at any location

    Args:
        broken_files: list of file paths with broken backing chains
        search_dirs: directories to search for relocated files
                     (default: ["/isard"])

    Returns list of dicts:
        file: the original broken file
        broken_link: the file whose backing reference is wrong
        missing_path: the path that doesn't exist
        missing_uuid: UUID extracted from missing_path
        found_at: actual location of the UUID on disk (or None)
        corrupt: True if qemu-img info fails entirely
        rebase_cmd: suggested fix command (or None)
    """
    if search_dirs is None:
        search_dirs = ["/isard"]

    log("Building UUID index for recovery search...")
    uuid_index = _build_uuid_index(search_dirs)
    log(f"  Indexed {len(uuid_index)} qcow2 files")

    results = []
    total = len(broken_files)
    start_time = time()

    for i, f in enumerate(broken_files, 1):
        broken_link, missing_path, missing_uuid = _walk_chain_to_break(f)

        corrupt = missing_path is None and broken_link == str(f)
        found_at = None
        rebase_cmd = None

        if missing_uuid and missing_uuid in uuid_index:
            found_at = uuid_index[missing_uuid]
            # Only suggest rebase if the found file is different from the missing path
            if found_at != missing_path:
                rebase_cmd = f"qemu-img rebase -u -b {found_at} -F qcow2 {broken_link}"

        results.append(
            {
                "file": str(f),
                "broken_link": broken_link,
                "missing_path": missing_path,
                "missing_uuid": missing_uuid,
                "found_at": found_at,
                "corrupt": corrupt,
                "rebase_cmd": rebase_cmd,
            }
        )

        if i % 50 == 0 or i == total:
            elapsed = time() - start_time
            if i < total:
                avg = elapsed / i
                remaining = avg * (total - i)
                log(
                    f"  Diagnosing: {i}/{total} ({i/total*100:.1f}%)"
                    f" - Est. {format_time_remaining(remaining)} remaining"
                )
            else:
                log(f"  Diagnosing: {i}/{total} (100.0%) - Done")

    return results


def is_file_in_use(file_path):
    """Check if a qcow2 file is in use by a hypervisor (locked).

    Runs qemu-img info WITHOUT -U flag — if the file is locked by a VM,
    it will fail with a lock error.

    Returns (in_use: bool, error_msg: str or None).
    """
    try:
        subprocess.run(
            ["qemu-img", "info", "--output=json", str(file_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=10,
        )
        return False, None
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip()
        if "lock" in stderr.lower() or "another process" in stderr.lower():
            return True, stderr
        # Other errors (file not found, etc.) — not "in use" but still an issue
        return False, stderr
    except subprocess.TimeoutExpired:
        # Timeout likely means the file is locked
        return True, "timeout (likely locked by hypervisor)"


def rebase_file(file_path, new_backing_path):
    """Run qemu-img rebase to fix a broken backing reference.

    First checks that the file is not in use by any hypervisor.
    Uses -u (unsafe) mode which only updates the metadata without
    rewriting data — fast and appropriate when the backing content is
    identical, just at a different path.

    Returns (success: bool, error: str or None).
    """
    # Safety: refuse to rebase a file that's in use by a VM
    in_use, lock_err = is_file_in_use(file_path)
    if in_use:
        return False, f"file is in use by hypervisor: {lock_err}"

    try:
        subprocess.run(
            [
                "qemu-img",
                "rebase",
                "-u",
                "-b",
                str(new_backing_path),
                "-F",
                "qcow2",
                str(file_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=30,
        )
        return True, None
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "timeout"


def create_incremental(file_path, backing_path):
    """Create a new empty qcow2 incremental disk with the given backing file.

    qemu-img create -f qcow2 -b <backing> -F qcow2 <file>

    Returns (success: bool, error: str or None).
    """
    try:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "qemu-img",
                "create",
                "-f",
                "qcow2",
                "-b",
                str(backing_path),
                "-F",
                "qcow2",
                str(file_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=30,
        )
        return True, None
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "timeout"


def sparsify_file(file_path):
    """Run virt-sparsify --in-place on a qcow2 file.

    Reclaims unused space within the image without creating a copy.
    Checks that the file is not in use by a hypervisor first.

    Returns (success: bool, saved_bytes: int, error: str or None).
    """
    file_path = str(file_path)
    in_use, lock_err = is_file_in_use(file_path)
    if in_use:
        return False, 0, f"file is in use by hypervisor: {lock_err}"

    try:
        before = Path(file_path).stat().st_size
    except OSError as e:
        return False, 0, str(e)

    try:
        subprocess.run(
            ["virt-sparsify", "--in-place", file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=600,
        )
        after = Path(file_path).stat().st_size
        return True, before - after, None
    except subprocess.CalledProcessError as e:
        return False, 0, e.stderr.strip()[:200]
    except subprocess.TimeoutExpired:
        return False, 0, "timeout (>10min)"


def compress_file(file_path):
    """Compress a qcow2 file in-place using qemu-img convert -c.

    Creates a compressed copy, then replaces the original.
    Checks that the file is not in use by a hypervisor first.

    Returns (success: bool, saved_bytes: int, error: str or None).
    """
    file_path = str(file_path)
    in_use, lock_err = is_file_in_use(file_path)
    if in_use:
        return False, 0, f"file is in use by hypervisor: {lock_err}"

    try:
        before = Path(file_path).stat().st_size
    except OSError as e:
        return False, 0, str(e)

    tmp_path = file_path + ".compress-tmp"
    try:
        subprocess.run(
            [
                "qemu-img",
                "convert",
                "-c",
                "-O",
                "qcow2",
                file_path,
                tmp_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=600,
        )
        # Replace original with compressed version
        import shutil

        shutil.move(tmp_path, file_path)
        after = Path(file_path).stat().st_size
        return True, before - after, None
    except subprocess.CalledProcessError as e:
        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)
        return False, 0, e.stderr.strip()[:200]
    except subprocess.TimeoutExpired:
        Path(tmp_path).unlink(missing_ok=True)
        return False, 0, "timeout (>10min)"
