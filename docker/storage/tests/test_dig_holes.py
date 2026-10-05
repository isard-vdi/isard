# SPDX-License-Identifier: AGPL-3.0-or-later

"""``dig-holes``: which disks may be dug, and that digging changes no byte."""

import json
import os
import shutil
import subprocess

import pytest
from storage_lib import holes

NOW = 1_800_000_000.0
OLD = NOW - 2 * holes.DEFAULT_SETTLE_SECONDS
MIB = 1 << 20


def _storage(
    sid, status="ready", parent=None, status_time=OLD, directory="/isard/templates"
):
    return {
        "id": sid,
        "type": "qcow2",
        "status": status,
        "status_time": status_time,
        "directory_path": directory,
        "parent": parent,
    }


def _domain(did, kind, status, *sids):
    return {
        "id": did,
        "kind": kind,
        "status": status,
        "create_dict": {"hardware": {"disks": [{"storage_id": s} for s in sids]}},
    }


def _by_id(cands):
    return {c.storage_id: c for c in cands}


class TestWhoIsEligible:
    def test_a_template_disk_is_eligible(self):
        c = _by_id(
            holes.classify(
                [_storage("t")], [_domain("T", "template", "Stopped", "t")], NOW
            )
        )
        assert c["t"].role == "template" and c["t"].reason is None

    def test_a_disk_with_descendants_is_left_out(self):
        """apiv4 cannot park a backing file, so nothing locks it while it is dug."""
        storages = [
            _storage("base"),
            _storage("child", parent="base", directory="/isard/groups"),
        ]
        domains = [_domain("D", "desktop", "Stopped", "child")]
        c = _by_id(
            holes.classify(storages, domains, NOW, include_stopped_desktops=True)
        )
        assert c["base"].role == "backing"
        assert c["base"].reason == "has descendants; the product cannot lock it"
        assert c["child"].reason is None

    def test_a_disk_with_children_that_a_running_desktop_uses_is_refused(self):
        """An incoherent row must not make a written disk look like a read-only parent."""
        storages = [_storage("x"), _storage("child", parent="x")]
        domains = [_domain("D", "desktop", "Started", "x")]
        assert (
            _by_id(holes.classify(storages, domains, NOW))["x"].reason
            == "a desktop using it is not stopped"
        )

    def test_desktop_disks_only_on_request_and_only_stopped(self):
        storages = [_storage("d1"), _storage("d2"), _storage("d3")]
        domains = [
            _domain("A", "desktop", "Stopped", "d1"),
            _domain("B", "desktop", "Paused", "d2"),
        ]
        default = _by_id(holes.classify(storages, domains, NOW))
        assert default["d1"].reason.startswith("desktop disk")
        asked = _by_id(
            holes.classify(storages, domains, NOW, include_stopped_desktops=True)
        )
        assert asked["d1"].reason is None
        assert asked["d2"].reason == "a desktop using it is not stopped"
        assert asked["d3"].reason.startswith("desktop disk with no domain")

    @pytest.mark.parametrize(
        "status", ["maintenance", "recycled", "deleted", "creating"]
    )
    def test_only_ready_disks(self, status):
        c = holes.classify(
            [_storage("t", status=status)],
            [_domain("T", "template", "Stopped", "t")],
            NOW,
        )
        assert c[0].reason == f"status {status}"

    def test_a_disk_that_just_changed_status_waits(self):
        c = holes.classify(
            [_storage("t", status_time=NOW - 60)],
            [_domain("T", "template", "Stopped", "t")],
            NOW,
        )
        assert "settle" in c[0].reason

    def test_files_parked_in_deleted_are_never_touched(self):
        c = holes.classify(
            [_storage("t", directory="/isard/templates/deleted")],
            [_domain("T", "template", "Stopped", "t")],
            NOW,
        )
        assert c[0].reason == "parked in deleted/"


def _fallocate_digs_holes():
    if shutil.which("fallocate") is None:
        return False
    help_text = subprocess.run(["fallocate", "--help"], capture_output=True, text=True)
    return "dig-holes" in help_text.stdout + help_text.stderr


needs_fallocate = pytest.mark.skipif(
    not _fallocate_digs_holes(), reason="needs util-linux fallocate (--dig-holes)"
)


def _inflated(path, apparent=32 * MIB, data=1 * MIB):
    with open(path, "wb") as f:
        f.write(os.urandom(data))
        f.write(b"\0" * (apparent - data))
        f.flush()
        os.fsync(f.fileno())
    return str(path)


@needs_fallocate
class TestDigChangesNoByte:
    def test_it_gives_the_zeros_back_and_reads_the_same(self, tmp_path):
        path = _inflated(tmp_path / "t.qcow2")
        before = holes.file_sha256(path)

        record = holes.dig(path)

        assert record["sha256"] == before
        assert os.stat(path).st_size == 32 * MIB
        assert record["allocated_after"] < 4 * MIB < record["allocated_before"]
        assert record["reclaimed"] > 24 * MIB


