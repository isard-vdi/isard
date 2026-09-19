# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fabricate qcow2 images with a known integrity fault, for the disk-repair
tests and the live reproduction.

Both faults are made by editing the refcount table of a freshly created qcow2 v3
— no special tooling, just ``qemu-img``/``qemu-io`` and ``struct`` — so a test
exercises a REAL ``qemu-img check`` / ``check -r`` rather than a mock.

- :func:`fabricate_leaky_qcow2` -> one leaked cluster: ``qemu-img check`` reports
  ``leaks=1 corruptions=0`` and exits 3. ``qemu-img check -r leaks`` repairs it.
- :func:`fabricate_corrupt_qcow2` -> one ``OFLAG_COPIED ... refcount=0``
  corruption (the production kind): ``qemu-img check`` exits 2. ``-r leaks``
  cannot fix it; ``-r all`` can.

qcow2 v3 header fields read here (big-endian): ``cluster_bits`` at 20,
``l1_table_offset`` at 40, ``refcount_table_offset`` at 48, ``refcount_order``
at 96. A refcount-table entry points, cluster-aligned, at a refcount block whose
entries are ``1 << refcount_order`` bits wide (default 4 -> 16-bit entries).
"""

import json
import struct
import subprocess

_HEADER_LEN = 104
_REFT_ENTRY_OFFSET_MASK = (
    0xFFFFFFFFFFFFFE00  # a refcount-table entry is cluster-aligned
)
_RC_FMT = {1: ">B", 2: ">H", 4: ">I", 8: ">Q"}


def _create_with_data(path):
    """A fresh qcow2 v3 with 4 MiB written, so it has metadata AND data clusters
    and a populated first refcount block to edit."""
    subprocess.run(
        ["qemu-img", "create", "-f", "qcow2", str(path), "64M"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["qemu-io", "-c", "write -P 0xab 0 4M", str(path)],
        check=True,
        capture_output=True,
    )


def _geometry(head):
    assert head[:4] == b"QFI\xfb", "not a qcow2 image"
    cluster_size = 1 << struct.unpack(">I", head[20:24])[0]
    l1_table_offset = struct.unpack(">Q", head[40:48])[0]
    refcount_table_offset = struct.unpack(">Q", head[48:56])[0]
    entry_bytes = (1 << struct.unpack(">I", head[96:100])[0]) // 8
    assert entry_bytes in _RC_FMT, "unsupported (sub-byte) refcount width"
    return cluster_size, l1_table_offset, refcount_table_offset, entry_bytes


def _first_refcount_block(fh, refcount_table_offset):
    fh.seek(refcount_table_offset)
    block = struct.unpack(">Q", fh.read(8))[0] & _REFT_ENTRY_OFFSET_MASK
    assert block, "no first refcount block"
    return block


def _first_data_cluster(path, cluster_size):
    out = subprocess.run(
        ["qemu-img", "map", "--output=json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    for extent in json.loads(out.stdout):
        if extent.get("data") and "offset" in extent:
            return extent["offset"] // cluster_size
    raise AssertionError("image has no data extent")


def fabricate_leaky_qcow2(path):
    """One leaked cluster, no corruption. Bumps the refcount of the L1-table
    cluster (metadata, referenced exactly once by the header) to 2: refcount 2 vs
    1 reference is a pure leak. A data cluster can't be used — ``qemu-io`` writes
    it with ``OFLAG_COPIED`` (refcount must be 1), so bumping one trips a
    corruption too."""
    _create_with_data(path)
    with open(path, "r+b") as fh:
        cluster_size, l1_off, reft_off, entry_bytes = _geometry(fh.read(_HEADER_LEN))
        block = _first_refcount_block(fh, reft_off)
        pos = block + (l1_off // cluster_size) * entry_bytes
        fh.seek(pos)
        current = struct.unpack(_RC_FMT[entry_bytes], fh.read(entry_bytes))[0]
        fh.seek(pos)
        fh.write(struct.pack(_RC_FMT[entry_bytes], current + 1))
    return str(path)


def fabricate_corrupt_qcow2(path):
    """One ``OFLAG_COPIED ... refcount=0`` corruption. Zeroes the refcount of the
    first data cluster: it is referenced by an L2 entry with the COPIED flag (so
    its refcount must be 1), which is exactly the production fault."""
    _create_with_data(path)
    with open(path, "rb") as fh:
        cluster_size, _l1_off, reft_off, entry_bytes = _geometry(fh.read(_HEADER_LEN))
    data_cluster = _first_data_cluster(path, cluster_size)
    with open(path, "r+b") as fh:
        block = _first_refcount_block(fh, reft_off)
        fh.seek(block + data_cluster * entry_bytes)
        fh.write(struct.pack(_RC_FMT[entry_bytes], 0))
    return str(path)
