#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Copy a disk image byte for byte without giving it more blocks than its data."""

import ctypes
import ctypes.util
import errno
import fcntl
import hashlib
import os
import secrets
import struct
import time

FICLONE = 0x40049409
FS_IOC_FIEMAP = 0xC020660B
FIEMAP_FLAG_SYNC = 0x1
FIEMAP_EXTENT_LAST = 0x1
FIEMAP_EXTENT_UNWRITTEN = 0x800
FALLOC_FL_KEEP_SIZE = 0x01
FALLOC_FL_PUNCH_HOLE = 0x02

BLOCK = 4096
#: shorter runs of zeros inside the data are written, not punched
MIN_HOLE = 64 * 1024
CHUNK = 4 * 1024 * 1024
_ZERO = memoryview(bytes(CHUNK))

_NO_CLONE = {
    errno.EXDEV,
    errno.EOPNOTSUPP,
    errno.ENOTTY,
    errno.EINVAL,
    errno.ENOSYS,
    errno.EBADF,
    errno.EPERM,
}
_NO_PUNCH = {errno.EOPNOTSUPP, errno.ENOSYS, errno.EINVAL}

_libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
_libc.fallocate.argtypes = [
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_longlong,
    ctypes.c_longlong,
]


class CopyCancelled(Exception):
    """The caller asked to stop; the destination was not created."""


class CopyVerificationError(RuntimeError):
    """The copy does not read like the source; the destination was not created."""


def temp_path(destination):
    """``.<name>.XXXXXX``, the pattern the scans recognise as an interrupted copy."""
    head, tail = os.path.split(destination)
    return os.path.join(head, f".{tail}.{secrets.token_hex(3)}")


def clone(src_fd, dst_fd):
    """``FICLONE``; ``False`` when the filesystem or the pair of mounts cannot."""
    try:
        fcntl.ioctl(dst_fd, FICLONE, src_fd)
    except OSError as exc:
        if exc.errno in _NO_CLONE:
            return False
        raise
    return True


def punch(fd, offset, length):
    """Punch a hole; ``False`` when the filesystem cannot."""
    if length <= 0:
        return True
    if _libc.fallocate(fd, FALLOC_FL_PUNCH_HOLE | FALLOC_FL_KEEP_SIZE, offset, length):
        err = ctypes.get_errno()
        if err in _NO_PUNCH:
            return False
        raise OSError(err, os.strerror(err))
    return True


def unwritten_extents(fd):
    """``[(offset, length)]`` of unwritten extents; ``None`` when not reported."""
    found = []
    start = 0
    count = 256
    header = struct.Struct("=QQIIII")
    extent = struct.Struct("=QQQQQIIII")
    while True:
        buf = bytearray(header.size + extent.size * count)
        header.pack_into(
            buf, 0, start, 2**64 - 1 - start, FIEMAP_FLAG_SYNC, 0, count, 0
        )
        try:
            fcntl.ioctl(fd, FS_IOC_FIEMAP, buf)
        except OSError as exc:
            if exc.errno in (
                errno.EOPNOTSUPP,
                errno.ENOTTY,
                errno.EINVAL,
                errno.ENOSYS,
            ):
                return None
            raise
        mapped = header.unpack_from(buf, 0)[3]
        if not mapped:
            return found
        last = False
        for i in range(mapped):
            logical, _phys, length, _r1, _r2, flags, *_ = extent.unpack_from(
                buf, header.size + i * extent.size
            )
            if flags & FIEMAP_EXTENT_UNWRITTEN:
                found.append((logical, length))
            start = logical + length
            last = bool(flags & FIEMAP_EXTENT_LAST)
        if last:
            return found


