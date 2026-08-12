# SPDX-License-Identifier: AGPL-3.0-or-later

"""The last progress write of a finished download.

The reader loop only runs while curl is alive and throttles its writes, so the
final line curl printed was never persisted: a completed download kept showing
whatever fraction the previous tick caught. Observed live on three downloads —
89%, 94% and 99% — each on a file that was byte-for-byte complete.
"""

from unittest.mock import MagicMock


class _Proc:
    """A curl that exits immediately and cleanly."""

    returncode = 0
    pid = 1234

    def __init__(self):
        self._polls = [0]
        self.stderr = MagicMock()
        self.stderr.read.return_value = b""
        self.stderr.readline.return_value = b""

    def poll(self):
        return self._polls.pop(0) if self._polls else 0

    def wait(self, timeout=None):
        return 0


def test_the_final_progress_is_flushed_at_100(monkeypatch):
    import task

    flushed = []
    job = MagicMock()
    job.meta = {}
    job.id = "j1"
    job.timeout = 3600

    class _Watcher:
        """No redis in a unit test; nothing cancels this download."""

        cancelled = False

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(task, "get_current_job", lambda: job, raising=False)
    monkeypatch.setattr(task, "Popen", lambda *a, **k: _Proc(), raising=False)
    monkeypatch.setattr(task, "TaskCancelWatcher", _Watcher, raising=False)

    task._run_curl_download(
        url="https://example/x.iso",
        dest_path="/tmp/x.iso",
        headers=[],
        insecure_ssl=False,
        google_drive_cookie=None,
        flush_progress=flushed.append,
        is_aborting=lambda: False,
    )

    assert flushed, "no final progress was persisted"
    assert flushed[-1]["received_percent"] == 100
    assert flushed[-1]["total_percent"] == 100
    assert job.meta["progress"] == 1.0


def test_the_final_progress_carries_the_on_disk_byte_size(monkeypatch, tmp_path):
    """``progress.total_bytes`` is the stat of the file the worker just wrote.

    That is the figure every media-space reader (quota, usage, analytics,
    cleanup) sums. curl only prints a human-rounded ``total`` ("3408k") and no
    reader consumes it, so the byte count has to come from the file itself.
    """
    import task

    dest = tmp_path / "x.iso"
    dest.write_bytes(b"\0" * 3490290)

    flushed = []
    job = MagicMock()
    job.meta = {}
    job.id = "j1"
    job.timeout = 3600

    class _Watcher:
        cancelled = False

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(task, "get_current_job", lambda: job, raising=False)
    monkeypatch.setattr(task, "Popen", lambda *a, **k: _Proc(), raising=False)
    monkeypatch.setattr(task, "TaskCancelWatcher", _Watcher, raising=False)

    task._run_curl_download(
        url="https://example/x.iso",
        dest_path=str(dest),
        headers=[],
        insecure_ssl=False,
        google_drive_cookie=None,
        flush_progress=flushed.append,
        is_aborting=lambda: False,
    )

    assert flushed[-1]["total_bytes"] == 3490290
