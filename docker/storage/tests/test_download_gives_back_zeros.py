# SPDX-License-Identifier: AGPL-3.0-or-later

"""A downloaded disk does not keep the zeros HTTP carried for its holes."""

import filecmp
import os
import shutil
from unittest.mock import MagicMock

import pytest

MIB = 1 << 20


class _Proc:
    """A curl that has already written the file and exits with ``rc``."""

    pid = 1234

    def __init__(self, rc=0):
        self.returncode = rc
        self.stderr = MagicMock()
        self.stderr.read.return_value = b""
        self.stderr.readline.return_value = b""

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


class _Watcher:
    cancelled = False

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _download(monkeypatch, dest, rc=0):
    from isardvdi_storage import task

    job = MagicMock()
    job.meta = {}
    job.id = "j1"
    job.timeout = 3600
    monkeypatch.setattr(task, "get_current_job", lambda: job, raising=False)
    monkeypatch.setattr(task, "Popen", lambda *a, **k: _Proc(rc), raising=False)
    monkeypatch.setattr(task, "TaskCancelWatcher", _Watcher, raising=False)
    task._run_curl_download(
        url="https://example/x.qcow2",
        dest_path=str(dest),
        headers=[],
        insecure_ssl=False,
        google_drive_cookie=None,
        flush_progress=lambda p: None,
        is_aborting=lambda: False,
    )


def _as_curl_writes_it(path):
    """A qcow2 header, 30 MiB of zeros the server sent for a hole, data at the end."""
    with open(path, "wb") as f:
        f.write(b"QFI\xfb" + os.urandom(MIB - 4))
        f.write(b"\0" * (30 * MIB))
        f.write(os.urandom(MIB))
        os.fsync(f.fileno())


def test_the_zeros_of_a_finished_download_are_given_back(monkeypatch, tmp_path):
    dest = tmp_path / "x.qcow2"
    _as_curl_writes_it(dest)
    reference = tmp_path / "reference"
    shutil.copyfile(dest, reference)
    before = os.stat(dest).st_blocks * 512

    _download(monkeypatch, dest)

    assert filecmp.cmp(dest, reference, shallow=False)
    after = os.stat(dest).st_blocks * 512
    if after == before:
        pytest.skip("the runner's filesystem cannot punch holes")
    assert before - after >= 28 * MIB


def test_the_download_goes_on_when_the_filesystem_cannot_punch(monkeypatch, tmp_path):
    from isardvdi_storage import disk_copy

    dest = tmp_path / "x.qcow2"
    _as_curl_writes_it(dest)
    reference = tmp_path / "reference"
    shutil.copyfile(dest, reference)
    monkeypatch.setattr(disk_copy, "punch", lambda fd, off, length: False)

    _download(monkeypatch, dest)

    assert filecmp.cmp(dest, reference, shallow=False)


def test_an_unreadable_file_does_not_fail_a_good_download(monkeypatch, tmp_path):
    from isardvdi_storage import disk_copy, task

    dest = tmp_path / "x.qcow2"
    _as_curl_writes_it(dest)

    def _broken(path, cancelled=None):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(disk_copy, "punch_zeros_in_place", _broken)
    monkeypatch.setattr(task, "_looks_like_html", lambda p: False)

    _download(monkeypatch, dest)

    assert dest.exists()


def test_a_failed_download_is_not_touched(monkeypatch, tmp_path):
    from isardvdi_storage import disk_copy, task

    dest = tmp_path / "x.qcow2"
    _as_curl_writes_it(dest)
    punched = []
    monkeypatch.setattr(
        disk_copy, "punch_zeros_in_place", lambda p, cancelled=None: punched.append(p)
    )

    with pytest.raises(task.DownloadError):
        _download(monkeypatch, dest, rc=22)

    assert punched == []