class TestTheCheckCanFail:
    def test_a_file_that_reads_differently_stops_the_run(self, tmp_path, monkeypatch):
        """The check must be able to fail: a changed hash raises instead of reporting success."""
        path = _inflated(tmp_path / "t.qcow2")
        hashes = iter(["before", "after"])
        monkeypatch.setattr(holes, "file_sha256", lambda p: next(hashes))
        monkeypatch.setattr(holes.subprocess, "run", lambda *a, **k: None)

        with pytest.raises(holes.DigHolesMismatch):
            holes.dig(path)


def _cli():
    import importlib.util
    from importlib.machinery import SourceFileLoader
    from pathlib import Path

    path = str(Path(__file__).resolve().parents[1] / "utils" / "dig-holes")
    loader = SourceFileLoader("dig_holes_cli", path)
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader("dig_holes_cli", loader)
    )
    loader.exec_module(module)
    return module


class TestTheDiskIsLockedWhileItIsDug:
    @pytest.fixture
    def cli(self, monkeypatch):
        cli = _cli()
        calls = []
        monkeypatch.setattr(
            cli.api, "lock_storage", lambda sid, a: calls.append(("lock", sid, a))
        )
        monkeypatch.setattr(
            cli.api, "release_storage", lambda sid: calls.append(("release", sid))
        )
        monkeypatch.setattr(
            cli.api, "remeasure_storage", lambda sid: calls.append(("remeasure", sid))
        )
        cli.calls = calls
        return cli

    def _candidate(self):
        return holes.Candidate(
            storage_id="t", path="/isard/templates/t.qcow2", role="template"
        )

    def test_locked_dug_released_and_measured_in_that_order(self, cli, monkeypatch):
        monkeypatch.setattr(
            cli,
            "dig",
            lambda path, verify: cli.calls.append(("dig", path)) or {"reclaimed": 1},
        )
        cli.dig_locked(self._candidate())
        assert [c[0] for c in cli.calls] == ["lock", "dig", "release", "remeasure"]
        assert cli.calls[0] == ("lock", "t", "dig_holes")

    def test_a_refused_lock_digs_nothing(self, cli, monkeypatch):
        def refuse(sid, action):
            raise cli.api.StorageLockRefused("428 storage_has_children")

        monkeypatch.setattr(cli.api, "lock_storage", refuse)
        monkeypatch.setattr(
            cli, "dig", lambda *a, **k: pytest.fail("dug an unlocked disk")
        )
        with pytest.raises(cli.api.StorageLockRefused):
            cli.dig_locked(self._candidate())
        assert cli.calls == []

    def test_a_failed_dig_still_releases(self, cli, monkeypatch):
        def boom(path, verify):
            raise OSError("fallocate failed")

        monkeypatch.setattr(cli, "dig", boom)
        with pytest.raises(OSError):
            cli.dig_locked(self._candidate())
        assert [c[0] for c in cli.calls] == ["lock", "release"]

    def test_a_disk_that_reads_differently_stays_locked(self, cli, monkeypatch):
        def mismatch(path, verify):
            raise holes.DigHolesMismatch("sha256 differs")

        monkeypatch.setattr(cli, "dig", mismatch)
        with pytest.raises(holes.DigHolesMismatch):
            cli.dig_locked(self._candidate())
        assert [c[0] for c in cli.calls] == ["lock"]

    def test_a_release_that_fails_stops_the_run(self, cli, monkeypatch):
        monkeypatch.setattr(cli, "dig", lambda path, verify: {"reclaimed": 1})

        def down(sid):
            raise RuntimeError("apiv4 down")

        monkeypatch.setattr(cli.api, "release_storage", down)
        with pytest.raises(cli.ReleaseFailed, match="still in maintenance"):
            cli.dig_locked(self._candidate())


def test_an_empty_ids_list_is_refused_not_read_as_every_disk(monkeypatch):
    """A shell variable that expands to nothing must not widen the run to the whole install."""
    cli = _cli()
    monkeypatch.setattr(
        cli.api, "fetch_storages_for_holes", lambda: pytest.fail("read the table")
    )
    with pytest.raises(SystemExit) as exc:
        cli.main(["--apply", "--ids"])
    assert exc.value.code == 2


def test_measure_counts_preallocated_zero_clusters_as_reclaimable(
    monkeypatch, tmp_path
):
    """Without extended_l2, preallocation=metadata reports allocated zero clusters as data."""
    disk = tmp_path / "d.qcow2"
    disk.write_bytes(b"\0" * (9 * MIB))
    extents = [
        {"start": 0, "length": MIB, "depth": 0, "zero": False, "data": True},
        {"start": MIB, "length": 8 * MIB, "depth": 0, "zero": True, "data": True},
        {"start": 9 * MIB, "length": 4 * MIB, "depth": 1, "zero": False, "data": True},
    ]
    monkeypatch.setattr(
        holes.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=json.dumps(extents)),
    )
    c = holes.measure(holes.Candidate(storage_id="d", path=str(disk), role="template"))
    assert c.data == MIB
