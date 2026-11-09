# SPDX-License-Identifier: AGPL-3.0-or-later

"""The zero scan counts unwritten extents from FIEMAP and reads only written data."""

import errno
import os

import pytest
from isardvdi_common.lib.storage import zeros

MIB = 1 << 20
BS = 4096


def _fiemap_buffer(extents, slots=None):
    slots = slots or max(len(extents), 1)
    buffer = bytearray(zeros._HEADER.size + slots * zeros._EXTENT.size)
    zeros._HEADER.pack_into(buffer, 0, 0, 0, 0, len(extents), slots, 0)
    for i, (logical, length, flags) in enumerate(extents):
        zeros._EXTENT.pack_into(
            buffer,
            zeros._HEADER.size + i * zeros._EXTENT.size,
            logical,
            logical + 7,
            length,
            0,
            0,
            flags,
            0,
            0,
            0,
        )
    return buffer


def test_the_struct_layout_is_the_kernels():
    assert (zeros._HEADER.size, zeros._EXTENT.size) == (32, 56)
    assert zeros.FS_IOC_FIEMAP == 0xC020660B
    assert zeros.FIEMAP_EXTENT_UNWRITTEN == 0x800


def test_the_parser_reads_each_extent_and_its_flags():
    unwritten = zeros.FIEMAP_EXTENT_UNWRITTEN
    buffer = _fiemap_buffer(
        [(0, MIB, 0), (4 * MIB, 8 * MIB, unwritten), (12 * MIB, MIB, 1)]
    )
    extents, last = zeros.parse_fiemap(buffer)
    assert extents == [(0, MIB, 0), (4 * MIB, 8 * MIB, unwritten), (12 * MIB, MIB, 1)]
    assert last is True


def test_the_parser_says_when_more_extents_follow():
    extents, last = zeros.parse_fiemap(_fiemap_buffer([(0, MIB, 0)], slots=4))
    assert extents == [(0, MIB, 0)] and last is False


def test_a_file_without_extents_is_the_last_page():
    assert zeros.parse_fiemap(_fiemap_buffer([])) == ([], True)


def test_fiemap_pages_on_from_the_end_of_the_previous_page():
    pages = [
        [(0, MIB, 0), (2 * MIB, MIB, 0)],
        [(5 * MIB, MIB, zeros.FIEMAP_EXTENT_LAST)],
    ]
    starts = []

    def ioctl(fd, request, buffer, mutate):
        assert request == zeros.FS_IOC_FIEMAP and mutate
        start, _, flags, _, count, _ = zeros._HEADER.unpack_from(buffer, 0)
        starts.append(start)
        assert flags & zeros.FIEMAP_FLAG_SYNC
        page = _fiemap_buffer(pages[len(starts) - 1], slots=count)
        buffer[: len(page)] = page

    got = list(zeros.fiemap(3, batch=2, ioctl=ioctl))
    assert [e[0] for e in got] == [0, 2 * MIB, 5 * MIB]
    assert starts == [0, 3 * MIB]


def _reader(data):
    return lambda size, at: bytes(data[at : at + size])


def test_only_whole_blocks_that_read_all_zeros_count():
    data = bytearray(8 * BS)
    data[BS + 5] = 1
    data[6 * BS] = 9
    assert zeros.count_zero_blocks(_reader(data), 0, len(data), BS, chunk=2 * BS) == (
        6 * BS
    )


def test_a_partial_block_at_either_end_does_not_count():
    data = bytearray(4 * BS)
    assert zeros.count_zero_blocks(_reader(data), 100, 3 * BS, BS) == 2 * BS


def test_unwritten_extents_count_without_being_read(monkeypatch, tmp_path):
    path = tmp_path / "d"
    path.write_bytes(b"")
    bs = os.stat(path).st_blksize
    path.write_bytes(b"\xab" * bs + bytes(3 * bs))
    unwritten = zeros.FIEMAP_EXTENT_UNWRITTEN
    monkeypatch.setattr(
        zeros, "extents", lambda fd: [(0, 4 * bs, 0), (64 * MIB, 8 * MIB, unwritten)]
    )
    read = []
    real_pread = os.pread
    monkeypatch.setattr(
        zeros.os, "pread", lambda fd, n, at: read.append(at) or real_pread(fd, n, at)
    )
    out = zeros.scan_zeros(str(path))
    assert out["unwritten_bytes"] == 8 * MIB
    assert out["zero_block_bytes"] == 3 * bs
    assert out["reclaimable_bytes"] == 8 * MIB + 3 * bs
    assert read and all(at < 4 * bs for at in read)


