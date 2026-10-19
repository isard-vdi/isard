# SPDX-License-Identifier: AGPL-3.0-or-later

"""The one answer to "what on-disk disks read through this backing file".

Header-only (offset 0x08 / size 0x10, no qemu-img), so a whole estate maps in
seconds. The index and the query here are the single primitive every caller
shares -- the recycle bin's purge guard (direct, with a covered set), the
Integrity pass (transitive) and the CLI census all build one index and ask one
question instead of each reimplementing the walk."""

import os
import re
import struct

QCOW2_MAGIC = b"QFI\xfb"

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def uuid_from_path(path):
    """Extract UUID from a filename. Returns UUID string or None."""
    if not path:
        return None
    m = _UUID_RE.search(os.path.basename(path))
    return m.group(0) if m else None


def read_backing(path, _read=65536):
    """Read a qcow2's backing-file reference straight from its header.

    :return: ``(backing_str, readable)`` -- ``backing_str`` is the raw stored
        reference or None when the image has no backing file; ``readable`` is
        False only when the file is not a readable qcow2, which a caller must
        treat as "cannot tell", never as "no backing"."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(_read)
            if head[:4] != QCOW2_MAGIC or len(head) < 20:
                return None, head[:4] == QCOW2_MAGIC
            off = struct.unpack(">Q", head[8:16])[0]
            size = struct.unpack(">I", head[16:20])[0]
            if not off or not size or size > 4096:
                return None, True
            if off + size <= len(head):
                raw = head[off : off + size]
            else:
                fh.seek(off)
                raw = fh.read(size)
    except OSError:
        return None, False
    return raw.decode("utf-8", "replace"), True


def build_backing_index(paths):
    """Map every qcow2 in *paths* to its uuid, size and backing reference.

    Reads headers only (see :func:`read_backing`) -- no qemu-img. Returns
    ``{path: {"uuid", "size", "backing_raw", "backing_uuid", "readable"}}``."""
    index = {}
    for p in paths:
        backing_raw, readable = read_backing(p)
        try:
            size = os.stat(p).st_size
        except OSError:
            size = 0
        index[p] = {
            "uuid": uuid_from_path(p),
            "size": size,
            "backing_raw": backing_raw,
            "backing_uuid": uuid_from_path(backing_raw) if backing_raw else None,
            "readable": readable,
        }
    return index


def _reads_through(entry, target_path, target_uuid):
    """Whether an index entry's backing resolves to target, uuid first (robust
    to a moved pointer), exact path otherwise."""
    if target_uuid and entry["backing_uuid"] == target_uuid:
        return True
    return bool(entry["backing_raw"]) and entry["backing_raw"] == target_path


def dependents_of(
    target_path, index, *, transitive=False, covered_paths=(), live_uuids=None
):
    """The disks in *index* that read through *target_path*: the single
    "what depends on this disk" query.

    ``transitive`` follows the chain to any depth, else direct children only.
    ``covered_paths`` are paths the caller already removes (a purge taking them
    too); never counted, and *target_path* is always skipped. ``live_uuids``, if
    given, keeps only candidates whose own uuid is live. Returns
    ``(dependents, unreadable)``, both sorted path lists; an unreadable candidate
    is reported, never silently treated as not-a-dependent."""
    skip = set(covered_paths) | {target_path}
    unreadable = sorted(
        p for p, e in index.items() if p not in skip and not e["readable"]
    )
    found = set()
    frontier = [(target_path, uuid_from_path(target_path))]
    walked = set()
    while frontier:
        tp, tu = frontier.pop()
        if tp in walked:
            continue
        walked.add(tp)
        for p, e in index.items():
            if p in skip or not _reads_through(e, tp, tu):
                continue
            # keep walking THROUGH a non-live intermediate to reach a live leaf;
            # the live filter only decides what counts, not what to traverse
            if transitive and p not in walked:
                frontier.append((p, e["uuid"]))
            if live_uuids is None or e["uuid"] in live_uuids:
                found.add(p)
    return sorted(found), unreadable
