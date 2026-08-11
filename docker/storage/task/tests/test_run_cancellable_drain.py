# SPDX-License-Identifier: AGPL-3.0-or-later

"""``_run_cancellable`` output handling and cancel latency.

Two guarantees are pinned here, and they pull in opposite directions:

* A chatty child must never wedge the worker. Handing the child a pipe and
  only reading it after ``wait()`` deadlocks as soon as the child writes more
  than the OS pipe buffer (~64 KiB): the child blocks in ``write()``, so it
  never exits, so the parent loops forever. ``qemu-img``/``rsync``/
  ``virt-sparsify`` are all capable of that on an error path.
* Fixing the above must NOT make cancellation lazy. Buffering the child's
  output with ``communicate()``/``run(capture_output=True)`` would drain the
  pipes safely but only return when the child is done, so a cancel request
  would sit unhandled for the whole operation. Cancel must still SIGTERM the
  process group within a couple of seconds.

Every call here runs in a bounded worker thread so a regression fails the
suite instead of hanging it.
"""

import sys
import tempfile
import threading
import time

CHATTY_OK = (
    "import sys;"
    "sys.stderr.write('E' * (1 << 20));"
    "sys.stderr.flush();"
    "sys.stdout.write('O' * (1 << 20));"
    "sys.stdout.flush()"
)

CHATTY_FAIL = (
    "import sys;"
    "sys.stderr.write('noise\\n' * 60000);"
    "sys.stderr.write('FATAL: could not open backing file\\n');"
    "sys.stderr.flush();"
    "sys.exit(3)"
)

SLEEPER = "import time; time.sleep(60)"

CALL_TIMEOUT = 15
PROMPT_CANCEL_SECONDS = 5


class _FakeJob:
    """Minimal RQ job stand-in: ``_run_cancellable`` only reads ``id``."""

    id = "test-run-cancellable"


class _FakeWatcher:
    """TaskCancelWatcher stand-in driven by a plain ``threading.Event``."""

    def __init__(self, event):
        self._event = event

    def __call__(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def cancelled(self):
        return self._event.is_set()

    def wait(self, timeout=None):
        return self._event.wait(timeout)


def _wire(monkeypatch, tmp_path, cancel_event):
    """Put ``task._run_cancellable`` on its real subprocess path.

    Returns the list of spawned ``Popen`` objects so a hung call can be
    unblocked instead of leaking a child into the rest of the suite.
    """
    import task

    monkeypatch.setattr(task, "get_current_job", lambda: _FakeJob())
    monkeypatch.setattr(task, "TaskCancelWatcher", _FakeWatcher(cancel_event))
    # Any temp file the runner creates must land here, so the test can assert
    # it was cleaned up.
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    spawned = []
    real_popen = task.Popen

    def _record(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        spawned.append(process)
        return process

    monkeypatch.setattr(task, "Popen", _record)
    return spawned


def _call_bounded(command, spawned, timeout=CALL_TIMEOUT):
    """Run ``_run_cancellable(command)`` with a hard wall-clock bound.

    Returns ``(returned, raised, elapsed, hung)``.
    """
    import task

    box = {}

    def _body():
        try:
            box["returned"] = task._run_cancellable(command)
        except BaseException as exc:  # noqa: BLE001 - reported to the test
            box["raised"] = exc

    thread = threading.Thread(target=_body, daemon=True)
    started = time.monotonic()
    thread.start()
    thread.join(timeout)
    elapsed = time.monotonic() - started
    hung = thread.is_alive()
    if hung:
        # Unwedge the blocked child so the thread can finish and the suite
        # does not leak a process.
        for process in spawned:
            try:
                process.kill()
            except OSError:
                pass
        thread.join(10)
    return box.get("returned"), box.get("raised"), elapsed, hung


def test_chatty_child_that_exits_zero_does_not_deadlock(monkeypatch, tmp_path):
    spawned = _wire(monkeypatch, tmp_path, threading.Event())

    returned, raised, elapsed, hung = _call_bounded(
        [sys.executable, "-c", CHATTY_OK], spawned
    )

    assert not hung, (
        f"_run_cancellable did not return within {CALL_TIMEOUT}s for a child "
        "that wrote 1 MiB and exited: the child is blocked writing to a full "
        "pipe nobody is reading"
    )
    assert raised is None, f"unexpected exception: {raised!r}"
    assert returned == 0
    assert list(tmp_path.iterdir()) == [], "temp capture file left behind"


def test_chatty_child_failure_still_surfaces_its_error_message(monkeypatch, tmp_path):
    import task

    spawned = _wire(monkeypatch, tmp_path, threading.Event())

    returned, raised, elapsed, hung = _call_bounded(
        [sys.executable, "-c", CHATTY_FAIL], spawned
    )

    assert not hung, (
        f"_run_cancellable did not return within {CALL_TIMEOUT}s for a chatty "
        "child that failed"
    )
    assert isinstance(raised, task.CalledProcessError), f"raised={raised!r}"
    assert raised.returncode == 3
    message = raised.stderr or raised.output or ""
    assert "FATAL: could not open backing file" in message, (
        "the callers log this message; the tail of the child's stderr must "
        "reach CalledProcessError"
    )
    assert len(message) <= 64 * 1024, "captured output must stay bounded"
    assert list(tmp_path.iterdir()) == [], "temp capture file left behind"


def test_cancel_kills_the_process_group_promptly(monkeypatch, tmp_path):
    import task

    cancel = threading.Event()
    spawned = _wire(monkeypatch, tmp_path, cancel)
    threading.Timer(0.2, cancel.set).start()

    returned, raised, elapsed, hung = _call_bounded(
        [sys.executable, "-c", SLEEPER], spawned
    )

    assert not hung, (
        f"cancel was not honoured within {CALL_TIMEOUT}s: the runner is "
        "waiting for the child instead of watching for the cancel signal"
    )
    assert isinstance(raised, task.CalledProcessError), f"raised={raised!r}"
    assert raised.returncode == 130
    assert elapsed < PROMPT_CANCEL_SECONDS, (
        f"cancel latency regressed: {elapsed:.1f}s for a child that would "
        "have run for 60s"
    )
    assert spawned and spawned[0].poll() is not None, "child left running"
    assert list(tmp_path.iterdir()) == [], "temp capture file left behind"
