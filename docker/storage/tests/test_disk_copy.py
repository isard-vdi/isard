# SPDX-License-Identifier: AGPL-3.0-or-later

"""``disk_copy`` copies a disk byte for byte without giving it more blocks."""

import errno
import filecmp
import os
import shutil

import pytest
from isardvdi_storage import disk_copy

MIB = 1 << 20
BLOCK = disk_copy.BLOCK


def _allocated(path):
    return os.stat(path).st_blocks * 512


def _write_at(path, pieces, size):
    """A file of ``size`` bytes with ``pieces`` ``(offset, bytes)`` and holes elsewhere."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.truncate(size)
        for offset, data in pieces:
            f.seek(offset)
            f.write(data)
        # flushed, so its block count includes what the filesystem adds on
        # writeback (an ext4 extent index block) as the fsynced copy's does
        os.fsync(f.fileno())
    return path


def _leftovers(directory):
    return [p for p in os.listdir(directory) if p.startswith(".")]


@pytest.fixture
def holes_supported(tmp_path):
    probe = _write_at(tmp_path / "probe", [(0, b"x")], 16 * MIB)
    if _allocated(probe) >= 8 * MIB:
        pytest.skip("the runner's filesystem does not keep holes")


class TestTheCopyReadsLikeTheSource:
    def test_holes_and_data_are_copied_byte_for_byte(self, tmp_path, holes_supported):
        src = _write_at(
            tmp_path / "a" / "d.qcow2",
            [(0, os.urandom(MIB)), (32 * MIB, os.urandom(3 * BLOCK))],
            64 * MIB,
        )
        dst = tmp_path / "b" / "d.qcow2"
        dst.parent.mkdir()

        report = disk_copy.copy_disk(str(src), str(dst))

        assert report["method"] == "sparse"
        assert filecmp.cmp(src, dst, shallow=False)
        assert os.stat(dst).st_size == 64 * MIB

    def test_the_check_reads_the_copy_from_storage(self, tmp_path, monkeypatch):
        """Over NFS a check from the client's page cache proves nothing, so the
        copy's cached pages are dropped before it is read back."""
        src = _write_at(tmp_path / "d.qcow2", [(0, os.urandom(MIB))], MIB)
        events = []
        real_fadvise = os.posix_fadvise
        real_digest = disk_copy.content_digest

        def fadvise(fd, offset, length, advice):
            if advice == os.POSIX_FADV_DONTNEED:
                events.append(("dropped", fd))
            return real_fadvise(fd, offset, length, advice)

        def digest(fd, size):
            events.append(("read", fd))
            return real_digest(fd, size)

        monkeypatch.setattr(disk_copy.os, "posix_fadvise", fadvise)
        monkeypatch.setattr(disk_copy, "content_digest", digest)

        disk_copy.copy_disk(str(src), str(tmp_path / "out.qcow2"))

        assert events[-2][0] == "dropped"
        assert events[-1] == ("read", events[-2][1])

    def test_a_qcow2_header_and_its_backing_reference_are_kept(self, tmp_path):
        header = b"QFI\xfb" + b"\0" * 60 + b"/isard/templates/base.qcow2"
        src = _write_at(tmp_path / "d.qcow2", [(0, header)], 4 * MIB)
        dst = tmp_path / "out.qcow2"

        disk_copy.copy_disk(str(src), str(dst))

        assert dst.read_bytes()[: len(header)] == header

    def test_mode_and_times_follow_the_source(self, tmp_path):
        """``rsync -a`` kept them, and the idempotent redelivery compares mtime."""
        src = _write_at(tmp_path / "d.qcow2", [(0, b"data")], MIB)
        os.chmod(src, 0o640)
        os.utime(src, ns=(1_700_000_000_000_000_000, 1_700_000_000_123_456_789))
        dst = tmp_path / "out.qcow2"

        disk_copy.copy_disk(str(src), str(dst))

        assert os.stat(dst).st_mode & 0o7777 == 0o640
        assert os.stat(dst).st_mtime_ns == os.stat(src).st_mtime_ns


