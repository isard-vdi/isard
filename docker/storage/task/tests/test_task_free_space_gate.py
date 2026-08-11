# SPDX-License-Identifier: AGPL-3.0-or-later

"""The destination free-space floor, for every action that writes a whole copy.

``move`` had a floor but it FAILED OPEN: a probe that could not answer let the
copy through, and a source whose size could not be read reserved zero. Both are
the case where the danger is highest — the filesystem is already unhappy — so
the guard was absent exactly when it mattered.

``convert`` and ``disconnect`` had no floor at all, and both write a full second
copy of the disk: ``convert`` a new destination, ``disconnect`` a ``.wo_chain``
sibling in the same directory. On a tight pool either fills the filesystem, and
a full storage node does not spoil one operation — it spoils every write on the
node and leaves rows mid-flight for someone to reconcile later.

These tests pin the decision the ticket asked for, taken once for the three:
**refuse when the space cannot be known**, and apply a floor by default rather
than only when an operator has configured one.
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


# --------------------------------------------------------------------------
# move: the two fail-open holes
# --------------------------------------------------------------------------


def test_move_refuses_when_free_space_is_unknown(tmp_path, monkeypatch):
    """``_free_space`` returns None when statvfs fails. Refuse: proceeding here
    is proceeding blind onto the very filesystem the floor exists to protect."""
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_free_space", lambda p: None)
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)

    with pytest.raises(RuntimeError) as excinfo:
        task.move(src, dst, "rsync", min_free_bytes=8192, remove_source_file=False)

    assert "cannot read the free space" in str(excinfo.value)
    assert not Path(dst).exists()
    assert Path(src).exists()


def test_move_refuses_when_the_source_cannot_be_sized(tmp_path, monkeypatch):
    """A source whose size cannot be read used to reserve ZERO, which is more
    permissive than any real disk. Refuse instead."""
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_free_space", lambda p: 1 << 40)
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)

    def _boom(path):
        raise OSError("stat failed")

    monkeypatch.setattr(task, "os_stat", _boom)

    with pytest.raises(RuntimeError) as excinfo:
        task.move(src, dst, "rsync", min_free_bytes=8192, remove_source_file=False)

    assert "cannot size" in str(excinfo.value)
    assert not Path(dst).exists()


def test_an_unknown_method_is_rejected_before_the_floor_is_probed(
    tmp_path, monkeypatch
):
    """Order matters: the floor runs early, so without an explicit method check
    ahead of it a caller error (``method="teleport"``) surfaces as "cannot read
    the free space" and points at the filesystem instead of at the call."""
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    probed = []
    monkeypatch.setattr(task, "_free_space", lambda p: probed.append(p) or None)

    with pytest.raises(ValueError) as excinfo:
        task.move(src, dst, "teleport", min_free_bytes=8192)

    assert "Invalid move method" in str(excinfo.value)
    assert probed == []  # the filesystem was never touched


def test_a_same_filesystem_move_is_still_never_blocked(tmp_path, monkeypatch):
    """A rename consumes nothing, so no probe failure may refuse it. This must
    keep holding after the gate turns fail-closed."""
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "dst.qcow2")  # same tmp_path -> same st_dev
    monkeypatch.setattr(task, "_free_space", lambda p: None)

    task.move(src, dst, "auto", min_free_bytes=1 << 40)

    assert Path(dst).exists()
    assert not Path(src).exists()


def test_move_floor_can_be_switched_off_explicitly(tmp_path, monkeypatch):
    """``min_free_bytes=0`` is an operator saying "no floor". It must still mean
    that after the default becomes non-zero, or there is no way back."""
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_free_space", lambda p: None)
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)

    task.move(src, dst, "rsync", min_free_bytes=0, remove_source_file=False)


