"""Two schedules firing in the same backupninja pass must report as one full session."""

import pytest

pytest.importorskip("isardvdi_apiv4_client")

from isardvdi_backupninja.backup_report import BackupLogParser  # noqa: E402

D = "/usr/local/etc/backup.d"


def _action(ts, name, status="SUCCESS"):
    return [
        f"{ts} Info: >>>> starting action {D}/{name}",
        f"{ts} Info: <<<< finished action {D}/{name}: {status}",
    ]


def _overlapping_pass(day="2026-11-18"):
    """One pass where 'everyday at 01' (full) and 'everyday at 01:00' (pools) both fire."""
    t = f"{day}T01:0"
    return [
        f"{t}0:00 Info: >>>> starting action {D}/10-session-start-0.sh",
        f"{t}0:00 Info: BACKUP_SESSION_START: automated full backup initiated "
        "by cron (schedule: everyday at 01)",
        f"{t}0:00 Info: <<<< finished action {D}/10-session-start-0.sh: SUCCESS",
        f"{t}0:01 Info: >>>> starting action {D}/10-session-start-1.sh",
        f"{t}0:01 Info: BACKUP_SESSION_START: automated pools backup initiated "
        "by cron (schedule: everyday at 01:00)",
        f"{t}0:01 Info: <<<< finished action {D}/10-session-start-1.sh: SUCCESS",
        *_action(f"{t}1:00", "22-db-dump.sh"),
        *_action(f"{t}2:00", "33-redis-borg.borg"),
        *_action(f"{t}3:00", "82-disks-borg.borg"),
        *_action(f"{t}4:00", "87-pools-borg.sh"),
        f"{t}5:00 Info: >>>> starting action {D}/90-session-report-0.sh",
        f"{t}5:00 Info: BACKUP_SESSION_END: automated backup completed",
    ]


def _second_report_tail(day="2026-11-18"):
    t = f"{day}T01:0"
    return [
        f"{t}5:01 Info: <<<< finished action {D}/90-session-report-0.sh: SUCCESS",
        f"{t}5:02 Info: >>>> starting action {D}/90-session-report-1.sh",
        f"{t}5:02 Info: BACKUP_SESSION_END: automated backup completed",
    ]


def _parse(tmp_path, lines):
    log = tmp_path / "backupninja.log"
    log.write_text("\n".join(lines) + "\n")
    report = BackupLogParser(str(log)).parse()
    assert report is not None
    return report.to_dict()


def _kinds(report):
    return {a["name"].rsplit("/", 1)[1].split("-")[1] for a in report["actions"]}


def test_first_report_of_overlapping_pass_is_full(tmp_path):
    d = _parse(tmp_path, _overlapping_pass())
    assert d["scope"] == "full"
    assert d["type"] == "automated"
    assert {"db", "redis", "disks", "pools"} <= _kinds(d)


def test_second_report_of_overlapping_pass_is_full(tmp_path):
    d = _parse(tmp_path, _overlapping_pass() + _second_report_tail())
    assert d["scope"] == "full"
    assert {"db", "redis", "disks", "pools"} <= _kinds(d)


def test_previous_pass_is_not_merged(tmp_path):
    t = "2026-11-19T01:0"
    previous = _overlapping_pass("2026-11-18") + _second_report_tail("2026-11-18")
    previous.append("2026-11-18T01:05:03 Info: FINISHED: 7 actions run. 0 fatal.")
    today = [
        f"{t}0:00 Info: >>>> starting action {D}/10-session-start-1.sh",
        f"{t}0:00 Info: BACKUP_SESSION_START: automated pools backup initiated "
        "by cron (schedule: saturday at 01)",
        f"{t}0:00 Info: <<<< finished action {D}/10-session-start-1.sh: SUCCESS",
        *_action(f"{t}4:00", "87-pools-borg.sh"),
        f"{t}5:00 Info: BACKUP_SESSION_END: automated backup completed",
    ]
    d = _parse(tmp_path, previous + today)
    assert d["scope"] == "pools"
    assert _kinds(d) == {"pools"}


def test_single_session_scope_unchanged(tmp_path):
    lines = _overlapping_pass()
    # Drop the pools session start: a plain full session.
    lines = lines[:3] + lines[6:]
    d = _parse(tmp_path, lines)
    assert d["scope"] == "full"
