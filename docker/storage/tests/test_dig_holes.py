# SPDX-License-Identifier: AGPL-3.0-or-later

"""``dig-holes``: which disks may be dug, and that digging changes no byte."""

import json
import subprocess

import pytest
from storage_lib import holes

NOW = 1_800_000_000.0
OLD = NOW - 2 * holes.DEFAULT_SETTLE_SECONDS
MIB = 1 << 20


def _storage(
    sid,
    status="ready",
    parent=None,
    status_time=OLD,
    directory="/isard/groups",
    perms=("r", "w"),
):
    return {
        "id": sid,
        "type": "qcow2",
        "status": status,
        "status_time": status_time,
        "directory_path": directory,
        "parent": parent,
        "perms": list(perms),
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
    """The same disks the product's dig_holes admits, so --apply is not refused."""

    def test_a_stopped_desktops_leaf_disk_is_eligible(self):
        c = holes.classify(
            [_storage("d")], [_domain("D", "desktop", "Stopped", "d")], NOW
        )
        assert c[0].role == "desktop" and c[0].reason is None

    def test_a_failed_desktop_counts_as_stopped(self):
        c = holes.classify(
            [_storage("d")], [_domain("D", "desktop", "Failed", "d")], NOW
        )
        assert c[0].reason is None

    def test_a_template_disk_is_left_out(self):
        c = holes.classify(
            [_storage("t", perms=("r",))],
            [_domain("T", "template", "Stopped", "t")],
            NOW,
        )
        assert c[0].reason == "read-only disk"
        c = holes.classify(
            [_storage("t")], [_domain("T", "template", "Stopped", "t")], NOW
        )
        assert c[0].reason == "a template uses it"

    def test_a_disk_no_domain_uses_is_left_out(self):
        assert holes.classify([_storage("x")], [], NOW)[0].reason == "no domain uses it"

    def test_a_base_with_descendants_is_left_out(self):
        storages = [_storage("base"), _storage("child", parent="base")]
        domains = [
            _domain("D", "desktop", "Stopped", "base"),
            _domain("E", "desktop", "Stopped", "child"),
        ]
        c = _by_id(holes.classify(storages, domains, NOW))
        assert c["base"].role == "backing"
        assert c["base"].reason == "has descendants"
        assert c["child"].reason is None

    def test_a_deleted_child_still_keeps_its_base_out(self):
        """A deleted row's file may still be on disk, backed on the base."""
        storages = [
            _storage("base"),
            _storage("gone", status="deleted", parent="base"),
        ]
        domains = [_domain("D", "desktop", "Stopped", "base")]
        assert (
            _by_id(holes.classify(storages, domains, NOW))["base"].reason
            == "has descendants"
        )

    def test_a_disk_with_children_that_a_running_desktop_uses_is_refused(self):
        """An incoherent row must not make a written disk look like a read-only parent."""
        storages = [_storage("x"), _storage("child", parent="x")]
        domains = [_domain("D", "desktop", "Started", "x")]
        assert (
            _by_id(holes.classify(storages, domains, NOW))["x"].reason
            == "a desktop using it is not stopped"
        )

    @pytest.mark.parametrize("status", ["Started", "Paused", "Shutting-down"])
    def test_a_desktop_not_stopped_is_left_out(self, status):
        c = holes.classify([_storage("d")], [_domain("D", "desktop", status, "d")], NOW)
        assert c[0].reason == "a desktop using it is not stopped"

    @pytest.mark.parametrize(
        "status", ["maintenance", "recycled", "deleted", "creating"]
    )
    def test_only_ready_disks(self, status):
        c = holes.classify(
            [_storage("d", status=status)],
            [_domain("D", "desktop", "Stopped", "d")],
            NOW,
        )
        assert c[0].reason == f"status {status}"

    def test_a_disk_that_just_changed_status_waits(self):
        c = holes.classify(
            [_storage("d", status_time=NOW - 60)],
            [_domain("D", "desktop", "Stopped", "d")],
            NOW,
        )
        assert "settle" in c[0].reason

    def test_files_parked_in_deleted_are_never_touched(self):
        c = holes.classify(
            [_storage("d", directory="/isard/groups/deleted")],
            [_domain("D", "desktop", "Stopped", "d")],
            NOW,
        )
        assert c[0].reason == "parked in deleted/"


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


class TestTheProductDigsIt:
    @pytest.fixture
    def cli(self, monkeypatch, tmp_path):
        cli = _cli()
        disk = tmp_path / "t.qcow2"
        disk.write_bytes(b"x")
        cli.disk = str(disk)
        cli.calls = []
        cli.task_status = iter(["queued", "started", "finished", "finished"])
        cli.rows = iter([{"status": "maintenance"}, {"status": "ready"}])

        def queue(sid):
            cli.calls.append(("queue", sid))
            return "task-1"

        monkeypatch.setattr(cli.api, "dig_holes_storage", queue)
        monkeypatch.setattr(
            cli.api, "poll_task", lambda tid: {"status": next(cli.task_status)}
        )
        monkeypatch.setattr(cli.api, "storage_row", lambda sid: next(cli.rows))
        return cli

    def _candidate(self, cli):
        return holes.Candidate(storage_id="t", path=cli.disk, role="desktop")

    def test_it_queues_the_product_dig_and_waits_for_the_release(self, cli):
        record = cli.dig_through_product(self._candidate(cli), sleep=lambda s: None)
        assert cli.calls == [("queue", "t")]
        assert record["task_id"] == "task-1"
        assert list(cli.rows) == []

    def test_a_disk_left_damaged_is_reported_as_such(self, cli):
        cli.task_status = iter(["failed", "failed"])
        cli.rows = iter([{"status": "damaged"}])
        with pytest.raises(cli.DigFailed, match="disk left damaged"):
            cli.dig_through_product(self._candidate(cli), sleep=lambda s: None)

    def test_the_tool_never_digs_a_file_itself(self):
        cli = _cli()
        assert not hasattr(cli, "dig") and not hasattr(holes, "dig")


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
