"""Unit tests for ``backup_report._build_request_body``.

Runs only where the generated apiv4 client is installed (the backupninja build
image / CI codegen env); skipped otherwise. Guards the regression where the
parser's undeclared fields (``disk_types``, ``actions``, the ``*_actions``
counts, ``duration``, ``backup_types_status``, ...) crashed
``_build_request_body`` via ``setattr`` on the generated attrs ``__slots__``
model — aborting the build before any POST and silently queuing every report.
"""

import json
import os

import pytest

pytest.importorskip("isardvdi_apiv4_client")
pytest.importorskip("isardvdi_apiv4_client_auth")

from isardvdi_apiv4_client_auth import ApiV4Error  # noqa: E402
from isardvdi_backupninja import backup_report  # noqa: E402
from isardvdi_backupninja.backup_report import (  # noqa: E402
    BackupAction,
    BackupLogParser,
    derive_scope_from_actions,
)


def _realistic_payload():
    """Mirror BackupLogParser.to_dict(): required + rich undeclared fields."""
    return {
        "timestamp": 1784050000,
        "status": "SUCCESS",
        "type": "automated",
        "scope": "full",
        "disk_types": ["qcow2", "raw"],
        "backup_types_status": {"db": "success", "disks": "success"},
        "total_actions": 21,
        "successful_actions": 20,
        "failed_actions": 0,
        "warning_actions": 2,
        "fatal_actions": 0,
        "actions": [{"name": "22-db-dump.sh", "status": "SUCCESS"}],
        "summary": "ok",
        "duration": 3600,
    }


def test_build_request_body_routes_undeclared_fields():
    # Must not raise (the pre-fix setattr raised AttributeError on disk_types).
    body = backup_report._build_request_body(_realistic_payload())
    d = body.to_dict()

    # Required fields (constructor) — note the generated model emits ``type``.
    assert d["timestamp"] == 1784050000
    assert d["status"] == "SUCCESS"
    assert d["type"] == "automated"
    assert d["scope"] == "full"

    # Undeclared parser fields must survive at top level (additional_properties).
    assert d["disk_types"] == ["qcow2", "raw"]
    assert d["total_actions"] == 21
    assert d["duration"] == 3600
    assert d["backup_types_status"] == {"db": "success", "disks": "success"}
    assert d["actions"] == [{"name": "22-db-dump.sh", "status": "SUCCESS"}]


def test_build_request_body_is_non_destructive():
    """flush_queue re-marshals the same queued dict on retry — building the body
    must not mutate the payload, so a retry reproduces an identical body."""
    payload = _realistic_payload()
    snapshot = dict(payload)
    backup_report._build_request_body(payload)
    assert payload == snapshot
    again = backup_report._build_request_body(payload).to_dict()
    assert again["total_actions"] == 21


# pools kind: prefix classification, scope derivation, config


def test_classify_splits_pools_out_of_disks():
    assert BackupAction(name="/x/82-disks-borg.borg").classify() == "disks"
    assert BackupAction(name="/x/85-disks-borg-integrity.sh").classify() == "disks"
    assert BackupAction(name="/x/86-pools-info.sh").classify() == "pools"
    assert BackupAction(name="/x/87-pools-borg.sh").classify() == "pools"
    assert BackupAction(name="/x/89-pools-borg-integrity.sh").classify() == "pools"


def test_derive_scope_pools_only_session():
    actions = [
        BackupAction(name="/x/86-pools-info.sh"),
        BackupAction(name="/x/87-pools-borg.sh"),
    ]
    assert derive_scope_from_actions(actions) == "pools"


def test_collect_backup_config_includes_pools(monkeypatch):
    monkeypatch.setenv("BACKUP_POOLS_ENABLED", "true")
    monkeypatch.setenv("BACKUP_POOLS_WHEN", "everyday at 03:00")
    monkeypatch.setenv("BACKUP_POOLS_EXCLUDE", "*/volatile*")
    cfg = backup_report.collect_backup_config()
    assert cfg["enabled"]["pools"] is True
    assert cfg["schedule"]["pools"]["hour"] == 3
    assert cfg["pools"] == {
        "enabled": True,
        "when": "everyday at 03:00",
        "exclude": "*/volatile*",
    }


def _write_pools_session_log(tmp_path, body_lines):
    log = tmp_path / "backupninja.log"
    lines = [
        "2026-01-15T01:00:00 Info: BACKUP_SESSION_START: automated pools backup "
        "initiated by cron (schedule: everyday at 01:00)",
        *body_lines,
        "2026-01-15T01:05:00 Info: BACKUP_SESSION_END: automated pools backup completed",
    ]
    log.write_text("\n".join(lines) + "\n")
    return str(log)


