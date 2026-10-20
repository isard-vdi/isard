# SPDX-License-Identifier: AGPL-3.0-or-later

from subprocess import CalledProcessError
from unittest.mock import MagicMock

import pytest


class _Proc:
    returncode = 0
    pid = 1234

    def __init__(self):
        self.stderr = MagicMock()
        self.stderr.read.return_value = b""
        self.stderr.readline.return_value = b""

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0


class _Watcher:
    cancelled = False

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _download(monkeypatch, dest):
    from isardvdi_storage import task

    job = MagicMock()
    job.meta = {}
    job.id = "j1"
    job.timeout = 3600
    monkeypatch.setattr(task, "get_current_job", lambda: job, raising=False)
    monkeypatch.setattr(task, "Popen", lambda *a, **k: _Proc(), raising=False)
    monkeypatch.setattr(task, "TaskCancelWatcher", _Watcher, raising=False)
    return task._run_curl_download(
        url="https://example/share/abc",
        dest_path=str(dest),
        headers=[],
        insecure_ssl=False,
        google_drive_cookie=None,
        flush_progress=lambda progress: None,
        is_aborting=lambda: False,
    )


@pytest.mark.parametrize(
    "body",
    [
        b"<!DOCTYPE html>\n<html><head><title>Download</title></head></html>",
        b"\n  <html lang='en'><body>sign in</body></html>",
    ],
    ids=["doctype", "html-tag"],
)
def test_an_html_page_is_rejected_and_removed(monkeypatch, tmp_path, body):
    dest = tmp_path / "media.iso"
    dest.write_bytes(body)

    from isardvdi_storage import task

    with pytest.raises(task.DownloadInvalidFormatError) as raised:
        _download(monkeypatch, dest)

    assert isinstance(raised.value, CalledProcessError)
    assert "HTML" in str(raised.value)
    assert not dest.exists()


def test_an_iso_image_is_kept(monkeypatch, tmp_path):
    dest = tmp_path / "media.iso"
    dest.write_bytes(b"\0" * 32769 + b"CD001" + b"\0" * 1024)

    assert _download(monkeypatch, dest) is True
    assert dest.exists()


def _download_media(monkeypatch, dest, kind):
    from isardvdi_storage import task

    job = MagicMock()
    job.meta = {}
    job.id = "j1"
    job.timeout = 3600
    monkeypatch.setattr(task, "get_current_job", lambda: job, raising=False)
    monkeypatch.setattr(task, "Popen", lambda *a, **k: _Proc(), raising=False)
    monkeypatch.setattr(task, "TaskCancelWatcher", _Watcher, raising=False)
    monkeypatch.setattr(task, "_state_progress", lambda progress: None)
    return task.download_url(
        media_id="m1", url="https://example/file", dest_path=str(dest), kind=kind
    )


ISO9660 = b"\0" * 32769 + b"CD001" + b"\0" * 1024
UDF = b"\0" * 32769 + b"BEA01" + b"\0" * 1024
FLOPPY = b"\xeb\x3c\x90" + b"\0" * 507 + b"\x55\xaa" + b"\0" * 1024
QCOW2 = b"QFI\xfb" + b"\0" * 1024
TEXT = b"0123abcd  ubuntu-24.04-desktop-amd64.iso\n" * 2000


@pytest.mark.parametrize(
    "kind,body",
    [("iso", ISO9660), ("iso", UDF), ("floppy", FLOPPY), ("qcow2", QCOW2)],
    ids=["iso9660", "udf", "floppy", "qcow2"],
)
def test_a_file_with_the_signature_of_its_kind_is_kept(
    monkeypatch, tmp_path, kind, body
):
    dest = tmp_path / f"media.{kind}"
    dest.write_bytes(body)

    result = _download_media(monkeypatch, dest, kind)

    assert result["path_downloaded"] == str(dest)
    assert dest.exists()


@pytest.mark.parametrize(
    "kind,body",
    [
        ("iso", TEXT),
        ("iso", QCOW2),
        ("iso", b"PK\x03\x04" + b"\0" * 40000),
        ("floppy", TEXT),
        ("qcow2", ISO9660),
        ("iso", b"short"),
    ],
    ids=["iso-text", "iso-qcow2", "iso-zip", "floppy-text", "qcow2-iso", "iso-short"],
)
def test_a_file_without_the_signature_of_its_kind_is_rejected_and_removed(
    monkeypatch, tmp_path, kind, body
):
    dest = tmp_path / f"media.{kind}"
    dest.write_bytes(body)

    from isardvdi_storage import task

    with pytest.raises(task.DownloadInvalidFormatError) as raised:
        _download_media(monkeypatch, dest, kind)

    assert f"not a valid {kind} image" in str(raised.value)
    assert not dest.exists()


def test_a_job_queued_without_a_kind_only_rejects_html(monkeypatch, tmp_path):
    dest = tmp_path / "media.iso"
    dest.write_bytes(TEXT)

    _download_media(monkeypatch, dest, None)

    assert dest.exists()
