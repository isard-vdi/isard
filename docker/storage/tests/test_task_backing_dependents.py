# SPDX-License-Identifier: AGPL-3.0-or-later

"""backing_dependents: the worker's read-only direct on-disk qcow2-header children query."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "utils"))

from isardvdi_storage import task  # noqa: E402


def _mk(path, backing=None, unsafe=False):
    cmd = ["qemu-img", "create", "-f", "qcow2"]
    if backing is not None:
        if unsafe:
            cmd.append("-u")  # don't open the backing: lets it be absent/stale
        cmd += ["-b", str(backing), "-F", "qcow2"]
    cmd += [str(path), "64M"]
    subprocess.run(cmd, check=True, capture_output=True)
    return str(path)


class TestBackingDependents:
    @pytest.fixture(autouse=True)
    def _force_direct_scan(self, monkeypatch):
        # No Redis: build the index straight off the candidates, hermetic.
        monkeypatch.setattr(task, "_redis_connection", lambda: None)

    def test_finds_the_direct_header_child_not_the_grandchild(
        self, tmp_path, monkeypatch
    ):
        base = _mk(tmp_path / "base.qcow2")
        child = _mk(tmp_path / "child.qcow2", backing=base)
        grand = _mk(tmp_path / "grand.qcow2", backing=child)
        monkeypatch.setattr(task, "_dependent_candidates", lambda: [base, child, grand])

        res = task.backing_dependents(base)

        assert res["dependents"] == [child]
        assert grand not in res["dependents"]
        assert res["unreadable"] == []

    def test_a_disk_with_no_header_child_reports_none(self, tmp_path, monkeypatch):
        base = _mk(tmp_path / "base.qcow2")
        other = _mk(tmp_path / "other.qcow2")
        monkeypatch.setattr(task, "_dependent_candidates", lambda: [base, other])

        res = task.backing_dependents(base)

        assert res["dependents"] == []
        assert res["unreadable"] == []

    def test_a_non_qcow2_candidate_is_reported_unreadable(self, tmp_path, monkeypatch):
        base = _mk(tmp_path / "base.qcow2")
        junk = tmp_path / "junk.qcow2"
        junk.write_bytes(b"not a qcow2 at all")
        monkeypatch.setattr(task, "_dependent_candidates", lambda: [base, str(junk)])

        res = task.backing_dependents(base)

        assert res["dependents"] == []
        assert str(junk) in res["unreadable"]

    def test_matches_a_header_child_by_uuid_when_its_backing_path_is_stale(
        self, tmp_path, monkeypatch
    ):
        # a moved child still records the OLD absolute backing path, but the uuid
        # in the base filename resolves it: the guard must still see the child.
        uuid = "a0a0a0a0-1111-2222-3333-a0a0a0a0a0a0"
        base = _mk(tmp_path / f"{uuid}.qcow2")
        stale = f"/isard/templates/old/{uuid}.qcow2"
        child = _mk(tmp_path / "child.qcow2", backing=stale, unsafe=True)
        monkeypatch.setattr(task, "_dependent_candidates", lambda: [base, child])

        res = task.backing_dependents(base)

        assert res["dependents"] == [child]
