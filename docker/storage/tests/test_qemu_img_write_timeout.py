# SPDX-License-Identifier: AGPL-3.0-or-later

"""Which qemu-img calls get the 30 s NFS guard, and which get the task's budget.

The read-only ``info`` probes answer out of metadata, so 30 s of silence there
can only be a filesystem that stopped answering. A call that WRITES is different:
the same ceiling kills one that is merely waiting on a busy filesystem, and it is
720x smaller than the budget the enqueuer already computed for that task.

DB-free: only the qemu-img subprocess call is stubbed.
"""

import pytest
from isardvdi_common.helpers.task_timeouts import job_timeout_for


class _Proc:
    returncode = 0
    stdout = b'[{"virtual-size": 10}]'
    stderr = b""


@pytest.fixture
def timeouts(monkeypatch):
    """The module, plus the ``timeout=`` every qemu-img child is handed."""
    from isardvdi_storage import task

    seen = []
    monkeypatch.setattr(task, "isdir", lambda p: True)
    monkeypatch.setattr(task, "isfile", lambda p: False)
    monkeypatch.setattr(
        task, "run", lambda *a, **k: seen.append(k["timeout"]) or _Proc()
    )
    monkeypatch.setattr(
        task,
        "check_output",
        lambda *a, **k: seen.append(k["timeout"]) or b'{"virtual-size": 10}',
    )
    return task, seen


class TestWritersGetTheActionBudget:
    def test_create_gets_the_create_budget(self, timeouts, geo):
        task, seen = timeouts

        task.create("/isard/g/d.qcow2", "qcow2", **geo)

        assert seen == [job_timeout_for("create") - task.QEMU_IMG_WRITE_MARGIN]
        assert seen[0] > task.QEMU_IMG_TIMEOUT

    def test_resize_gets_the_resize_budget(self, timeouts):
        task, seen = timeouts

        task.resize("/isard/g/d.qcow2", 10)

        assert seen == [job_timeout_for("resize") - task.QEMU_IMG_WRITE_MARGIN]
        assert seen[0] > task.QEMU_IMG_TIMEOUT

    def test_the_child_expires_before_the_rq_budget_does(self):
        """A SIGALRM from rq names no command; a TimeoutExpired carries the argv."""
        from isardvdi_storage import task

        for action in ("create", "resize"):
            assert task._qemu_img_write_timeout(action) < job_timeout_for(action)

    def test_never_shorter_than_the_ceiling_it_replaces(self, monkeypatch):
        """A misconfigured budget must not make a writer stricter than it was."""
        from isardvdi_storage import task

        monkeypatch.setattr(task, "job_timeout_for", lambda action: 1)

        assert task._qemu_img_write_timeout("create") == task.QEMU_IMG_TIMEOUT


class TestReadersKeepTheNfsGuard:
    """The half that must NOT move: on an install whose NFS server backs a whole
    fleet, widening these turns a hung mount into a stuck worker."""

    def test_qemu_img_info_stays_at_thirty(self, timeouts):
        task, seen = timeouts

        task.qemu_img_info("st-1", "/isard/g/d.qcow2")

        assert seen == [task.QEMU_IMG_TIMEOUT]

    def test_backing_chain_stays_at_thirty(self, timeouts):
        task, seen = timeouts

        task.qemu_img_info_backing_chain("st-1", "/isard/g/d.qcow2")

        assert seen == [task.QEMU_IMG_TIMEOUT]