def test_without_fiemap_the_data_extents_come_from_seek_data(monkeypatch, tmp_path):
    path = tmp_path / "d"
    with open(path, "wb") as f:
        f.write(b"\xab" * MIB)
        f.seek(16 * MIB)
        f.write(bytes(MIB))

    def no_fiemap(fd):
        raise OSError(errno.EOPNOTSUPP, "no fiemap")
        yield

    monkeypatch.setattr(zeros, "fiemap", no_fiemap)
    out = zeros.scan_zeros(str(path))
    assert out["unwritten_bytes"] == 0
    assert out["read_bytes"] < 16 * MIB
    assert out["zero_block_bytes"] >= MIB - out["block_size"]


def test_punch_unwritten_punches_only_the_unwritten_extents(monkeypatch, tmp_path):
    path = tmp_path / "d"
    path.write_bytes(b"")
    os.truncate(path, 9 * MIB)
    unwritten = zeros.FIEMAP_EXTENT_UNWRITTEN
    monkeypatch.setattr(
        zeros,
        "fiemap",
        lambda fd: iter(
            [(0, MIB, 0), (MIB, 2 * MIB, unwritten), (8 * MIB, MIB, unwritten)]
        ),
    )
    calls = []
    punched = zeros.punch_unwritten(
        str(path), fallocate=lambda *args: calls.append(args[1:]) or 0
    )
    mode = zeros.FALLOC_FL_PUNCH_HOLE | zeros.FALLOC_FL_KEEP_SIZE
    assert calls == [(mode, MIB, 2 * MIB), (mode, 8 * MIB, MIB)]
    assert punched == 3 * MIB


def test_a_refused_punch_raises_with_the_errno(monkeypatch, tmp_path):
    path = tmp_path / "d"
    path.write_bytes(b"")
    os.truncate(path, MIB)
    monkeypatch.setattr(
        zeros, "fiemap", lambda fd: iter([(0, MIB, zeros.FIEMAP_EXTENT_UNWRITTEN)])
    )
    monkeypatch.setattr(zeros.ctypes, "get_errno", lambda: errno.EOPNOTSUPP)
    with pytest.raises(OSError) as raised:
        zeros.punch_unwritten(str(path), fallocate=lambda *args: -1)
    assert raised.value.errno == errno.EOPNOTSUPP


def test_a_filesystem_without_fiemap_has_nothing_to_punch(monkeypatch, tmp_path):
    path = tmp_path / "d"
    path.write_bytes(b"")

    def no_fiemap(fd):
        raise OSError(errno.ENOTTY, "no fiemap")

    monkeypatch.setattr(zeros, "fiemap", no_fiemap)
    assert zeros.punch_unwritten(str(path), fallocate=lambda *a: pytest.fail()) == 0


def _preallocated(path):
    """1 MiB data, a 4 MiB hole, 8 MiB preallocated, 2 MiB written zeros, 1 MiB data."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        os.pwrite(fd, b"\xab" * MIB, 0)
        os.posix_fallocate(fd, 5 * MIB, 8 * MIB)
        os.pwrite(fd, bytes(2 * MIB), 13 * MIB)
        os.pwrite(fd, b"\xcd" * MIB, 15 * MIB)
        os.fsync(fd)
    finally:
        os.close(fd)
    return str(path)


def _unwritten_supported(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        return any(f & zeros.FIEMAP_EXTENT_UNWRITTEN for _, _, f in zeros.fiemap(fd))
    except OSError:
        return False
    finally:
        os.close(fd)


def test_a_real_file_counts_preallocated_and_written_zeros(tmp_path):
    path = _preallocated(tmp_path / "d")
    if not _unwritten_supported(path):
        pytest.skip("this filesystem reports no unwritten extents through FIEMAP")
    out = zeros.scan_zeros(path)
    assert out["unwritten_bytes"] == 8 * MIB
    assert out["zero_block_bytes"] == 2 * MIB
    assert out["reclaimable_bytes"] == 10 * MIB
    assert out["read_bytes"] == 4 * MIB


def test_a_real_punch_frees_the_preallocation_and_reads_the_same(tmp_path):
    path = _preallocated(tmp_path / "d")
    if not _unwritten_supported(path):
        pytest.skip("this filesystem reports no unwritten extents through FIEMAP")
    before, blocks = open(path, "rb").read(), os.stat(path).st_blocks
    assert zeros.punch_unwritten(path) == 8 * MIB
    assert blocks - os.stat(path).st_blocks == 8 * MIB // 512
    assert open(path, "rb").read() == before
