#!/usr/bin/env python3
"""
BackupNinja Report Sender

Parses the backupninja log of the most recent completed backup session,
shapes it into a JSON report and POSTs it to the IsardVDI API at
POST /api/v4/backups via the generated apiv4 Python client (with a
service-signed JWT).

Design notes:
  * Each schedule (DB, Redis, …) writes its own SESSION_START / SESSION_END
    markers and calls this script. One invocation = one report.
  * Log lines use ISO-8601 timestamps when available (new markers) and fall
    back to syslog-style "Mon DD HH:MM:SS" (backupninja's own lines).
  * Year-rollover for syslog-style lines is inferred from the latest ISO
    timestamp seen, or from the log file's mtime — never from `now()` alone.
  * If the API POST fails the payload is appended to a replay queue and
    retried on the next invocation.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from isardvdi_apiv4_client.api.role_admin import admin_backup_report
from isardvdi_apiv4_client.models import BackupReportRequest
from isardvdi_apiv4_client_auth import build_client, raise_for_status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


LOG_PATH_DEFAULT = "/var/log/backupninja.log"
QUEUE_DIR_DEFAULT = "/var/log/backupninja.queue"
BACKUP_ROOT = "/backup"
SOURCE_ROOT = "/opt/isard"

# Map the numeric handler-name prefix to a logical backup type.
# Handler filenames are `<prefix>-<type>-<phase>.*` — see run.sh.
PREFIX_TYPE_RANGES: List[Tuple[int, int, str]] = [
    (10, 19, "session"),
    (20, 29, "db"),
    (30, 39, "redis"),
    (40, 49, "stats"),
    (70, 79, "config"),
    (80, 89, "disks"),
    (90, 99, "session"),
]

VALID_SCOPES = {"full", "db", "redis", "stats", "config", "disks"}

SUCCESS_STATUSES = {"SUCCESS", "OK"}
WARNING_STATUSES = {"WARNING"}
ERROR_STATUSES = {"ERROR", "FAILED"}
FATAL_STATUSES = {"FATAL", "CRITICAL"}

# Patterns whose presence alone should not raise an action above SUCCESS.
# Borg always prints these on stderr regardless of severity; treating them as
# warnings created false alarms and pointless WARNING reports.
INFORMATIONAL_PATTERNS_GLOBAL: Tuple[str, ...] = (
    "Attempting to access a previously unknown unencrypted repository",
    "Backing up source finished with warnings",
)
# Per-action-type informational patterns. "file changed while we backed it up"
# is expected for live VM disk backup but would be a real concern if it
# appeared during a controlled dump (db, redis, config), so it is scoped.
INFORMATIONAL_PATTERNS_BY_TYPE: Dict[str, Tuple[str, ...]] = {
    "disks": ("file changed while we backed it up",),
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BackupAction:
    name: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: str = "UNKNOWN"
    duration: Optional[float] = None
    messages: List[str] = field(default_factory=list)
    info_messages: List[str] = field(default_factory=list)
    borg_statistics: Optional[Dict[str, Any]] = None
    compact_results: Optional[Dict[str, Any]] = None

    def classify(self) -> str:
        """Return 'db' | 'redis' | 'stats' | 'config' | 'disks' | 'other'."""
        basename = self.name.rsplit("/", 1)[-1]
        match = re.match(r"(\d+)", basename)
        if not match:
            return "other"
        prefix = int(match.group(1))
        for lo, hi, kind in PREFIX_TYPE_RANGES:
            if lo <= prefix <= hi:
                return kind
        return "other"


@dataclass
class BackupReport:
    timestamp: datetime
    status: str
    total_actions: int
    successful_actions: int
    failed_actions: int
    warning_actions: int
    fatal_actions: int
    actions: List[Dict[str, Any]]
    summary: str
    backup_type: Optional[str] = None
    backup_scope: Optional[str] = None
    disk_types: Optional[List[str]] = None
    backup_types_status: Optional[Dict[str, str]] = None
    backup_type_summary: Optional[Dict[str, Any]] = None
    filesystem_metrics: Optional[Dict[str, Any]] = None
    backup_config: Optional[Dict[str, Any]] = None
    host: Optional[str] = None

    def total_duration(self) -> Optional[int]:
        total = 0.0
        for action in self.actions:
            duration = action.get("duration")
            if duration and duration > 0:
                total += duration
        return int(total) if total > 0 else None

    def to_dict(self) -> Dict[str, Any]:
        backup_type = self.backup_type or os.getenv("BACKUP_TYPE", "automated")
        if backup_type not in ("automated", "manual"):
            backup_type = "automated"

        scope = self.backup_scope or "full"
        if scope not in VALID_SCOPES:
            scope = "full"

        out: Dict[str, Any] = {
            "timestamp": int(self.timestamp.timestamp()),
            "host": self.host or resolve_host_name(),
            "status": self.status,
            "type": backup_type,
            "scope": scope,
            "disk_types": self.disk_types,
            "backup_types_status": self.backup_types_status,
            "total_actions": self.total_actions,
            "successful_actions": self.successful_actions,
            "failed_actions": self.failed_actions,
            "warning_actions": self.warning_actions,
            "fatal_actions": self.fatal_actions,
            "actions": self.actions,
            "summary": self.summary,
            "duration": self.total_duration(),
        }
        if self.backup_type_summary:
            out["backup_types"] = self.backup_type_summary
        if self.filesystem_metrics:
            out["filesystem_metrics"] = self.filesystem_metrics
        if self.backup_config:
            out["backup_config"] = self.backup_config
        return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def resolve_host_name() -> str:
    """Identifier for the host running backupninja. Honours BACKUP_HOST_NAME."""
    name = os.environ.get("BACKUP_HOST_NAME")
    if name:
        return name
    try:
        return socket.gethostname() or "unknown-host"
    except Exception:
        return "unknown-host"


def format_bytes(value: Any) -> str:
    """Human-readable size. Accepts int/float/numeric-string, else '0 B'."""
    try:
        size = float(value)
    except (TypeError, ValueError):
        return "0 B"
    if size <= 0:
        return "0 B"
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} P"


def parse_iso8601(value: str) -> Optional[datetime]:
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except Exception:
        return None


SYSLOG_RE = re.compile(r"^(\w{3})\s+(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})")
ISO_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)

MONTHS = {
    m: i + 1
    for i, m in enumerate(
        [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
    )
}


def line_timestamp(line: str, anchor_year: int) -> Optional[datetime]:
    """Extract a datetime from the start of `line`.

    Accepts ISO-8601 (preferred) or syslog-style "Mon DD HH:MM:SS". For
    syslog lines the caller provides an anchor year — typically the year of
    the most recent ISO timestamp seen so far, or the log file's mtime year.
    """
    iso = ISO_RE.match(line)
    if iso:
        parsed = parse_iso8601(iso.group(1))
        if parsed:
            return parsed

    match = SYSLOG_RE.match(line)
    if not match:
        return None
    month = MONTHS.get(match.group(1))
    if not month:
        return None
    try:
        return datetime(
            anchor_year,
            month,
            int(match.group(2)),
            int(match.group(3)),
            int(match.group(4)),
            int(match.group(5)),
        )
    except ValueError:
        return None


def build_year_anchors(log_lines: List[str], fallback_year: int) -> List[int]:
    """Return a list the same length as `log_lines` giving the year to use
    for each syslog-style line. Year changes only when:
      * an ISO-dated line is seen (absolute year), or
      * the syslog month wraps from Dec back to Jan.
    """
    years: List[int] = [fallback_year] * len(log_lines)
    current_year = fallback_year
    prev_month: Optional[int] = None

    for i, line in enumerate(log_lines):
        iso = ISO_RE.match(line)
        if iso:
            parsed = parse_iso8601(iso.group(1))
            if parsed:
                current_year = parsed.year
                prev_month = parsed.month
                years[i] = current_year
                continue

        match = SYSLOG_RE.match(line)
        if match:
            month = MONTHS.get(match.group(1))
            if month is not None:
                # Syslog logs are chronological. If we see Dec then Jan, the
                # Jan entries belong to the following year.
                if prev_month is not None and prev_month == 12 and month == 1:
                    current_year += 1
                prev_month = month
        years[i] = current_year

    return years


def log_mtime_year(log_path: str) -> int:
    try:
        return datetime.fromtimestamp(os.path.getmtime(log_path)).year
    except OSError:
        return datetime.now().year


def _is_informational(line: str, action_kind: str) -> bool:
    if any(p in line for p in INFORMATIONAL_PATTERNS_GLOBAL):
        return True
    for p in INFORMATIONAL_PATTERNS_BY_TYPE.get(action_kind, ()):
        if p in line:
            return True
    return False


def _demote_informational_warnings(actions: List["BackupAction"]) -> None:
    for a in actions:
        if a.status in WARNING_STATUSES and not a.messages and a.info_messages:
            a.status = "SUCCESS"


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------


class BackupLogParser:
    def __init__(self, log_path: str = LOG_PATH_DEFAULT) -> None:
        self.log_path = log_path

    def tail_lines(self, max_lines: int = 2000) -> List[str]:
        try:
            with open(self.log_path, "r") as fh:
                lines = fh.readlines()
        except OSError as e:
            logger.error("Cannot read log %s: %s", self.log_path, e)
            return []
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        return [line.rstrip("\n") for line in lines]

    def find_last_session(self, log_lines: List[str]) -> List[str]:
        """Lines between the latest SESSION_START and SESSION_END (inclusive).

        Falls back to the lines between the latest SESSION_START and the
        latest FINISHED line, and finally to everything after the latest
        SESSION_START (partial session still running).
        """
        end_idx = _last_index(log_lines, "BACKUP_SESSION_END:")
        start_idx = _last_index(log_lines, "BACKUP_SESSION_START:", up_to=end_idx)

        if end_idx is not None and start_idx is not None and start_idx < end_idx:
            return log_lines[start_idx : end_idx + 1]

        finished_idx = _last_index(log_lines, "FINISHED:")
        if (
            start_idx is not None
            and finished_idx is not None
            and start_idx < finished_idx
        ):
            return log_lines[start_idx : finished_idx + 1]

        if start_idx is not None:
            return log_lines[start_idx:]

        return []

    def parse(self) -> Optional[BackupReport]:
        all_lines = self.tail_lines()
        if not all_lines:
            return None

        session_lines = self.find_last_session(all_lines)
        if not session_lines:
            logger.info("No backup session markers found; nothing to report.")
            return None

        anchors = build_year_anchors(session_lines, log_mtime_year(self.log_path))
        actions = self._parse_actions(session_lines, anchors)
        self._attach_borg_statistics(session_lines, actions)
        self._attach_compact_results(session_lines, actions)

        session_info = self._parse_session_markers(session_lines, anchors)
        backup_type = session_info.get("backup_type")
        backup_scope = session_info.get("backup_scope") or derive_scope_from_actions(
            actions
        )
        disk_types = session_info.get("disk_types")
        session_timestamp = session_info.get("timestamp") or _fallback_timestamp(
            actions
        )

        success = sum(1 for a in actions if a.status in SUCCESS_STATUSES)
        warning = sum(1 for a in actions if a.status in WARNING_STATUSES)
        error = sum(1 for a in actions if a.status in ERROR_STATUSES)
        fatal = sum(1 for a in actions if a.status in FATAL_STATUSES)
        total = len(actions)

        if fatal:
            overall_status = "CRITICAL"
            summary = f"Backup completed with {fatal} fatal errors"
        elif error:
            overall_status = "ERROR"
            summary = f"Backup completed with {error} errors"
        elif warning:
            overall_status = "WARNING"
            summary = f"Backup completed with {warning} warnings"
        elif total == 0:
            overall_status = "UNKNOWN"
            summary = "No actions were recorded for this session"
        else:
            overall_status = "SUCCESS"
            summary = f"Backup completed successfully with {total} actions"

        filesystem_metrics = collect_filesystem_metrics()
        backup_config = collect_backup_config()
        backup_types_status = analyze_backup_types_status(actions, backup_config)
        backup_types_summary = generate_type_summary(actions, filesystem_metrics)

        return BackupReport(
            timestamp=session_timestamp or datetime.now(),
            status=overall_status,
            total_actions=total,
            successful_actions=success,
            failed_actions=error,
            warning_actions=warning,
            fatal_actions=fatal,
            actions=[_action_to_dict(a) for a in actions],
            summary=summary,
            backup_type=backup_type,
            backup_scope=backup_scope,
            disk_types=disk_types,
            backup_types_status=backup_types_status,
            backup_type_summary=backup_types_summary,
            filesystem_metrics=filesystem_metrics,
            backup_config=backup_config,
            host=resolve_host_name(),
        )

    # -----------------------------------------------------------------------
    # Action parsing
    # -----------------------------------------------------------------------

    def _parse_actions(
        self, log_lines: List[str], anchors: List[int]
    ) -> List[BackupAction]:
        actions: List[BackupAction] = []
        current: Optional[BackupAction] = None

        for i, line in enumerate(log_lines):
            if ">>>> starting action" in line:
                match = re.search(r"starting action (\S+)", line)
                if match:
                    current = BackupAction(
                        name=match.group(1),
                        start_time=line_timestamp(line, anchors[i]),
                        status="RUNNING",
                    )

            elif "<<<< finished action" in line and current:
                match = re.search(r"finished action ([^:]+):\s*(\w+)", line)
                if match:
                    current.status = match.group(2).upper()
                    current.end_time = line_timestamp(line, anchors[i])
                    if current.start_time and current.end_time:
                        current.duration = (
                            current.end_time - current.start_time
                        ).total_seconds()
                    actions.append(current)
                    current = None

            elif current and (
                "Warning:" in line or "Error:" in line or "Fatal:" in line
            ):
                if _is_informational(line, current.classify()):
                    current.info_messages.append(line)
                else:
                    current.messages.append(line)

        _demote_informational_warnings(actions)
        return actions

    # -----------------------------------------------------------------------
    # Borg statistics
    # -----------------------------------------------------------------------

    def _attach_borg_statistics(
        self, log_lines: List[str], actions: List[BackupAction]
    ) -> None:
        self._attach_structured_stats(log_lines, actions)
        self._attach_native_stats(log_lines, actions)

    def _attach_structured_stats(
        self, log_lines: List[str], actions: List[BackupAction]
    ) -> None:
        for line in log_lines:
            if "BORG_STATS_" not in line or "STATS_JSON:" not in line:
                continue
            type_match = re.search(r"BORG_STATS_(\w+):", line)
            json_match = re.search(r"STATS_JSON:\s*(.+)$", line)
            if not (type_match and json_match):
                continue
            backup_type = type_match.group(1).lower()
            try:
                stats_data = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                continue
            stats = stats_data.get("stats", {})
            payload = {
                "repository": f"/backup/{backup_type}",
                "backup_type": backup_type,
                "file_count": stats.get("nfiles"),
                "original_size": format_bytes(stats.get("original_size", 0)),
                "compressed_size": format_bytes(stats.get("compressed_size", 0)),
                "deduplicated_size": format_bytes(stats.get("deduplicated_size", 0)),
                "original_size_bytes": stats.get("original_size", 0),
                "compressed_size_bytes": stats.get("compressed_size", 0),
                "deduplicated_size_bytes": stats.get("deduplicated_size", 0),
            }
            for action in actions:
                if (
                    action.borg_statistics is None
                    and backup_type in action.name.lower()
                    and action.name.lower().endswith("borg.borg")
                ):
                    action.borg_statistics = payload
                    break

    def _attach_native_stats(
        self, log_lines: List[str], actions: List[BackupAction]
    ) -> None:
        i = 0
        while i < len(log_lines):
            line = log_lines[i]
            if "Repository: /backup/" not in line:
                i += 1
                continue
            repo_match = re.search(r"Repository:\s+(/backup/(\w+))", line)
            if not repo_match:
                i += 1
                continue
            repository = repo_match.group(1)
            backup_type = repo_match.group(2)

            archive_name = None
            file_count = None
            sizes: Optional[Tuple[str, str, str]] = None
            end = min(i + 20, len(log_lines))
            j = i + 1
            while j < end:
                probe = log_lines[j]
                if "Archive name:" in probe:
                    m = re.search(r"Archive name:\s*(.+)", probe)
                    if m:
                        archive_name = m.group(1).strip()
                elif "Number of files:" in probe:
                    m = re.search(r"Number of files:\s*(\d+)", probe)
                    if m:
                        file_count = int(m.group(1))
                elif "This archive:" in probe:
                    m = re.search(
                        r"This archive:\s+([0-9.]+\s*[KMG]?B)\s+"
                        r"([0-9.]+\s*[KMG]?B)\s+([0-9.]+\s*[KMG]?B)",
                        probe,
                    )
                    if m:
                        sizes = (m.group(1), m.group(2), m.group(3))
                        break
                j += 1

            if sizes:
                payload = {
                    "repository": repository,
                    "backup_type": backup_type,
                    "archive_name": archive_name,
                    "file_count": file_count,
                    "original_size": sizes[0],
                    "compressed_size": sizes[1],
                    "deduplicated_size": sizes[2],
                }
                for action in actions:
                    if (
                        action.borg_statistics is None
                        and backup_type in action.name.lower()
                        and "borg" in action.name.lower()
                    ):
                        action.borg_statistics = payload
                        break
            i = j + 1 if sizes else i + 1

    def _attach_compact_results(
        self, log_lines: List[str], actions: List[BackupAction]
    ) -> None:
        for line in log_lines:
            lowered = line.lower()
            if "compact succeeded" in lowered or "compaction completed" in lowered:
                status = "success"
            elif "compact failed" in lowered or "compaction failed" in lowered:
                status = "failed"
            else:
                continue
            for action in actions:
                if action.compact_results is None and "compact" in action.name.lower():
                    action.compact_results = {
                        "operation": "compact",
                        "status": status,
                        "message": line,
                    }
                    break

    # -----------------------------------------------------------------------
    # Session markers
    # -----------------------------------------------------------------------

    def _parse_session_markers(
        self, log_lines: List[str], anchors: List[int]
    ) -> Dict[str, Any]:
        info: Dict[str, Any] = {}
        for i, line in enumerate(log_lines):
            if "BACKUP_SESSION_START:" in line:
                m = re.search(r"BACKUP_SESSION_START:\s+(\w+)\s+(\S+)\s+backup", line)
                if m:
                    backup_type = m.group(1).lower()
                    scope = m.group(2).lower()
                    info["backup_type"] = (
                        backup_type if backup_type in ("automated", "manual") else None
                    )
                    info["backup_scope"] = scope if scope in VALID_SCOPES else None
            if "BACKUP_DISK_TYPES:" in line:
                m = re.search(r"BACKUP_DISK_TYPES:\s*(.+)$", line)
                if m and m.group(1).strip():
                    info["disk_types"] = m.group(1).split()

        # Pick the timestamp from SESSION_END (preferred) or FINISHED.
        for i in range(len(log_lines) - 1, -1, -1):
            line = log_lines[i]
            if "BACKUP_SESSION_END:" in line or "FINISHED:" in line:
                ts = line_timestamp(line, anchors[i])
                if ts:
                    info["timestamp"] = ts
                break

        return info


def _last_index(
    lines: List[str], needle: str, up_to: Optional[int] = None
) -> Optional[int]:
    end = len(lines) - 1 if up_to is None else up_to - 1
    for i in range(end, -1, -1):
        if needle in lines[i]:
            return i
    return None


def _fallback_timestamp(actions: List[BackupAction]) -> Optional[datetime]:
    for action in reversed(actions):
        if action.end_time:
            return action.end_time
        if action.start_time:
            return action.start_time
    return None


def _action_to_dict(action: BackupAction) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "name": action.name,
        "status": action.status,
        "duration": action.duration,
        "messages": action.messages,
        "info_messages": action.info_messages,
    }
    if action.start_time:
        out["start_time"] = action.start_time.isoformat()
    if action.end_time:
        out["end_time"] = action.end_time.isoformat()
    if action.borg_statistics:
        out["borg_statistics"] = action.borg_statistics
    if action.compact_results:
        out["compact_results"] = action.compact_results
    return out


def derive_scope_from_actions(actions: List[BackupAction]) -> Optional[str]:
    """If all actions belong to a single logical type, use that as the scope."""
    kinds = {a.classify() for a in actions if a.classify() not in ("other", "session")}
    kinds.discard("session")
    if len(kinds) == 1:
        only = kinds.pop()
        if only in VALID_SCOPES:
            return only
    if kinds:
        return "full"
    return None


# ---------------------------------------------------------------------------
# Status analysis
# ---------------------------------------------------------------------------


def analyze_backup_types_status(
    actions: List[BackupAction], backup_config: Dict[str, Any]
) -> Dict[str, str]:
    """Per-type status, including per-sub-source breakdown for disks."""

    status: Dict[str, str] = {
        t: "not_included" for t in ("db", "redis", "stats", "config", "disks")
    }
    per_type: Dict[str, List[BackupAction]] = {t: [] for t in status}

    for action in actions:
        kind = action.classify()
        if kind in per_type:
            per_type[kind].append(action)

    for kind, kind_actions in per_type.items():
        if not kind_actions:
            continue
        status[kind] = _aggregate_status(kind_actions)

    # Disk sub-sources: emit only the enabled ones, since all three share
    # the same borg repo and we can't tell them apart from action names.
    disks_cfg = backup_config.get("disks") or {}
    for sub in ("templates", "groups", "media"):
        if disks_cfg.get(f"{sub}_enabled"):
            status[f"disks:{sub}"] = status["disks"]

    return status


def _aggregate_status(actions: List[BackupAction]) -> str:
    has_failed = any(
        a.status in ERROR_STATUSES or a.status in FATAL_STATUSES for a in actions
    )
    if has_failed:
        return "failed"
    has_warning = any(a.status in WARNING_STATUSES for a in actions)
    has_success = any(a.status in SUCCESS_STATUSES for a in actions)
    if has_warning and not has_success:
        return "warning"
    if has_success:
        return "success"
    return "not_included"


def generate_type_summary(
    actions: List[BackupAction], filesystem_metrics: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    per_type: Dict[str, List[BackupAction]] = {}
    for action in actions:
        kind = action.classify()
        if kind in ("session", "other"):
            continue
        per_type.setdefault(kind, []).append(action)

    out: Dict[str, Any] = {}
    for kind, kind_actions in per_type.items():
        summary = {
            "total_actions": len(kind_actions),
            "successful": sum(1 for a in kind_actions if a.status in SUCCESS_STATUSES),
            "warnings": sum(1 for a in kind_actions if a.status in WARNING_STATUSES),
            "errors": sum(
                1
                for a in kind_actions
                if a.status in ERROR_STATUSES or a.status in FATAL_STATUSES
            ),
            "total_duration": sum((a.duration or 0) for a in kind_actions),
            "actions": [
                {
                    "name": a.name.rsplit("/", 1)[-1],
                    "status": a.status,
                    "duration": a.duration,
                }
                for a in kind_actions
            ],
        }

        borg_stats = next(
            (a.borg_statistics for a in kind_actions if a.borg_statistics),
            None,
        )
        if not borg_stats and filesystem_metrics:
            borg_stats = _borg_stats_from_filesystem(kind, filesystem_metrics)
        if borg_stats:
            summary["borg_statistics"] = borg_stats

        out[kind] = summary
    return out


def _borg_stats_from_filesystem(
    kind: str, filesystem_metrics: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    repos = filesystem_metrics.get("borg_repositories") or {}
    repo = repos.get(kind)
    if not repo:
        return None
    archive = repo.get("latest_archive") or {}
    stats = archive.get("stats") or {}
    if not stats:
        return None
    return {
        "repository": repo.get("location"),
        "archive_name": archive.get("name"),
        "file_count": stats.get("nfiles"),
        "original_size": format_bytes(stats.get("original_size", 0)),
        "compressed_size": format_bytes(stats.get("compressed_size", 0)),
        "deduplicated_size": format_bytes(stats.get("deduplicated_size", 0)),
    }


# ---------------------------------------------------------------------------
# Filesystem + configuration collection
# ---------------------------------------------------------------------------


def collect_filesystem_metrics() -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}

    usage = _df_usage()
    if usage:
        metrics["usage"] = usage

    backup_sizes = _du_sizes(BACKUP_ROOT, skip={"extract"})
    if backup_sizes:
        metrics["backup_sizes"] = backup_sizes

    source_sizes = _du_sizes(SOURCE_ROOT, skip=set(), drop_trivial=True)
    if source_sizes:
        metrics["source_sizes"] = source_sizes

    borg_repos = _borg_repositories(BACKUP_ROOT)
    if borg_repos:
        metrics["borg_repositories"] = borg_repos

    return metrics


def _df_usage() -> Dict[str, Any]:
    try:
        result = subprocess.run(
            ["df", "-h"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("df failed: %s", e)
        return {}
    usage: Dict[str, Any] = {}
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        device, size, used, avail, pct, mount = parts[:6]
        try:
            pct_int = int(pct.rstrip("%"))
        except ValueError:
            continue
        entry = {
            "device": device,
            "size": size,
            "used": used,
            "available": avail,
            "usage_percent": pct_int,
            "mount_point": mount,
        }
        if mount == "/backup":
            usage["backup_storage"] = entry
        elif mount.startswith("/opt") or "raid" in device.lower():
            usage["source_storage"] = entry
    return usage


def _du_sizes(root: str, skip: set, drop_trivial: bool = False) -> Dict[str, str]:
    """Per-child directory size under `root`. Uses Python glob (no shell)."""
    sizes: Dict[str, str] = {}
    if not os.path.isdir(root):
        return sizes
    for path in sorted(glob.glob(os.path.join(root, "*"))):
        name = os.path.basename(path)
        if name in skip:
            continue
        try:
            proc = subprocess.run(
                ["du", "-sh", path],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as e:
            logger.warning("du failed for %s: %s", path, e)
            continue
        line = (proc.stdout or "").strip()
        if not line:
            continue
        size = line.split(None, 1)[0]
        if drop_trivial and size in {"0", "4.0K"}:
            continue
        sizes[name] = size
    return sizes


def _borg_repositories(root: str) -> Dict[str, Any]:
    if not os.path.isdir(root):
        return {}
    env = os.environ.copy()
    env.setdefault("BORG_PASSPHRASE", "")
    env.setdefault("BORG_RELOCATED_REPO_ACCESS_IS_OK", "yes")
    env.setdefault("BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK", "yes")

    repos: Dict[str, Any] = {}
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if not os.path.isdir(path) or name == "extract":
            continue
        info = _run_borg_json(["borg", "info", path, "--json"], env)
        if not info or "repository" not in info:
            continue
        entry: Dict[str, Any] = {
            "repository_id": (info["repository"].get("id") or "")[:16],
            "location": info["repository"].get("location", path),
        }
        archives = _run_borg_json(["borg", "list", path, "--json"], env)
        if archives and archives.get("archives"):
            latest = archives["archives"][-1]
            archive_name = latest.get("name")
            detail = _run_borg_json(
                ["borg", "info", f"{path}::{archive_name}", "--json"], env
            )
            stats = {}
            start = latest.get("start", "N/A")
            end = "N/A"
            duration = 0
            if detail and detail.get("archives"):
                details = detail["archives"][0]
                stats = details.get("stats", {})
                start = details.get("start", start)
                end = details.get("end", end)
                duration = details.get("duration", duration)
            entry["latest_archive"] = {
                "name": archive_name,
                "start": start,
                "end": end,
                "duration": duration,
                "stats": stats,
            }
        repos[name] = entry
    return repos


def _run_borg_json(cmd: List[str], env: Dict[str, str]) -> Optional[Dict[str, Any]]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, env=env, check=False
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("borg cmd failed (%s): %s", " ".join(cmd), e)
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def collect_backup_config() -> Dict[str, Any]:
    def parse_schedule(raw: Optional[str]) -> Optional[Dict[str, Any]]:
        if not raw:
            return None
        m = re.search(r"at\s+(\d{1,2})(?::(\d{2}))?", raw)
        if not m:
            return None
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        return {"hour": hour, "minute": minute, "text": raw}

    cfg: Dict[str, Any] = {
        "schedule": {
            kind: parse_schedule(os.getenv(f"BACKUP_{kind.upper()}_WHEN"))
            for kind in ("db", "redis", "stats", "config", "disks")
        },
        "enabled": {
            kind: os.getenv(f"BACKUP_{kind.upper()}_ENABLED", "false").lower() == "true"
            for kind in ("db", "redis", "stats", "config", "disks")
        },
        "prune_policies": {
            kind: os.getenv(f"BACKUP_{kind.upper()}_PRUNE", "")
            for kind in ("db", "redis", "stats", "config", "disks")
        },
        "nfs": {
            "enabled": os.getenv("BACKUP_NFS_ENABLED", "false").lower() == "true",
            "server": os.getenv("BACKUP_NFS_SERVER", ""),
            "folder": os.getenv("BACKUP_NFS_FOLDER", ""),
        },
        "disks": {
            "templates_enabled": os.getenv(
                "BACKUP_DISKS_TEMPLATES_ENABLED", "false"
            ).lower()
            == "true",
            "groups_enabled": os.getenv("BACKUP_DISKS_GROUPS_ENABLED", "false").lower()
            == "true",
            "media_enabled": os.getenv("BACKUP_DISKS_MEDIA_ENABLED", "false").lower()
            == "true",
        },
        "email": os.getenv("BACKUP_REPORT_EMAIL", ""),
        "backup_dir": os.getenv("BACKUP_DIR", "/opt/isard-local/backup"),
    }

    enabled_schedules = [
        cfg["schedule"][k]
        for k in cfg["enabled"]
        if cfg["enabled"][k] and cfg["schedule"][k]
    ]
    if enabled_schedules:
        hours = [s["hour"] for s in enabled_schedules]
        main_hour = max(set(hours), key=hours.count)
        cfg["main_schedule"] = next(
            s for s in enabled_schedules if s["hour"] == main_hour
        )
    else:
        cfg["main_schedule"] = None

    return cfg


# ---------------------------------------------------------------------------
# Sending + retry queue
# ---------------------------------------------------------------------------


def send_with_queue(
    report_dict: Dict[str, Any],
    api_domain: Optional[str] = None,
    queue_dir: str = QUEUE_DIR_DEFAULT,
    max_attempts: int = 3,
) -> bool:
    """POST the report. On failure, queue it for retry. Then flush the queue.

    Returns True if the current report was delivered successfully.
    """
    # ``api_domain`` was the legacy ApiRest base-url override. The generated
    # apiv4 client picks its target from the bundled service-token registry
    # via ``build_client(...)``, so the parameter is accepted-but-ignored
    # for backwards compatibility with the run.sh CLI surface.
    if api_domain:
        logger.debug("api_domain=%s ignored — generated client", api_domain)

    os.makedirs(queue_dir, exist_ok=True)

    delivered = _post_with_retries(report_dict, max_attempts)
    if not delivered:
        _enqueue(queue_dir, report_dict)

    # Try to flush anything queued from previous runs (best-effort).
    flush_queue(queue_dir, max_attempts=1)

    return delivered


def _post_with_retries(payload: Dict[str, Any], max_attempts: int) -> bool:
    """POST a single report via the generated apiv4 client with retries."""
    delay = 2.0
    for attempt in range(1, max_attempts + 1):
        try:
            body = _build_request_body(payload)
            with build_client("isard-backupninja") as client:
                resp = admin_backup_report.sync_detailed(client=client, body=body)
                raise_for_status(resp)
            logger.info("Backup report delivered (attempt %d)", attempt)
            return True
        except Exception as e:
            logger.warning(
                "Backup report POST failed (attempt %d/%d): %s",
                attempt,
                max_attempts,
                e,
            )
            if attempt < max_attempts:
                time.sleep(delay)
                delay *= 2
    return False


def _build_request_body(payload: Dict[str, Any]) -> BackupReportRequest:
    """Map the dict produced by the parser to the generated BackupReportRequest.

    Required fields go through the constructor; optional fields are set as
    attributes (the generated client exposes them as plain dataclass-style
    fields). The dict is consumed non-destructively so the queue retry
    flow can re-marshal an identical body on the next attempt.
    """
    body = BackupReportRequest(
        timestamp=payload["timestamp"],
        status=payload["status"],
        type_=payload["type"],
        scope=payload["scope"],
    )
    for key, value in payload.items():
        if key in ("timestamp", "status", "type", "scope"):
            continue
        # The generated dataclass uses ``type_`` to avoid the Python
        # builtin clash; re-route any stray "type" assignments accordingly.
        attr = "type_" if key == "type" else key
        setattr(body, attr, value)
    return body


def _enqueue(queue_dir: str, payload: Dict[str, Any]) -> None:
    name = f"report-{int(time.time())}-{os.getpid()}.json"
    path = os.path.join(queue_dir, name)
    try:
        with open(path, "w") as fh:
            json.dump(payload, fh)
        logger.info("Queued backup report for retry: %s", path)
    except OSError as e:
        logger.error("Failed to enqueue report %s: %s", path, e)


def flush_queue(queue_dir: str, max_attempts: int = 1) -> int:
    """Try to deliver every queued report. Returns the number sent."""
    if not os.path.isdir(queue_dir):
        return 0
    sent = 0
    for entry in sorted(os.listdir(queue_dir)):
        if not entry.endswith(".json"):
            continue
        path = os.path.join(queue_dir, entry)
        try:
            with open(path) as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Dropping unreadable queued report %s: %s", path, e)
            _safe_unlink(path)
            continue
        if _post_with_retries(payload, max_attempts):
            _safe_unlink(path)
            sent += 1
        else:
            # Stop at the first failure — avoid hammering the API when it's down.
            break
    if sent:
        logger.info("Flushed %d queued backup reports", sent)
    return sent


def _safe_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError as e:
        logger.warning("Could not delete %s: %s", path, e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[Iterable[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Parse BackupNinja logs and send a report to IsardVDI."
    )
    parser.add_argument("--log-path", default=LOG_PATH_DEFAULT)
    parser.add_argument("--api-domain", help="Override API_DOMAIN env var")
    parser.add_argument("--queue-dir", default=QUEUE_DIR_DEFAULT)
    parser.add_argument(
        "--max-attempts", type=int, default=3, help="HTTP retry attempts"
    )
    parser.add_argument(
        "--json", action="store_true", help="Print report as JSON and don't POST"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = BackupLogParser(args.log_path).parse()
    if not report:
        logger.info("No backup session available to report.")
        return 0

    payload = report.to_dict()

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return 0

    ok = send_with_queue(
        payload,
        api_domain=args.api_domain,
        queue_dir=args.queue_dir,
        max_attempts=args.max_attempts,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
