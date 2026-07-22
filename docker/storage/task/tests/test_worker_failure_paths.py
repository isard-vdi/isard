# SPDX-License-Identifier: AGPL-3.0-or-later

"""Storage-worker tasks must RAISE on failure, not return an error value.

The ``_publishes_result`` decorator publishes ``job_status="finished"``
whenever the wrapped body *returns* and ``"failed"`` only when it *raises*.
Several tasks historically caught their failure and returned an error string
/ dict / rc, so a failed convert / virt_win_reg / resize / sparsify / disconnect
was published as ``finished`` — the change-handler then took the success branch
of the terminal ``update_status`` and marked a broken disk ready (the
worker-side half of bug #2306). These tests pin the raise-on-failure contract
and the convert partial-destination cleanup. (#2308)
"""

import contextlib

import pytest


def _nullcontext(*args, **kwargs):
    return contextlib.nullcontext()


# ---------------------------------------------------------------------------
# convert: raise + unlink the partial destination on abort or non-zero rc
# ---------------------------------------------------------------------------


def test_convert_raises_and_unlinks_on_nonzero_rc(monkeypatch):
    import task

    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 1)
    removed = []
    monkeypatch.setattr(task, "isfile", lambda p: True)
    monkeypatch.setattr(task, "remove", lambda p: removed.append(p))

    with pytest.raises(task.CalledProcessError):
        task.convert("/isard/src.qcow2", "/isard/dst.qcow2", "qcow2", False)
    assert removed == ["/isard/dst.qcow2"]


def test_convert_raises_and_unlinks_on_abort(monkeypatch):
    import task

    def boom(*a, **k):
        raise task.CalledProcessError(returncode=130, cmd="qemu-img convert")

    monkeypatch.setattr(task, "run_with_progress", boom)
    removed = []
    monkeypatch.setattr(task, "isfile", lambda p: True)
    monkeypatch.setattr(task, "remove", lambda p: removed.append(p))

    with pytest.raises(task.CalledProcessError):
        task.convert("/isard/src.qcow2", "/isard/dst.qcow2", "qcow2", False)
    assert removed == ["/isard/dst.qcow2"]


def test_convert_returns_zero_and_keeps_dest_on_success(monkeypatch):
    import task

    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)
    removed = []
    monkeypatch.setattr(task, "isfile", lambda p: True)
    monkeypatch.setattr(task, "remove", lambda p: removed.append(p))

    assert task.convert("/isard/src.qcow2", "/isard/dst.qcow2", "qcow2", False) == 0
    assert removed == []


# ---------------------------------------------------------------------------
# virt_win_reg / sparsify / resize / disconnect: raise on failure
# ---------------------------------------------------------------------------


def test_virt_win_reg_raises_on_failure(monkeypatch):
    import task

    monkeypatch.setattr(task, "task_heartbeat", _nullcontext)

    def boom(*a, **k):
        raise task.CalledProcessError(returncode=1, cmd="virt-win-reg", stderr="bad")

    monkeypatch.setattr(task, "run", boom)
    with pytest.raises(task.CalledProcessError):
        task.virt_win_reg("/isard/d.qcow2", "[HKEY_LOCAL_MACHINE]")


def test_sparsify_raises_on_failure(monkeypatch):
    import task

    monkeypatch.setattr(task, "task_heartbeat", _nullcontext)
    monkeypatch.setattr(task, "_get_disk_usage", lambda p: 100)

    def boom(*a, **k):
        raise task.CalledProcessError(returncode=1, cmd="virt-sparsify", stderr="bad")

    monkeypatch.setattr(task, "run", boom)
    with pytest.raises(task.CalledProcessError):
        task.sparsify("/isard/d.qcow2")


def test_resize_raises_on_failure(monkeypatch):
    import task

    def boom(*a, **k):
        raise task.CalledProcessError(returncode=1, cmd="qemu-img resize")

    monkeypatch.setattr(task, "run", boom)
    with pytest.raises(Exception):
        task.resize("/isard/d.qcow2", 10)


def test_disconnect_raises_on_failure(monkeypatch):
    import task

    def boom(*a, **k):
        raise task.CalledProcessError(returncode=1, cmd="qemu-img convert")

    monkeypatch.setattr(task, "run", boom)
    monkeypatch.setattr(task, "isfile", lambda p: True)
    monkeypatch.setattr(task, "remove", lambda p: None)
    with pytest.raises(Exception):
        task.disconnect("/isard/d.qcow2")


# ---------------------------------------------------------------------------
# delete: a missing file is idempotent success ONLY on a reachable mount.
#
# `isfile()` returns False both when the disk is genuinely already gone and
# when its storage-pool mount is down / unmounted / has a stale NFS handle.
# Blindly raising on a missing file (the old behaviour) means that, once the
# consumer honours job_status, a legitimately-gone disk fails forever and its
# recycle-bin entry sticks in `deleting`. Blindly succeeding risks dropping a
# DB row whose disk still exists on a mount that is merely down. So: missing +
# parent dir reachable -> no-op success; missing + parent dir unreachable ->
# raise (fail & retry).
# ---------------------------------------------------------------------------


