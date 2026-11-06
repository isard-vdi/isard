# SPDX-License-Identifier: AGPL-3.0-or-later

"""QEMU's image locks: OFD locks on byte 100+bit (permission held) and 200+bit (not shared)."""

import errno
import fcntl
import os
import struct
from contextlib import contextmanager

PERM_BASE = 100
SHARED_BASE = 200
WRITE = 1
RESIZE = 3

F_OFD_GETLK = getattr(fcntl, "F_OFD_GETLK", 36)
F_OFD_SETLK = getattr(fcntl, "F_OFD_SETLK", 37)

#: struct flock on Linux 64-bit: l_type, l_whence, l_start, l_len, l_pid, padding
_FLOCK = struct.Struct("@hhqqi4x")


class WriterPresent(RuntimeError):
    """Another process holds the image with a permission that changes its content."""


def _flock(fd, cmd, lock_type, byte):
    raw = fcntl.fcntl(fd, cmd, _FLOCK.pack(lock_type, os.SEEK_SET, byte, 1, 0))
    return _FLOCK.unpack(raw)


def held_by_others(fd, byte):
    """Whether another open file description holds a lock on ``byte``."""
    lock_type = _flock(fd, F_OFD_GETLK, fcntl.F_WRLCK, byte)[0]
    return lock_type != fcntl.F_UNLCK


def _deny(fd, byte):
    try:
        _flock(fd, F_OFD_SETLK, fcntl.F_RDLCK, byte)
    except OSError as e:
        if e.errno in (errno.EAGAIN, errno.EACCES):
            raise WriterPresent(f"lock byte {byte} is held exclusively") from e
        raise


def writers(fd, perms=(WRITE, RESIZE)):
    """The permission bits of ``perms`` some other process holds on ``fd``'s file."""
    return [bit for bit in perms if held_by_others(fd, PERM_BASE + bit)]


@contextmanager
def no_writers(path, perms=(WRITE, RESIZE)):
    """Keep every writer off ``path`` while the block runs, and refuse if one is there.

    The shared bytes are taken first and the permission bytes read after, as QEMU
    does, so a writer that opens the image in between fails on our lock instead of
    slipping past the check. Readers (the descendants of a base) are unaffected.
    """
    fd = os.open(path, os.O_RDONLY)
    try:
        for bit in perms:
            _deny(fd, SHARED_BASE + bit)
        found = writers(fd, perms)
        if found:
            names = {WRITE: "write", RESIZE: "resize"}
            raise WriterPresent(
                f"{path} is open with {', '.join(names[b] for b in found)} permission by another process"
            )
        yield fd
    finally:
        os.close(fd)
