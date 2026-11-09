# SPDX-License-Identifier: AGPL-3.0-or-later

"""The exact count of the zeros a file allocates, and the unwritten extents a dig must punch."""

import ctypes
import ctypes.util
import errno
import fcntl
import os
import struct

FS_IOC_FIEMAP = 0xC020660B
FIEMAP_FLAG_SYNC = 0x1
FIEMAP_EXTENT_LAST = 0x1
FIEMAP_EXTENT_UNWRITTEN = 0x800
FIEMAP_MAX_OFFSET = 0xFFFFFFFFFFFFFFFF

FALLOC_FL_KEEP_SIZE = 0x1
FALLOC_FL_PUNCH_HOLE = 0x2

#: What a dig raises when the filesystem cannot punch holes; the change-handler reads it.
DIG_HOLES_UNSUPPORTED = "cannot punch holes on this filesystem"

_HEADER = struct.Struct("=QQIIII")
_EXTENT = struct.Struct("=QQQ2QI3I")
_BATCH = 512
_CHUNK = 8 << 20

_NO_FIEMAP = (errno.EOPNOTSUPP, errno.ENOTTY, errno.EINVAL)


def parse_fiemap(buffer):
    """``([(logical, length, flags)], last)`` from a filled ``struct fiemap`` buffer."""
    _, _, _, mapped, _, _ = _HEADER.unpack_from(buffer, 0)
    extents, last = [], False
    for i in range(mapped):
        logical, _, length, _, _, flags, _, _, _ = _EXTENT.unpack_from(
            buffer, _HEADER.size + i * _EXTENT.size
        )
        extents.append((logical, length, flags))
        last = last or bool(flags & FIEMAP_EXTENT_LAST)
    return extents, last or mapped == 0


def fiemap(fd, batch=_BATCH, ioctl=fcntl.ioctl):
    """Every extent of ``fd`` as ``(logical, length, flags)``, flushed first."""
    start = 0
    while True:
        buffer = bytearray(_HEADER.size + batch * _EXTENT.size)
        _HEADER.pack_into(
            buffer, 0, start, FIEMAP_MAX_OFFSET - start, FIEMAP_FLAG_SYNC, 0, batch, 0
        )
        ioctl(fd, FS_IOC_FIEMAP, buffer, True)
        extents, last = parse_fiemap(buffer)
        yield from extents
        if last or not extents:
            return
        logical, length, _ = extents[-1]
        start = logical + length


def _seek_data_extents(fd):
    """Data extents by SEEK_DATA/SEEK_HOLE; none reads as unwritten."""
    size = os.fstat(fd).st_size
    offset = 0
    while offset < size:
        try:
            data = os.lseek(fd, offset, os.SEEK_DATA)
        except OSError as e:
            if e.errno == errno.ENXIO:
                return
            raise
        hole = os.lseek(fd, data, os.SEEK_HOLE)
        yield data, hole - data, 0
        offset = hole


def extents(fd):
    """The file's extents, FIEMAP or SEEK_DATA, clipped to its size.

    An extent at or past EOF is dropped and one straddling EOF is cut to it:
    a filesystem that preallocates past the end of the file (XFS speculative
    preallocation) allocates those blocks itself and gives them back on its
    own; they are not zeros the file holds for a dig to reclaim.
    """
    size = os.fstat(fd).st_size
    try:
        raw = list(fiemap(fd))
    except OSError as e:
        if e.errno not in _NO_FIEMAP:
            raise
        raw = list(_seek_data_extents(fd))
    return [
        (logical, min(length, size - logical), flags)
        for logical, length, flags in raw
        if logical < size
    ]


def count_zero_blocks(read, offset, length, block_size, chunk=_CHUNK):
    """Bytes of whole ``block_size`` blocks reading all zeros in ``[offset, offset+length)``."""
    first = -(-offset // block_size) * block_size
    end = offset + length
    zeros, zero_chunk, zero_block = 0, bytes(chunk), bytes(block_size)
    position = first
    while position + block_size <= end:
        size = min(chunk, (end - position) // block_size * block_size)
        data = read(size, position)
        if not data:
            break
        if data == zero_chunk[: len(data)]:
            zeros += len(data) // block_size * block_size
        else:
            for start in range(0, len(data) - block_size + 1, block_size):
                if data[start : start + block_size] == zero_block:
                    zeros += block_size
        position += len(data)
    return zeros


def scan_zeros(path, on_progress=None):
    """Exact zeros a dig can give back: unwritten extents plus all-zero written blocks."""
    fd = os.open(path, os.O_RDONLY)
    try:
        stat = os.fstat(fd)
        block_size = stat.st_blksize or 4096
        unwritten = zero_blocks = read_bytes = 0
        for logical, length, flags in extents(fd):
            if flags & FIEMAP_EXTENT_UNWRITTEN:
                unwritten += length
                continue
            zero_blocks += count_zero_blocks(
                lambda size, at: os.pread(fd, size, at), logical, length, block_size
            )
            read_bytes += length
            if on_progress:
                on_progress(read_bytes)
        return {
            "reclaimable_bytes": unwritten + zero_blocks,
            "unwritten_bytes": unwritten,
            "zero_block_bytes": zero_blocks,
            "read_bytes": read_bytes,
            "allocated_bytes": stat.st_blocks * 512,
            "block_size": block_size,
        }
    finally:
        os.close(fd)


def _libc_fallocate():
    libc = ctypes.CDLL(ctypes.util.find_library("c") or None, use_errno=True)
    fallocate = libc.fallocate
    fallocate.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_longlong,
        ctypes.c_longlong,
    ]
    return fallocate


def punch_unwritten(path, fallocate=None):
    """Punch every unwritten extent within ``path``; returns the bytes punched.

    Extents at or past EOF (XFS speculative preallocation) are the filesystem's
    own and are left for it to reclaim; only the file's allocation is punched.
    """
    fd = os.open(path, os.O_RDWR)
    try:
        size = os.fstat(fd).st_size
        try:
            unwritten = [
                (logical, min(length, size - logical))
                for logical, length, flags in fiemap(fd)
                if flags & FIEMAP_EXTENT_UNWRITTEN and logical < size
            ]
        except OSError as e:
            if e.errno in _NO_FIEMAP:
                return 0
            raise
        if not unwritten:
            return 0
        fallocate = fallocate or _libc_fallocate()
        for logical, length in unwritten:
            if fallocate(
                fd, FALLOC_FL_PUNCH_HOLE | FALLOC_FL_KEEP_SIZE, logical, length
            ):
                code = ctypes.get_errno()
                raise OSError(code, os.strerror(code), path)
        return sum(length for _, length in unwritten)
    finally:
        os.close(fd)
