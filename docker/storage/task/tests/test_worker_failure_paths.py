# SPDX-License-Identifier: AGPL-3.0-or-later

"""Storage-worker tasks must RAISE on failure, not return an error value.

``_publishes_result`` publishes ``job_status="finished"`` when the body returns
and ``"failed"`` only when it raises, so a task that catches its failure and
returns an error value is recorded as success and a broken disk marked ready.
These tests pin the raise-on-failure contract and the convert
partial-destination cleanup.
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
