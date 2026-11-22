# SPDX-License-Identifier: AGPL-3.0-or-later

"""storage_check of a disk whose file is gone: a finding on a live volume, no verdict on a dead one."""

import errno
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "utils"))

from isardvdi_storage import task  # noqa: E402


def test_a_missing_file_in_a_live_directory_is_reported_missing(tmp_path):
    groups = tmp_path / "storage_pools" / "fast" / "groups"
    groups.mkdir(parents=True)
    path = str(groups / "gone.qcow2")
    out = task.storage_check(path)
    assert out["missing"] is True
    assert out["ok"] is False and out["inconclusive"] is False
    assert out["path"] == path


def test_a_missing_file_on_an_unmounted_pool_reaches_no_verdict(tmp_path):
    pool = tmp_path / "storage_pools" / "fast"
    pool.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="does not exist"):
        task.storage_check(str(pool / "groups" / "gone.qcow2"))


def test_a_stale_read_of_the_file_reaches_no_verdict(tmp_path, monkeypatch):
    groups = tmp_path / "storage_pools" / "fast" / "groups"
    groups.mkdir(parents=True)

    def stale(path):
        raise OSError(errno.ESTALE, "Stale file handle", path)

    monkeypatch.setattr(task, "os_stat", stale)
    with pytest.raises(OSError):
        task.storage_check(str(groups / "there.qcow2"))
