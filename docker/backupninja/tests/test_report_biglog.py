"""Session detection must survive a large log and a copytruncate rotation."""

import pytest

pytest.importorskip("isardvdi_apiv4_client")

from isardvdi_backupninja.backup_report import BackupLogParser  # noqa: E402


def _session(day, scope, status):
    ts = f"2026-{day:02d}-01T01:0"
    return [
        f"{ts}0:00 Info: BACKUP_SESSION_START: automated {scope} backup "
        f"initiated by cron (schedule: everyday at 01:00)",
        f"{ts}0:01 Info: >>>> starting action /x/22-db-dump.sh",
        *([f"{ts}0:02 Fatal: db dump failed"] if status == "CRITICAL" else []),
        f"{ts}0:03 Info: <<<< finished action /x/22-db-dump.sh: "
        f"{'FATAL' if status == 'CRITICAL' else 'SUCCESS'}",
        f"{ts}5:00 Info: BACKUP_SESSION_END: automated {scope} backup completed",
    ]


def test_last_session_wins_in_a_year_long_log(tmp_path):
    lines = []
    # 600 successful padding sessions (thousands of lines), then a CRITICAL one.
    for i in range(600):
        lines += _session((i % 12) + 1, "db", "SUCCESS")
    lines += _session(6, "db", "CRITICAL")
    log = tmp_path / "backupninja.log"
    log.write_text("\n".join(lines) + "\n")
    assert len(lines) > 2000  # exceeds the parser's tail window

    report = BackupLogParser(str(log)).parse()
    assert report is not None
    assert report.to_dict()["status"] == "CRITICAL"


def test_fresh_file_after_copytruncate_parses(tmp_path):
    # copytruncate leaves the current file holding only the new session.
    log = tmp_path / "backupninja.log"
    log.write_text("\n".join(_session(6, "pools", "SUCCESS")) + "\n")
    report = BackupLogParser(str(log)).parse()
    assert report is not None
    d = report.to_dict()
    assert d["scope"] == "pools"
    assert d["status"] == "SUCCESS"
