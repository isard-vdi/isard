# SPDX-License-Identifier: AGPL-3.0-or-later

"""Destructive path: ``_run_curl_download`` cancel / cleanup decisions.

This is the download body that writes a media/disk file. Two decisions carry
real risk and are pinned here with a REAL temp file so deletion is observed
directly:

* when the transfer is cancelled (watcher) or the post-download abort check
  says so, the partial file is unlinked and the job raises (rc 130);
* when curl exits non-zero, the partial file is unlinked and the job raises;
* on SUCCESS the file is KEPT — a download that must continue must never be
  deleted (the assert-what-is-NOT-touched case).

``_run_curl_download`` takes ``is_aborting`` / ``flush_progress`` as
callbacks, so no DB is involved: only the job, the curl process and the
cancel watcher are stubbed.
"""

import os

import pytest


class _FakeStderr:
    def readline(self):
        return b""

    def read(self, n=-1):
        return b""


class _FakeProc:
    def __init__(self, poll_values, returncode=0):
        self._polls = iter(poll_values)
        self.returncode = returncode
        self.pid = 2**30  # nonexistent: os.getpgid -> ProcessLookupError (caught)
        self.stderr = _FakeStderr()

    def poll(self):
        try:
            return next(self._polls)
        except StopIteration:
            return self.returncode

    def wait(self, timeout=None):
        return self.returncode


class _FakeWatcher:
    def __init__(self, cancelled):
        self.cancelled = cancelled

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeJob:
    id = "job-1"
    timeout = 300
    func_name = "task.download_url"
    origin = "default"
    connection = object()

    def __init__(self):
        self.meta = {}

    def save_meta(self):
        pass


def _wire(monkeypatch, task, *, proc, cancelled):
    monkeypatch.setattr(task, "get_current_job", lambda: _FakeJob())
    monkeypatch.setattr(task, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(
        task,
        "TaskCancelWatcher",
        lambda job_id, initial_check=None: _FakeWatcher(cancelled),
    )
    monkeypatch.setattr(task, "_publish_task_event", lambda *a, **k: None)


def _dest(tmp_path):
    d = tmp_path / "media"
    d.mkdir()
    f = d / "download.iso"
    f.write_bytes(b"partial")
    return str(f)


def _run(task, dest):
    return task._run_curl_download(
        url="http://x/file.iso",
        dest_path=dest,
        headers=[],
        insecure_ssl=False,
        google_drive_cookie=None,
        flush_progress=lambda p: None,
        is_aborting=lambda: False,
    )


class TestRunCurlDownloadDestructive:
    def test_success_keeps_the_file(self, monkeypatch, tmp_path):
        import task

        dest = _dest(tmp_path)
        _wire(monkeypatch, task, proc=_FakeProc([0], returncode=0), cancelled=False)
        assert _run(task, dest) is True
        assert os.path.exists(dest)  # a completed download is NOT deleted

    def test_cancellation_unlinks_and_raises(self, monkeypatch, tmp_path):
        import task

        dest = _dest(tmp_path)
        # poll returns None so the loop runs; the watcher reports cancelled
        _wire(monkeypatch, task, proc=_FakeProc([None]), cancelled=True)
        with pytest.raises(task.CalledProcessError) as exc:
            _run(task, dest)
        assert exc.value.returncode == 130
        assert not os.path.exists(dest)  # partial file cleaned up

    def test_post_download_abort_unlinks_and_raises(self, monkeypatch, tmp_path):
        import task

        dest = _dest(tmp_path)
        _wire(monkeypatch, task, proc=_FakeProc([0], returncode=0), cancelled=False)
        with pytest.raises(task.CalledProcessError) as exc:
            task._run_curl_download(
                url="http://x/file.iso",
                dest_path=dest,
                headers=[],
                insecure_ssl=False,
                google_drive_cookie=None,
                flush_progress=lambda p: None,
                is_aborting=lambda: True,  # abort detected after the transfer
            )
        assert exc.value.returncode == 130
        assert not os.path.exists(dest)

    def test_nonzero_curl_rc_unlinks_and_raises(self, monkeypatch, tmp_path):
        import task

        dest = _dest(tmp_path)
        _wire(monkeypatch, task, proc=_FakeProc([0], returncode=7), cancelled=False)
        with pytest.raises(task.CalledProcessError) as exc:
            _run(task, dest)
        assert exc.value.returncode == 7
        assert not os.path.exists(dest)