class TestTheCopyIsNoBiggerThanItsData:
    def test_written_zeros_come_back_as_holes(self, tmp_path, holes_supported):
        """The disk an old copy inflated gets its space back on the next one."""
        src = tmp_path / "d.qcow2"
        with open(src, "wb") as f:
            f.write(os.urandom(2 * MIB))
            f.write(b"\0" * (62 * MIB))
        assert _allocated(src) >= 60 * MIB
        dst = tmp_path / "out.qcow2"

        disk_copy.copy_disk(str(src), str(dst))

        assert filecmp.cmp(src, dst, shallow=False)
        assert _allocated(dst) < 4 * MIB

    def test_scattered_data_never_takes_more_blocks_than_the_source(
        self, tmp_path, holes_supported
    ):
        """Blocks of data alone in a hole stay alone: rounding them up to a
        bigger unit would make the copy bigger than the free-space floor
        reserved for it."""
        pieces = [(i * MIB, os.urandom(BLOCK)) for i in range(32)]
        src = _write_at(tmp_path / "d.qcow2", pieces, 32 * MIB)
        dst = tmp_path / "out.qcow2"

        disk_copy.copy_disk(str(src), str(dst))

        assert filecmp.cmp(src, dst, shallow=False)
        assert _allocated(dst) <= _allocated(src)

    def test_short_runs_of_zeros_inside_data_are_written(self, tmp_path):
        """Below MIN_HOLE a run of zeros is kept, so the copy is not cut into
        4 KiB extents."""
        data = os.urandom(BLOCK) + bytes(2 * BLOCK) + os.urandom(BLOCK)
        src = _write_at(tmp_path / "d.qcow2", [(0, data)], len(data))
        dst = tmp_path / "out.qcow2"

        report = disk_copy.copy_disk(str(src), str(dst))

        assert report["written"] == len(data)
        assert filecmp.cmp(src, dst, shallow=False)

    def test_nothing_is_preallocated(self, tmp_path, holes_supported):
        src = _write_at(tmp_path / "d.qcow2", [(0, b"x")], 256 * MIB)
        dst = tmp_path / "out.qcow2"

        disk_copy.copy_disk(str(src), str(dst))

        assert _allocated(dst) < MIB

    def test_no_unwritten_extent_is_left(self, tmp_path):
        """Unwritten extents read as zeros and hold blocks: the copy has none."""
        src = tmp_path / "d.qcow2"
        with open(src, "wb") as f:
            f.write(os.urandom(MIB))
            try:
                os.posix_fallocate(f.fileno(), MIB, 8 * MIB)
            except OSError:
                pytest.skip("the runner's filesystem cannot preallocate")
        with open(src, "rb") as f:
            if disk_copy.unwritten_extents(f.fileno()) is None:
                pytest.skip("the runner's filesystem cannot report unwritten extents")
        dst = tmp_path / "out.qcow2"

        disk_copy.copy_disk(str(src), str(dst))

        with open(dst, "rb") as f:
            assert disk_copy.unwritten_extents(f.fileno()) == []
        assert filecmp.cmp(src, dst, shallow=False)


class TestTheNameIsTakenOnlyByAVerifiedCopy:
    def test_a_copy_that_does_not_read_like_the_source_is_refused(
        self, tmp_path, monkeypatch
    ):
        src = _write_at(tmp_path / "d.qcow2", [(0, os.urandom(MIB))], 2 * MIB)
        dst = tmp_path / "out.qcow2"
        monkeypatch.setattr(disk_copy, "content_digest", lambda fd, size: "other")

        with pytest.raises(disk_copy.CopyVerificationError):
            disk_copy.copy_disk(str(src), str(dst))

        assert not dst.exists()
        assert _leftovers(tmp_path) == []

    def test_a_cancel_leaves_nothing_behind(self, tmp_path):
        src = _write_at(tmp_path / "d.qcow2", [(0, os.urandom(MIB))], 2 * MIB)
        dst = tmp_path / "out.qcow2"

        with pytest.raises(disk_copy.CopyCancelled):
            disk_copy.copy_disk(str(src), str(dst), cancelled=lambda: True)

        assert not dst.exists()
        assert _leftovers(tmp_path) == []

    def test_a_failed_write_leaves_the_previous_destination_whole(
        self, tmp_path, monkeypatch
    ):
        """The copy goes under a temporary sibling: a destination that was
        already there is replaced only by a whole, verified file."""
        src = _write_at(tmp_path / "d.qcow2", [(0, os.urandom(MIB))], 2 * MIB)
        dst = tmp_path / "out.qcow2"
        dst.write_bytes(b"previous")

        def _full(*a, **k):
            raise OSError(errno.ENOSPC, "No space left on device")

        monkeypatch.setattr(disk_copy.os, "pwrite", _full)

        with pytest.raises(OSError):
            disk_copy.copy_disk(str(src), str(dst))

        assert dst.read_bytes() == b"previous"
        assert _leftovers(tmp_path) == []

    def test_the_temporary_name_is_one_the_scans_recognise(self):
        """``scan_backing_index`` lists ``.<name>.qcow2.*`` as an interrupted copy."""
        tmp = disk_copy.temp_path("/isard/templates/t.qcow2")
        head, tail = os.path.split(tmp)
        assert head == "/isard/templates"
        assert tail.startswith(".t.qcow2.")

    def test_the_source_is_never_written(self, tmp_path):
        src = _write_at(
            tmp_path / "d.qcow2",
            [(0, os.urandom(MIB)), (8 * MIB, b"\0" * MIB)],
            16 * MIB,
        )
        before = (src.read_bytes(), os.stat(src).st_mtime_ns)

        disk_copy.copy_disk(str(src), str(tmp_path / "out.qcow2"))

        assert (src.read_bytes(), os.stat(src).st_mtime_ns) == before


