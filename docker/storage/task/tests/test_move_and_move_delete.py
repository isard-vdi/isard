# SPDX-License-Identifier: AGPL-3.0-or-later

"""Destructive path of the storage worker: ``task.move`` and
``task.move_delete``.

Both relocate a real disk on disk — ``move`` (``mv`` branch) renames/moves the
file and drops the source; ``move_delete`` renames the file into a sibling
``deleted/`` directory. These had no coverage, and a data-relocation path
without a test is exactly the one that costs the most when it regresses. The
tests operate on real files under ``tmp_path`` so the actual move happens (the
function under test is never mocked); only the guard branches assert on the
raised ``ValueError``.
"""

import pytest


def _write(path, content=b"disk-bytes"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class TestMove:
    def test_mv_relocates_file_and_drops_source(self, tmp_path):
        import task

        src = _write(tmp_path / "src" / "d.qcow2")
        dst = tmp_path / "dst" / "d.qcow2"

        rc = task.move(str(src), str(dst), method="mv")

        assert rc == 0
        assert dst.read_bytes() == b"disk-bytes"  # data really moved
        assert not src.exists()  # source really gone

    def test_auto_uses_mv_within_same_filesystem(self, tmp_path):
        import task

        src = _write(tmp_path / "a" / "d.qcow2")
        dst = tmp_path / "b" / "d.qcow2"
        # tmp_path is a single filesystem, so auto resolves to mv and moves it.
        rc = task.move(str(src), str(dst), method="auto")
        assert rc == 0
        assert dst.exists() and not src.exists()

    def test_missing_source_raises_valueerror(self, tmp_path):
        import task

        with pytest.raises(ValueError):
            task.move(str(tmp_path / "nope.qcow2"), str(tmp_path / "d.qcow2"), "mv")

    def test_invalid_method_raises_valueerror(self, tmp_path):
        import task

        src = _write(tmp_path / "d.qcow2")
        with pytest.raises(ValueError):
            task.move(str(src), str(tmp_path / "out" / "d.qcow2"), method="bogus")

    def test_identical_destination_removes_source_when_requested(self, tmp_path):
        import task

        # Same basename + same mtime + same size => _same_file True.
        src = _write(tmp_path / "src" / "d.qcow2")
        dst = _write(tmp_path / "dst" / "d.qcow2")
        import os

        st = os.stat(src)
        os.utime(dst, (st.st_atime, st.st_mtime))  # equalise mtime

        task.move(str(src), str(dst), method="mv", remove_source_file=True)
        # Idempotent no-op move still honours remove_source_file: source dropped,
        # destination left intact.
        assert not src.exists()
        assert dst.exists()

    def test_identical_destination_keeps_source_when_not_removing(self, tmp_path):
        import os

        import task

        src = _write(tmp_path / "src" / "d.qcow2")
        dst = _write(tmp_path / "dst" / "d.qcow2")
        st = os.stat(src)
        os.utime(dst, (st.st_atime, st.st_mtime))

        rc = task.move(str(src), str(dst), method="mv", remove_source_file=False)
        assert rc == 0
        assert src.exists() and dst.exists()  # nothing removed


class TestMoveDelete:
    def test_relocates_into_deleted_subdir(self, tmp_path):
        import task

        src = _write(tmp_path / "group" / "d.qcow2")

        rc = task.move_delete(str(src))

        assert rc == 0
        moved = tmp_path / "group" / "deleted" / "d.qcow2"
        assert moved.read_bytes() == b"disk-bytes"  # bytes preserved in deleted/
        assert not src.exists()  # original path cleared

    def test_missing_file_raises_valueerror(self, tmp_path):
        import task

        with pytest.raises(ValueError):
            task.move_delete(str(tmp_path / "group" / "gone.qcow2"))
