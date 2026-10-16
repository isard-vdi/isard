# SPDX-License-Identifier: AGPL-3.0-or-later

"""A missing disk is gone when its VOLUME is live, not only when its directory is.

The directory a disk lives in can disappear on its own: a user or group
directory removed after its disks, or the layout of an older version
(``<pool>/<category>/groups/<category>/<group>/<provider>/<user>/``). Treating
that missing directory as an unreachable mount fails the delete forever and
leaves its recycle-bin entry in ``deleting``. What tells a live volume from an
unmounted one is the pool root: an unmounted mountpoint is an empty directory,
a live pool always holds its usage directories.
"""

import errno

import pytest
from isardvdi_storage import task


def _live_pool(tmp_path, name="fast"):
    root = tmp_path / "storage_pools" / name
    (root / "cat" / "groups").mkdir(parents=True)
    return root


def _legacy_disk(root):
    # The directories under the pool root do not exist any more.
    return str(
        root / "cat" / "groups" / "cat" / "Main" / "local" / "gestor" / "w.qcow2"
    )


def test_missing_legacy_directory_on_a_live_pool_is_gone(tmp_path):
    root = _live_pool(tmp_path)
    assert task.delete(_legacy_disk(root), pool_root=str(root)) is None


def test_the_pool_root_is_derived_when_the_caller_sends_none(tmp_path):
    """Jobs queued before the caller sent ``pool_root`` still finish."""
    root = _live_pool(tmp_path)
    assert task.delete(_legacy_disk(root)) is None


def test_an_unmounted_pool_still_raises(tmp_path):
    root = tmp_path / "storage_pools" / "fast"
    root.mkdir(parents=True)  # the mountpoint, with nothing mounted on it
    with pytest.raises(FileNotFoundError):
        task.delete(_legacy_disk(root), pool_root=str(root))


def test_a_missing_pool_root_still_raises(tmp_path):
    root = tmp_path / "storage_pools" / "fast"
    with pytest.raises(FileNotFoundError):
        task.delete(_legacy_disk(root), pool_root=str(root))


def test_a_live_default_mountpoint_does_not_hide_an_unmounted_pool(tmp_path):
    """A pool whose row is gone resolves to the default mountpoint, which is
    live; the pool's own directory under ``storage_pools`` must decide."""
    (tmp_path / "groups").mkdir()
    root = tmp_path / "storage_pools" / "gone"
    root.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        task.delete(_legacy_disk(root), pool_root=str(tmp_path))


def test_a_pool_root_that_does_not_hold_the_path_is_ignored(tmp_path):
    other = tmp_path / "elsewhere"
    (other / "x").mkdir(parents=True)
    path = str(tmp_path / "groups" / "u" / "d.qcow2")
    with pytest.raises(FileNotFoundError):
        task.delete(path, pool_root=str(other))


def test_without_any_known_root_the_old_rule_holds(tmp_path):
    (tmp_path / "x").mkdir()
    with pytest.raises(FileNotFoundError):
        task.delete(str(tmp_path / "groups" / "u" / "d.qcow2"))
    assert task.delete(str(tmp_path / "x" / "d.qcow2")) is None


def test_a_stale_pool_root_raises_instead_of_answering(tmp_path, monkeypatch):
    root = _live_pool(tmp_path)

    def stale(path):
        raise OSError(errno.ESTALE, "Stale file handle", path)

    monkeypatch.setattr(task.os, "statvfs", stale)
    with pytest.raises(OSError) as exc:
        task.delete(_legacy_disk(root), pool_root=str(root))
    assert exc.value.errno == errno.ESTALE


def test_an_existing_disk_is_removed(tmp_path):
    root = _live_pool(tmp_path)
    disk = root / "cat" / "groups" / "d.qcow2"
    disk.write_bytes(b"x")
    task.delete(str(disk), pool_root=str(root))
    assert not disk.exists()


def test_move_delete_follows_the_same_rule(tmp_path):
    root = _live_pool(tmp_path)
    assert task.move_delete(_legacy_disk(root), pool_root=str(root)) == 0

    empty = tmp_path / "storage_pools" / "empty"
    empty.mkdir()
    with pytest.raises(ValueError):
        task.move_delete(_legacy_disk(empty), pool_root=str(empty))
