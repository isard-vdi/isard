# SPDX-License-Identifier: AGPL-3.0-or-later

"""Cancel / failure decisions in ``run_with_progress`` and ``_run_cancellable``.

Both run a subprocess under a cancel watcher. What matters is the terminal
decision:

* cancelled mid-run -> raise CalledProcessError(130) (so RQ marks the job
  non-finished and the chain takes its cleanup branch);
* run_with_progress: a non-zero rc is RETURNED (the caller decides), only
  cancellation raises; success returns 0 and drives the final progress tick;
* _run_cancellable: a non-zero rc RAISES; with no RQ job it runs
  synchronously.

DB-free: the job, the curl/qemu process and the cancel watcher are stubbed;
``extract_progress`` is a callback.
"""

import pytest


class _Stdout:
    def read(self, *a):
        return b""

    def read1(self, *a):
        return b""

    def close(self):
        pass


class _Proc:
    def __init__(self, poll_values, returncode=0):
        self._polls = iter(poll_values)
        self.returncode = returncode
        self.pid = 2**30
        self.stdout = _Stdout()

    def poll(self):
        try:
            return next(self._polls)
        except StopIteration:
            return self.returncode

    def wait(self, timeout=None):
        return self.returncode


class _Watcher:
    def __init__(self, cancelled):
        self.cancelled = cancelled

    def wait(self, timeout=None):
        return self.cancelled

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Job:
    id = "job-1"
    func_name = "task.move"
    origin = "default"
    connection = object()

    def __init__(self):
        self.meta = {}

    def save_meta(self):
        pass


def _wire(monkeypatch, task, *, proc, cancelled, job=True):
    monkeypatch.setattr(task, "get_current_job", lambda: _Job() if job else None)
    monkeypatch.setattr(task, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(
        task,
        "TaskCancelWatcher",
        lambda job_id, initial_check=None: _Watcher(cancelled),
    )
    monkeypatch.setattr(task, "_publish_task_event", lambda *a, **k: None)


class TestRunWithProgress:
    def test_cancelled_raises_130(self, monkeypatch):
        import task

        _wire(monkeypatch, task, proc=_Proc([None]), cancelled=True)
        with pytest.raises(task.CalledProcessError) as exc:
            task.run_with_progress(["rsync"], lambda p: 0.0)
        assert exc.value.returncode == 130

    def test_success_returns_zero_and_final_progress(self, monkeypatch):
        import task

        _wire(monkeypatch, task, proc=_Proc([0], returncode=0), cancelled=False)
        ticks = []
        assert (
            task.run_with_progress(["rsync"], lambda p: 0.0, on_progress=ticks.append)
            == 0
        )
        assert ticks == [1.0]  # final tick fired on success

    def test_nonzero_rc_is_returned_not_raised(self, monkeypatch):
        import task

        _wire(monkeypatch, task, proc=_Proc([0], returncode=23), cancelled=False)
        # a genuine command failure is returned; the caller (move/convert) decides
        assert task.run_with_progress(["rsync"], lambda p: 0.0) == 23


class TestRunCancellable:
    def test_no_job_runs_synchronously(self, monkeypatch):
        import task

        ran = []
        monkeypatch.setattr(task, "get_current_job", lambda: None)
        monkeypatch.setattr(task, "run", lambda *a, **k: ran.append(a[0]))
        assert task._run_cancellable(["cp", "a", "b"]) == 0
        assert ran == [["cp", "a", "b"]]

    def test_cancelled_raises_130(self, monkeypatch):
        import task

        _wire(monkeypatch, task, proc=_Proc([None]), cancelled=True)
        with pytest.raises(task.CalledProcessError) as exc:
            task._run_cancellable(["cp", "a", "b"])
        assert exc.value.returncode == 130

    def test_nonzero_rc_raises(self, monkeypatch):
        import task

        _wire(monkeypatch, task, proc=_Proc([0], returncode=4), cancelled=False)
        with pytest.raises(task.CalledProcessError) as exc:
            task._run_cancellable(["cp", "a", "b"])
        assert exc.value.returncode == 4

    def test_success_returns_zero(self, monkeypatch):
        import task

        _wire(monkeypatch, task, proc=_Proc([0], returncode=0), cancelled=False)
        assert task._run_cancellable(["cp", "a", "b"]) == 0
