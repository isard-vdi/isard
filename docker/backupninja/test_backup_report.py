"""Unit tests for ``backup_report._build_request_body``.

Runs only where the generated apiv4 client is installed (the backupninja build
image / CI codegen env); skipped otherwise. Guards the regression where the
parser's undeclared fields (``disk_types``, ``actions``, the ``*_actions``
counts, ``duration``, ``backup_types_status``, ...) crashed
``_build_request_body`` via ``setattr`` on the generated attrs ``__slots__``
model — aborting the build before any POST and silently queuing every report.
"""

import pytest

pytest.importorskip("isardvdi_apiv4_client")
pytest.importorskip("isardvdi_apiv4_client_auth")

import backup_report  # noqa: E402


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
