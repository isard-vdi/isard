# SPDX-License-Identifier: AGPL-3.0-or-later

"""The destination free-space floor on ``task.move``.

A migration drains hundreds of disks over a night, so the free space on the
destination pool at plan time says nothing about the space left when the 200th
disk copies. The only place the number is true is the worker, immediately before
the copy — and only the worker can see the pool mounts at all (apiv4 and the
scheduler have no /isard). These tests pin that guard: it refuses the copy while
there is still room to refuse it, instead of filling the filesystem.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import task  # noqa: E402


def _sized(tmp_path, name, nbytes):
    p = tmp_path / name
    p.write_bytes(b"\0" * nbytes)
    return str(p)


def test_move_refuses_when_the_copy_would_breach_the_floor(tmp_path, monkeypatch):
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    # 4 KiB free, a 1 KiB disk and a 8 KiB floor -> the copy must not start
    monkeypatch.setattr(task, "_free_space", lambda p: 4096)

    with pytest.raises(Exception) as exc:
        task.move(src, dst, "rsync", min_free_bytes=8192)

    msg = str(exc.value).lower()
    assert "refusing to copy" in msg and "floor" in msg
    assert not Path(dst).exists()  # nothing was written
    assert Path(src).exists()  # and the source is untouched


def test_move_proceeds_when_the_floor_is_respected(tmp_path, monkeypatch):
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_free_space", lambda p: 1024 * 1024)
    copied = {}
    monkeypatch.setattr(
        task, "run_with_progress", lambda *a, **k: copied.setdefault("ran", True) or 0
    )

    task.move(src, dst, "rsync", min_free_bytes=8192, remove_source_file=False)

    assert copied.get("ran") is True


def test_a_same_filesystem_move_is_never_blocked(tmp_path, monkeypatch):
    """``method="auto"`` renames when both sides share a filesystem, which frees
    no space and consumes none. Applying the floor there would refuse an
    operation that cannot possibly fill anything."""
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "dst.qcow2")  # same tmp_path -> same st_dev
    monkeypatch.setattr(task, "_free_space", lambda p: 1)  # essentially full

    task.move(src, dst, "auto", min_free_bytes=1 << 40)

    assert Path(dst).exists()
    assert not Path(src).exists()  # renamed


def test_move_without_a_floor_is_unchanged(tmp_path, monkeypatch):
    """Every non-migration caller passes no floor and must keep today's
    behaviour, even on a filesystem that reports almost nothing free."""
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_free_space", lambda p: 1)
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)

    task.move(src, dst, "rsync", remove_source_file=False)  # no raise


def test_move_proceeds_when_free_space_is_unknown(tmp_path, monkeypatch):
    """``_free_space`` returns None when statvfs fails. Fail OPEN: a probe that
    cannot answer must not block an otherwise valid migration."""
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_free_space", lambda p: None)
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)

    task.move(src, dst, "rsync", min_free_bytes=1 << 40, remove_source_file=False)