def test_delete_removes_existing_file(monkeypatch):
    import task

    removed = []
    monkeypatch.setattr(task, "isfile", lambda p: True)
    monkeypatch.setattr(task, "remove", lambda p: removed.append(p))

    task.delete("/isard/groups/x.qcow2")
    assert removed == ["/isard/groups/x.qcow2"]


def test_delete_missing_file_on_live_mount_is_noop(monkeypatch):
    import task

    removed = []
    monkeypatch.setattr(task, "isfile", lambda p: False)
    monkeypatch.setattr(task, "isdir", lambda p: True)  # parent reachable
    monkeypatch.setattr(task, "remove", lambda p: removed.append(p))

    # Must NOT raise: the disk is already gone on a live mount.
    assert task.delete("/isard/groups/x.qcow2") is None
    assert removed == []


def test_delete_missing_file_on_dead_mount_raises(monkeypatch):
    import task

    monkeypatch.setattr(task, "isfile", lambda p: False)
    monkeypatch.setattr(task, "isdir", lambda p: False)  # parent unreachable
    monkeypatch.setattr(task, "remove", lambda p: None)

    with pytest.raises(Exception):
        task.delete("/isard/groups/x.qcow2")


# Safe-cancel copy+atomic-swap for the in-place ops
# ---------------------------------------------------------------------------


def test_virt_win_reg_copies_to_tmp_then_atomic_swaps(monkeypatch):
    import task

    monkeypatch.setattr(task, "task_heartbeat", _nullcontext)
    calls = []
    monkeypatch.setattr(task, "_run_cancellable", lambda cmd: calls.append(cmd) or 0)
    renamed = []
    monkeypatch.setattr(task, "rename", lambda a, b: renamed.append((a, b)))

    rc = task.virt_win_reg("/isard/d.qcow2", "[HKEY_LOCAL_MACHINE]")
    assert rc == 0
    # 1) byte copy to sibling temp (cp preserves backing header)
    assert calls[0][0] == "cp"
    assert calls[0][-2:] == ["/isard/d.qcow2", "/isard/d.qcow2.regtmp"]
    # 2) edit the TEMP, never the live disk
    assert any(c[0] == "virt-win-reg" and "/isard/d.qcow2.regtmp" in c for c in calls)
    # 3) atomic swap
    assert renamed == [("/isard/d.qcow2.regtmp", "/isard/d.qcow2")]


def test_virt_win_reg_failure_cleans_tmp_and_never_swaps(monkeypatch):
    import task

    monkeypatch.setattr(task, "task_heartbeat", _nullcontext)

    def boom(cmd):
        if cmd[0] == "virt-win-reg":
            raise task.CalledProcessError(returncode=1, cmd=cmd)
        return 0

    monkeypatch.setattr(task, "_run_cancellable", boom)
    unlinked = []
    monkeypatch.setattr(task, "_safe_unlink", lambda p: unlinked.append(p))
    renamed = []
    monkeypatch.setattr(task, "rename", lambda a, b: renamed.append((a, b)))

    with pytest.raises(task.CalledProcessError):
        task.virt_win_reg("/isard/d.qcow2", "[HKEY_LOCAL_MACHINE]")
    assert unlinked == ["/isard/d.qcow2.regtmp"]  # temp discarded
    assert renamed == []  # live disk NEVER swapped on failure


def test_sparsify_safe_cancel_copies_sparsifies_temp_and_swaps(monkeypatch):
    import task

    monkeypatch.setattr(task, "task_heartbeat", _nullcontext)
    monkeypatch.setattr(task, "_get_disk_usage", lambda p: 100)
    monkeypatch.setattr(task, "_free_space", lambda p: 100 * 1024 * 10)  # ample
    calls = []
    monkeypatch.setattr(task, "_run_cancellable", lambda cmd: calls.append(cmd) or 0)
    renamed = []
    monkeypatch.setattr(task, "rename", lambda a, b: renamed.append((a, b)))

    r = task.sparsify("/isard/d.qcow2")
    assert r["exit_code"] == 0
    assert calls[0][0] == "cp"
    assert any(
        c[0] == "virt-sparsify" and "/isard/d.qcow2.sparsetmp" in c for c in calls
    )
    assert renamed == [("/isard/d.qcow2.sparsetmp", "/isard/d.qcow2")]


def test_sparsify_falls_back_in_place_without_headroom(monkeypatch):
    import task

    monkeypatch.setattr(task, "task_heartbeat", _nullcontext)
    monkeypatch.setattr(task, "_get_disk_usage", lambda p: 100)
    monkeypatch.setattr(task, "_free_space", lambda p: 10)  # no headroom
    rc_calls = []
    monkeypatch.setattr(task, "_run_cancellable", lambda cmd: rc_calls.append(cmd) or 0)
    ran = []

    class _R:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(task, "run", lambda *a, **k: ran.append(a[0]) or _R())

    r = task.sparsify("/isard/d.qcow2")
    assert r["exit_code"] == 0
    assert rc_calls == []  # no cancellable copy attempted
    assert any(cmd[0] == "virt-sparsify" and "--in-place" in cmd for cmd in ran)