def test_move_applies_the_default_floor_when_none_is_given(tmp_path, monkeypatch):
    """A caller that passes no floor used to get NO protection. It now gets the
    default one, which is the whole point of a default."""
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "DEFAULT_MIN_FREE_BYTES", 1 << 30)
    monkeypatch.setattr(task, "_free_space", lambda p: 4096)
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)

    with pytest.raises(RuntimeError) as excinfo:
        task.move(src, dst, "rsync", remove_source_file=False)

    assert "refusing to copy" in str(excinfo.value)


# --------------------------------------------------------------------------
# convert and disconnect: a floor where there was none
# --------------------------------------------------------------------------


def test_convert_refuses_when_the_destination_would_breach_the_floor(
    tmp_path, monkeypatch
):
    src = _sized(tmp_path, "src.qcow2", 5000)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_free_space", lambda p: 10000)
    called = {}
    monkeypatch.setattr(
        task, "run_with_progress", lambda *a, **k: called.setdefault("ran", True) or 0
    )

    with pytest.raises(RuntimeError) as excinfo:
        task.convert(src, dst, "qcow2", False, min_free_bytes=8000)

    assert "refusing to convert" in str(excinfo.value)
    assert "ran" not in called  # qemu-img was never started
    assert not Path(dst).exists()


def test_convert_refuses_when_free_space_is_unknown(tmp_path, monkeypatch):
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_free_space", lambda p: None)
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)

    with pytest.raises(RuntimeError) as excinfo:
        task.convert(src, dst, "qcow2", False, min_free_bytes=8192)

    assert "cannot read the free space" in str(excinfo.value)


def test_convert_proceeds_when_there_is_room(tmp_path, monkeypatch):
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_free_space", lambda p: 1 << 40)
    called = {}

    def _ran(*a, **k):
        called["ran"] = True
        return 0

    monkeypatch.setattr(task, "run_with_progress", _ran)

    assert task.convert(src, dst, "qcow2", False, min_free_bytes=8192) == 0
    assert called.get("ran") is True


def test_disconnect_refuses_when_the_sibling_would_breach_the_floor(
    tmp_path, monkeypatch
):
    """``disconnect`` writes a ``.wo_chain`` sibling in the SAME directory, so
    the disk it can fill is the one holding the live disk."""
    disk = _sized(tmp_path, "disk.qcow2", 5000)
    monkeypatch.setattr(task, "_free_space", lambda p: 10000)
    called = {}
    monkeypatch.setattr(task, "run", lambda *a, **k: called.setdefault("ran", True))

    with pytest.raises(RuntimeError) as excinfo:
        task.disconnect(disk, min_free_bytes=8000)

    assert "refusing to disconnect" in str(excinfo.value)
    assert "ran" not in called
    assert not Path(disk + ".wo_chain").exists()
    assert Path(disk).exists()  # the live disk is untouched


def test_disconnect_refuses_when_free_space_is_unknown(tmp_path, monkeypatch):
    disk = _sized(tmp_path, "disk.qcow2", 1024)
    monkeypatch.setattr(task, "_free_space", lambda p: None)
    monkeypatch.setattr(task, "run", lambda *a, **k: None)

    with pytest.raises(RuntimeError) as excinfo:
        task.disconnect(disk, min_free_bytes=8192)

    assert "cannot read the free space" in str(excinfo.value)


def test_disconnect_measures_after_clearing_a_stale_sibling(tmp_path, monkeypatch):
    """A crashed prior run leaves a ``.wo_chain`` holding a whole disk image on
    the very filesystem being measured. It must be unlinked BEFORE the probe, or
    the floor refuses on space that is about to be released."""
    disk = _sized(tmp_path, "disk.qcow2", 1024)
    stale = Path(disk + ".wo_chain")
    stale.write_bytes(b"\0" * 4096)
    seen = {}

    def _free(path):
        seen["stale_gone"] = not stale.exists()
        return 1 << 40

    monkeypatch.setattr(task, "_free_space", _free)
    monkeypatch.setattr(task, "run", lambda *a, **k: stale.write_bytes(b"\0" * 8))

    task.disconnect(disk, min_free_bytes=8192)

    assert seen["stale_gone"] is True