def test_report_carries_pools_scope_and_pool_dirs(tmp_path):
    log = _write_pools_session_log(
        tmp_path,
        [
            "2026-01-15T01:00:01 Info: >>>> starting action /x/86-pools-info.sh",
            "2026-01-15T01:00:02 Info: BACKUP_POOL_DIRS: 3",
            "2026-01-15T01:00:03 Info: <<<< finished action /x/86-pools-info.sh: SUCCESS",
            "2026-01-15T01:00:04 Info: >>>> starting action /x/87-pools-borg.sh",
            "2026-01-15T01:04:00 Info: <<<< finished action /x/87-pools-borg.sh: SUCCESS",
        ],
    )
    report = BackupLogParser(log).parse()
    assert report is not None
    d = report.to_dict()
    assert d["scope"] == "pools"
    assert d["pool_dirs"] == 3
    assert d["backup_types_status"]["pools"] == "success"


# backward compatibility of the report sender (fake client via _post_report)


def _pools_payload(status="CRITICAL"):
    return {
        "timestamp": 1,
        "status": status,
        "type": "automated",
        "scope": "pools",
        "summary": "x",
    }


def _queued(tmp_path):
    return [f for f in os.listdir(str(tmp_path)) if f.endswith(".json")]


def test_pools_scope_rejection_resends_as_full(tmp_path, monkeypatch):
    calls = []

    def fake_post(payload):
        calls.append(dict(payload))
        if payload["scope"] == "pools":
            raise ApiV4Error(
                400, "bad_request", "Backup scope must be one of: full, db"
            )
        return None

    monkeypatch.setattr(backup_report, "_post_report", fake_post)
    ok = backup_report.send_with_queue(
        _pools_payload(), queue_dir=str(tmp_path), max_attempts=2
    )
    assert ok is True
    assert [c["scope"] for c in calls] == ["pools", "full"]
    assert calls[1]["scope_requested"] == "pools"
    assert _queued(tmp_path) == []


def test_invalid_report_is_dropped_not_queued(tmp_path, monkeypatch):
    monkeypatch.setattr(
        backup_report,
        "_post_report",
        lambda p: (_ for _ in ()).throw(
            ApiV4Error(400, "bad_request", "missing required field: timestamp")
        ),
    )
    ok = backup_report.send_with_queue(
        {"timestamp": 1, "status": "SUCCESS", "type": "automated", "scope": "disks"},
        queue_dir=str(tmp_path),
        max_attempts=2,
    )
    assert ok is False
    assert _queued(tmp_path) == []


def test_transient_failure_is_queued(tmp_path, monkeypatch):
    monkeypatch.setattr(
        backup_report,
        "_post_report",
        lambda p: (_ for _ in ()).throw(ApiV4Error(503, "maintenance", "down")),
    )
    ok = backup_report.send_with_queue(
        {"timestamp": 1, "status": "SUCCESS", "type": "automated", "scope": "db"},
        queue_dir=str(tmp_path),
        max_attempts=1,
    )
    assert ok is False
    assert _queued(tmp_path)


def test_pools_fallback_transient_queues_the_full_payload(tmp_path, monkeypatch):
    def fake_post(payload):
        if payload["scope"] == "pools":
            raise ApiV4Error(400, "bad_request", "Backup scope must be one of: full")
        raise ApiV4Error(503, "maintenance", "down")

    monkeypatch.setattr(backup_report, "_post_report", fake_post)
    ok = backup_report.send_with_queue(
        _pools_payload(), queue_dir=str(tmp_path), max_attempts=1
    )
    assert ok is False
    files = _queued(tmp_path)
    assert files
    q = json.loads((tmp_path / files[0]).read_text())
    assert q["scope"] == "full"
    assert q["scope_requested"] == "pools"


def test_flush_drops_invalid_queued_report(tmp_path, monkeypatch):
    (tmp_path / "report-1.json").write_text(
        json.dumps(
            {"timestamp": 1, "status": "SUCCESS", "type": "automated", "scope": "bogus"}
        )
    )
    monkeypatch.setattr(
        backup_report,
        "_post_report",
        lambda p: (_ for _ in ()).throw(
            ApiV4Error(400, "bad_request", "invalid scope")
        ),
    )
    sent = backup_report.flush_queue(str(tmp_path), max_attempts=1)
    assert sent == 0
    assert not (tmp_path / "report-1.json").exists()