class TestTheFloorRunsOnlyForARealCopy:
    def test_a_copy_that_cannot_clone_runs_the_floor_before_writing(self, tmp_path):
        src = _write_at(tmp_path / "d.qcow2", [(0, b"x")], MIB)
        dst = tmp_path / "out.qcow2"

        def _refuse():
            raise RuntimeError("floor")

        with pytest.raises(RuntimeError, match="floor"):
            disk_copy.copy_disk(str(src), str(dst), before_copy=_refuse)

        assert not dst.exists()
        assert _leftovers(tmp_path) == []

    def test_a_clone_allocates_nothing_and_skips_the_floor(self, tmp_path, monkeypatch):
        src = _write_at(tmp_path / "d.qcow2", [(0, os.urandom(MIB))], 2 * MIB)
        dst = tmp_path / "out.qcow2"

        def _clone(src_fd, dst_fd):
            os.lseek(src_fd, 0, os.SEEK_SET)
            with open(src_fd, "rb", closefd=False) as s, open(
                dst_fd, "wb", closefd=False
            ) as d:
                shutil.copyfileobj(s, d)
            return True

        monkeypatch.setattr(disk_copy, "clone", _clone)
        floor = []

        report = disk_copy.copy_disk(
            str(src), str(dst), before_copy=lambda: floor.append(1)
        )

        assert report["method"] == "clone"
        assert floor == []
        assert filecmp.cmp(src, dst, shallow=False)

    def test_a_real_clone_reads_like_the_source(self, tmp_path, allow_clone):
        src = _write_at(tmp_path / "d.qcow2", [(0, os.urandom(MIB))], 4 * MIB)
        dst = tmp_path / "out.qcow2"

        report = disk_copy.copy_disk(str(src), str(dst))

        if report["method"] != "clone":
            pytest.skip("the runner's filesystem cannot clone")
        assert filecmp.cmp(src, dst, shallow=False)


class TestProgressAndRate:
    def test_progress_reaches_the_end(self, tmp_path):
        src = _write_at(tmp_path / "d.qcow2", [(0, os.urandom(9 * MIB))], 9 * MIB)
        seen = []

        disk_copy.copy_disk(
            str(src),
            str(tmp_path / "out.qcow2"),
            on_bytes=lambda d, t: seen.append((d, t)),
        )

        assert seen and seen[-1] == (9 * MIB, 9 * MIB)
        assert [d for d, _ in seen] == sorted(d for d, _ in seen)

    def test_a_bandwidth_limit_slows_the_copy(self, tmp_path, monkeypatch):
        src = _write_at(tmp_path / "d.qcow2", [(0, os.urandom(8 * MIB))], 8 * MIB)
        slept = []
        monkeypatch.setattr(disk_copy.time, "sleep", slept.append)

        disk_copy.copy_disk(str(src), str(tmp_path / "out.qcow2"), bwlimit_kbs=1024)

        # 8 MiB at 1 MiB/s: the copy waits about seven seconds in total
        assert sum(slept) > 5


class TestPunchingInPlace:
    def test_a_downloaded_file_gives_back_its_zeros(self, tmp_path, holes_supported):
        path = tmp_path / "download.qcow2"
        with open(path, "wb") as f:
            f.write(os.urandom(MIB))
            f.write(b"\0" * (31 * MIB))
            f.write(os.urandom(BLOCK))
        reference = tmp_path / "reference"
        shutil.copyfile(path, reference)

        freed = disk_copy.punch_zeros_in_place(str(path))

        if freed is None:
            pytest.skip("the runner's filesystem cannot punch holes")
        assert freed >= 30 * MIB
        assert filecmp.cmp(path, reference, shallow=False)

    def test_short_runs_of_zeros_are_left_alone(self, tmp_path):
        path = tmp_path / "d.qcow2"
        data = os.urandom(BLOCK) + bytes(4 * BLOCK) + os.urandom(BLOCK)
        path.write_bytes(data)
        before = _allocated(path)

        disk_copy.punch_zeros_in_place(str(path))

        assert _allocated(path) == before
        assert path.read_bytes() == data


class TestContentDigest:
    def test_the_same_content_with_another_layout_has_the_same_digest(
        self, tmp_path, holes_supported
    ):
        data = os.urandom(MIB)
        dense = tmp_path / "dense"
        with open(dense, "wb") as f:
            f.write(data)
            f.write(b"\0" * (3 * MIB))
        sparse = _write_at(tmp_path / "sparse", [(0, data)], 4 * MIB)

        with open(dense, "rb") as a, open(sparse, "rb") as b:
            assert disk_copy.content_digest(
                a.fileno(), 4 * MIB
            ) == disk_copy.content_digest(b.fileno(), 4 * MIB)

    def test_one_changed_byte_changes_the_digest(self, tmp_path):
        a = _write_at(tmp_path / "a", [(0, b"\1" * MIB)], 2 * MIB)
        b = _write_at(tmp_path / "b", [(0, b"\1" * MIB), (MIB + 7, b"\2")], 2 * MIB)

        with open(a, "rb") as fa, open(b, "rb") as fb:
            assert disk_copy.content_digest(
                fa.fileno(), 2 * MIB
            ) != disk_copy.content_digest(fb.fileno(), 2 * MIB)