def data_regions(fd, size):
    """``(offset, end)`` of each data region; the whole file when unknown."""
    offset = 0
    while offset < size:
        try:
            start = os.lseek(fd, offset, os.SEEK_DATA)
        except OSError as exc:
            if exc.errno == errno.ENXIO:
                return
            if exc.errno == errno.EINVAL and offset == 0:
                yield 0, size
                return
            raise
        end = min(os.lseek(fd, start, os.SEEK_HOLE), size)
        yield start, end
        offset = end


def _block_chunks(fd, size):
    """File-aligned chunks covering, once each, every block touching a data region."""
    done = 0
    for start, end in data_regions(fd, size):
        offset = max(start - start % BLOCK, done)
        stop = min(-(-end // BLOCK) * BLOCK, size)
        while offset < stop:
            buf = os.pread(fd, min(CHUNK, stop - offset), offset)
            if not buf:
                return
            yield offset, buf
            offset += len(buf)
        done = max(done, offset)


def _nonzero_blocks(view):
    """Offsets in ``view`` of the blocks that hold a non-zero byte."""
    if _ZERO[: len(view)] == view:
        return []
    return [
        pos
        for pos in range(0, len(view), BLOCK)
        if _ZERO[: len(view[pos : pos + BLOCK])] != view[pos : pos + BLOCK]
    ]


def _runs(blocks, length):
    """Write runs of the non-zero blocks, bridging gaps shorter than ``MIN_HOLE``."""
    runs = []
    for pos in blocks:
        end = min(pos + BLOCK, length)
        if runs and pos - runs[-1][1] < MIN_HOLE:
            runs[-1][1] = end
        else:
            runs.append([pos, end])
    return runs


def _hash_blocks(digest, base, view, blocks):
    for pos in blocks:
        digest.update((base + pos).to_bytes(8, "little"))
        digest.update(view[pos : pos + BLOCK])


def content_digest(fd, size):
    """Digest of the non-zero blocks and their offsets, independent of layout."""
    digest = hashlib.sha256(size.to_bytes(8, "little"))
    for offset, buf in _block_chunks(fd, size):
        view = memoryview(buf)
        _hash_blocks(digest, offset, view, _nonzero_blocks(view))
    return digest.hexdigest()


def _throttle(started, done, bwlimit_kbs):
    if bwlimit_kbs:
        ahead = done / (bwlimit_kbs * 1024) - (time.monotonic() - started)
        if ahead > 0:
            time.sleep(ahead)


def sparse_copy(src_fd, dst_fd, size, *, bwlimit_kbs=0, on_bytes=None, cancelled=None):
    """Write only the non-zero data into a fresh file; ``(digest, written)``."""
    digest = hashlib.sha256(size.to_bytes(8, "little"))
    written = read = 0
    started = time.monotonic()
    # sized up front: no write extends the file, so nothing is preallocated past it
    os.ftruncate(dst_fd, size)
    os.posix_fadvise(src_fd, 0, 0, os.POSIX_FADV_SEQUENTIAL)
    for offset, buf in _block_chunks(src_fd, size):
        if cancelled is not None and cancelled():
            raise CopyCancelled()
        view = memoryview(buf)
        blocks = _nonzero_blocks(view)
        _hash_blocks(digest, offset, view, blocks)
        for start, end in _runs(blocks, len(view)):
            os.pwrite(dst_fd, view[start:end], offset + start)
            written += end - start
        read += len(buf)
        if on_bytes is not None:
            on_bytes(offset + len(buf), size)
        _throttle(started, read, bwlimit_kbs)
    return digest.hexdigest(), written


def _copy_metadata(src_stat, dst_fd):
    try:
        os.fchown(dst_fd, src_stat.st_uid, src_stat.st_gid)
    except PermissionError:
        pass
    os.fchmod(dst_fd, src_stat.st_mode & 0o7777)


def _fsync_dir(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def copy_disk(
    source,
    destination,
    *,
    bwlimit_kbs=0,
    on_bytes=None,
    cancelled=None,
    before_copy=None,
):
    """Clone or copy ``source`` under a temporary sibling, verify it, then rename.

    ``before_copy`` runs only when no clone is possible, before the first write.
    """
    src_stat = os.stat(source)
    size = src_stat.st_size
    tmp = temp_path(destination)
    src_fd = os.open(source, os.O_RDONLY)
    try:
        dst_fd = os.open(tmp, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            if clone(src_fd, dst_fd):
                method = "clone"
                written = 0
                if os.fstat(dst_fd).st_size != size:
                    raise CopyVerificationError(
                        f"clone of {source} has size {os.fstat(dst_fd).st_size}, not {size}"
                    )
                # a clone also shares the zeros the source wasted
                punch_supported = _punch_zero_runs(dst_fd, size, cancelled)
            else:
                method = "sparse"
                if before_copy is not None:
                    before_copy()
                punch_supported = None
                digest, written = sparse_copy(
                    src_fd,
                    dst_fd,
                    size,
                    bwlimit_kbs=bwlimit_kbs,
                    on_bytes=on_bytes,
                    cancelled=cancelled,
                )
                os.fsync(dst_fd)
                # drop the cached pages so the check reads what the storage holds
                os.posix_fadvise(dst_fd, 0, 0, os.POSIX_FADV_DONTNEED)
                if os.fstat(dst_fd).st_size != size:
                    raise CopyVerificationError(
                        f"copy of {source} has size {os.fstat(dst_fd).st_size}, not {size}"
                    )
                if content_digest(dst_fd, size) != digest:
                    raise CopyVerificationError(
                        f"copy of {source} does not read like the source"
                    )
            # unwritten extents read as zeros, so punching them changes no byte
            unwritten = unwritten_extents(dst_fd)
            reclaimed_unwritten = 0
            for off, length in unwritten or ():
                punch_supported = punch(dst_fd, off, length)
                if not punch_supported:
                    break
                reclaimed_unwritten += length
            _copy_metadata(src_stat, dst_fd)
            os.fsync(dst_fd)
            allocated = os.fstat(dst_fd).st_blocks * 512
        finally:
            os.close(dst_fd)
        os.utime(tmp, ns=(src_stat.st_atime_ns, src_stat.st_mtime_ns))
        os.rename(tmp, destination)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    finally:
        os.close(src_fd)
    _fsync_dir(os.path.dirname(destination) or ".")
    return {
        "method": method,
        "size": size,
        "source_allocated": src_stat.st_blocks * 512,
        "allocated": allocated,
        "written": written,
        "punch_supported": punch_supported,
        "unwritten_checked": unwritten is not None,
        "reclaimed_unwritten": reclaimed_unwritten,
    }


def _punch_zero_runs(fd, size, cancelled=None):
    """Punch zero runs of ``MIN_HOLE`` or more and unwritten extents; ``False`` if unsupported."""
    for offset, buf in _block_chunks(fd, size):
        if cancelled is not None and cancelled():
            raise CopyCancelled()
        view = memoryview(buf)
        cursor = 0
        for start, end in _runs(_nonzero_blocks(view), len(view)) + [
            [len(view), len(view)]
        ]:
            if start - cursor >= MIN_HOLE and not punch(
                fd, offset + cursor, start - cursor
            ):
                return False
            cursor = end
    for off, length in unwritten_extents(fd) or ():
        punch(fd, off, length)
    return True


def punch_zeros_in_place(path, cancelled=None):
    """Bytes freed by punching the zeros of ``path``, ``None`` if unsupported.

    Only for a file nobody else has open: a concurrent write could be punched.
    """
    fd = os.open(path, os.O_RDWR)
    try:
        size = os.fstat(fd).st_size
        before = os.fstat(fd).st_blocks * 512
        if not _punch_zero_runs(fd, size, cancelled):
            return None
        os.fsync(fd)
        return before - os.fstat(fd).st_blocks * 512
    finally:
        os.close(fd)
