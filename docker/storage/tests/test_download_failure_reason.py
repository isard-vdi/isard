# SPDX-License-Identifier: AGPL-3.0-or-later

"""A failed download raises with a reason an operator can read."""

from unittest.mock import MagicMock

import pytest


class _Watcher:
    cancelled = False

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Stderr:
    def __init__(self, data):
        self._data = data

    def readline(self):
        return b""

    def read(self, size=-1):
        if size < 0:
            chunk, self._data = self._data, b""
        else:
            chunk, self._data = self._data[:size], self._data[size:]
        return chunk


class _FailingCurl:
    pid = 1234

    def __init__(self, stderr, returncode):
        self.stderr = _Stderr(stderr)
        self._returncode = returncode
        self.returncode = None

    def poll(self):
        if self.stderr._data:
            return None
        self.returncode = self._returncode
        return self.returncode

    def wait(self, timeout=None):
        return self._returncode


def _wire(monkeypatch, task):
    job = MagicMock()
    job.meta = {}
    job.id = "j1"
    job.timeout = 3600
    monkeypatch.setattr(task, "get_current_job", lambda: job, raising=False)
    monkeypatch.setattr(task, "TaskCancelWatcher", _Watcher, raising=False)


def _download(task, url, dest):
    task._run_curl_download(
        url=url,
        dest_path=str(dest),
        headers=[],
        insecure_ssl=False,
        google_drive_cookie=None,
        flush_progress=lambda progress: None,
        is_aborting=lambda: False,
    )


def test_a_download_without_url_fails_with_a_reason_not_a_type_error(
    monkeypatch, tmp_path
):
    from isardvdi_storage import task

    _wire(monkeypatch, task)

    with pytest.raises(task.DownloadError) as exc:
        _download(task, None, tmp_path / "x.iso")

    assert str(exc.value) == "the download has no source URL"


def test_the_curl_error_line_read_by_the_progress_loop_reaches_the_reason(
    monkeypatch, tmp_path
):
    from isardvdi_storage import task

    _wire(monkeypatch, task)
    stderr = (
        b"\r  0     0    0     0    0     0      0      0 --:--:--  0:00:30 --:--:--"
        b"     0\ncurl: (28) Connection timed out after 30001 milliseconds\n"
    )
    monkeypatch.setattr(
        task, "Popen", lambda *a, **k: _FailingCurl(stderr, 28), raising=False
    )

    with pytest.raises(task.DownloadError) as exc:
        _download(task, "https://example.org/x.iso", tmp_path / "x.iso")

    assert exc.value.returncode == 28
    assert str(exc.value) == (
        "the download timed out (curl exit 28): "
        "curl: (28) Connection timed out after 30001 milliseconds"
    )


def test_an_unknown_curl_exit_code_still_names_the_code(monkeypatch, tmp_path):
    from isardvdi_storage import task

    _wire(monkeypatch, task)
    monkeypatch.setattr(
        task, "Popen", lambda *a, **k: _FailingCurl(b"", 99), raising=False
    )

    with pytest.raises(task.DownloadError) as exc:
        _download(task, "https://example.org/x.iso", tmp_path / "x.iso")

    assert str(exc.value) == "the download failed (curl exit 99)"
