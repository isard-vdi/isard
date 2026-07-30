# SPDX-License-Identifier: AGPL-3.0-or-later

"""A registry download's ``Authorization`` header must never reach the argv.

The registry download source builds an ``Authorization: <registration code>``
header. Passed as ``curl -H``, that code is readable in ``ps`` and
``/proc/<pid>/cmdline`` for the whole transfer, and every failure path raises
``CalledProcessError(cmd=curl_cmd)``, whose ``str()`` renders the full argv into
the worker log and from there into Loki. Observed live on a failed registry
media download. The header goes to curl on stdin (``-K -``) instead.
"""

import contextlib

import pytest

TOKEN = "NOT-A-REAL-REGISTRATION-CODE"
HEADER = f"Authorization: {TOKEN}"


class _FakeStderr:
    def __init__(self, payload=b""):
        self._payload = payload

    def readline(self):
        return b""

    def read(self, size=-1):
        return self._payload


class _FakeStdin:
    def __init__(self):
        self.written = ""
        self.closed = False

    def write(self, data):
        self.written += data if isinstance(data, str) else data.decode()

    def close(self):
        self.closed = True


class _FakeProcess:
    def __init__(self, returncode=0, stderr_payload=b""):
        self.returncode = returncode
        self.stderr = _FakeStderr(stderr_payload)
        self.stdin = _FakeStdin()
        self.pid = 4242

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


class _FakeJob:
    id = "job-1"
    timeout = 600
    func_name = "task.download_url"
    origin = "default"
    connection = None

    def __init__(self):
        self.meta = {}

    def save_meta(self):
        pass


class _FakeWatcher:
    cancelled = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def curl(monkeypatch):
    """Drive ``_run_curl_download`` against a fake curl, capturing its argv."""
    import task

    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["argv"] = cmd
        captured["kwargs"] = kwargs
        process = captured["process"]
        captured["stdin"] = process.stdin
        return process

    monkeypatch.setattr(task, "Popen", fake_popen)
    monkeypatch.setattr(task, "get_current_job", lambda: _FakeJob())
    monkeypatch.setattr(task, "makedirs", lambda *a, **k: None)
    monkeypatch.setattr(task, "TaskCancelWatcher", lambda *a, **k: _FakeWatcher())
    monkeypatch.setattr(task.os, "unlink", lambda p: None)

    def run(returncode=0, is_aborting=lambda: False):
        captured["process"] = _FakeProcess(returncode=returncode)
        return task._run_curl_download(
            url="https://registry.example/storage/media/x.iso",
            dest_path="/isard/media/x.iso",
            headers=[HEADER],
            insecure_ssl=False,
            google_drive_cookie=None,
            flush_progress=lambda p: None,
            is_aborting=is_aborting,
        )

    captured["run"] = run
    return captured


def test_token_is_not_in_the_argv(curl):
    curl["run"]()

    argv = curl["argv"]
    assert TOKEN not in " ".join(argv)
    assert "-H" not in argv


def test_header_still_reaches_curl_on_stdin(curl):
    curl["run"]()

    argv = curl["argv"]
    assert "-K" in argv
    assert argv[argv.index("-K") + 1] == "-"
    written = curl["stdin"].written
    assert HEADER in written
    assert curl["stdin"].closed


def test_token_is_not_in_the_failure_exception(curl):
    with pytest.raises(Exception) as excinfo:
        curl["run"](returncode=6)

    assert TOKEN not in str(excinfo.value)
    assert TOKEN not in str(getattr(excinfo.value, "cmd", ""))


def test_token_is_not_in_the_abort_exception(curl):
    with pytest.raises(Exception) as excinfo:
        curl["run"](is_aborting=lambda: True)

    assert TOKEN not in str(excinfo.value)
    assert TOKEN not in str(getattr(excinfo.value, "cmd", ""))


def test_no_config_is_written_when_there_are_no_headers(curl, monkeypatch):
    import task

    captured = curl
    captured["process"] = _FakeProcess()
    task._run_curl_download(
        url="https://example/x.iso",
        dest_path="/isard/media/x.iso",
        headers=None,
        insecure_ssl=False,
        google_drive_cookie=None,
        flush_progress=lambda p: None,
        is_aborting=lambda: False,
    )

    assert "-K" not in captured["argv"]
    assert captured["process"].stdin.written == ""
