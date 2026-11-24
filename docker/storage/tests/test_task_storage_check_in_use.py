# SPDX-License-Identifier: AGPL-3.0-or-later

"""storage_check reaches no verdict on an image a writer holds open before, during or after it."""

import fcntl
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "utils"))

from isardvdi_common.lib.storage import qemu_locks  # noqa: E402
from isardvdi_storage import task  # noqa: E402


def _hold_write(path):
    """Take the lock byte a running QEMU takes for its write permission."""
    fd = os.open(path, os.O_RDWR)
    qemu_locks._flock(
        fd,
        qemu_locks.F_OFD_SETLK,
        fcntl.F_RDLCK,
        qemu_locks.PERM_BASE + qemu_locks.WRITE,
    )
    return fd


class _Qcow:
    def __init__(self, during=None):
        self.during = during
        self.calls = 0

    def qemu_img_check_report(self, path):
        self.calls += 1
        if self.during:
            self.during()
        return {"ok": False, "inconclusive": False, "summary": "corruptions=1"}


@pytest.fixture
def image(tmp_path, monkeypatch):
    monkeypatch.setattr(task, "CHECK_WRITER_POLL_S", 0.01)
    path = tmp_path / "groups" / "d.qcow2"
    path.parent.mkdir()
    path.write_bytes(b"\0" * 512)
    return str(path)


def test_an_image_nobody_writes_gets_its_verdict(image, monkeypatch):
    qcow = _Qcow()
    monkeypatch.setattr(task, "_storage_qcow", lambda: qcow)
    out = task.storage_check(image)
    assert out["summary"] == "corruptions=1" and out["inconclusive"] is False
    assert out["started_at"] > 0


def test_an_image_open_for_writing_is_not_even_checked(image, monkeypatch):
    qcow = _Qcow()
    monkeypatch.setattr(task, "_storage_qcow", lambda: qcow)
    holder = _hold_write(image)
    try:
        out = task.storage_check(image)
    finally:
        os.close(holder)
    assert out["inconclusive"] is True and out["in_use"] is True
    assert qcow.calls == 0


def test_a_writer_that_opens_the_image_mid_check_voids_the_verdict(image, monkeypatch):
    held = []

    def start_and_stop_a_desktop():
        fd = _hold_write(image)
        time.sleep(0.1)
        os.close(fd)
        held.append(fd)

    qcow = _Qcow(during=start_and_stop_a_desktop)
    monkeypatch.setattr(task, "_storage_qcow", lambda: qcow)
    out = task.storage_check(image)
    assert held and qcow.calls == 1
    assert out["inconclusive"] is True and out["in_use"] is True


def test_a_writer_still_there_at_the_end_voids_the_verdict(image, monkeypatch):
    holders = []
    qcow = _Qcow(during=lambda: holders.append(_hold_write(image)))
    monkeypatch.setattr(task, "CHECK_WRITER_POLL_S", 3600)
    monkeypatch.setattr(task, "_storage_qcow", lambda: qcow)
    try:
        out = task.storage_check(image)
    finally:
        for fd in holders:
            os.close(fd)
    assert out["inconclusive"] is True
