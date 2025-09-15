#!/usr/bin/env python3
"""
BackupNinja Report Sender
A standalone script to parse backup execution logs and send JSON reports to IsardVDI API

This script provides parsing of BackupNinja backup logs and sends detailed reports
to the IsardVDI API at /api/v3/backups when backups are finished.
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from isardvdi_common.api_rest import ApiRest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BackupAction:
    """Represents a single backup action"""

    name: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: str = "UNKNOWN"
    duration: Optional[float] = None
    messages: List[str] = field(default_factory=list)


@dataclass
class BackupReport:
    """Complete backup report"""

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

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        # Use parsed backup type if available, otherwise fall back to environment variable
        if self.backup_type:
            backup_type = self.backup_type
        else:
            backup_type = os.getenv("BACKUP_TYPE", "automated")
            if backup_type not in ["automated", "manual"]:
                backup_type = "automated"  # Default fallback

        # Determine scope - use parsed scope if available, otherwise default to full
        scope = self.backup_scope if self.backup_scope else "full"

        result = {
            "timestamp": int(self.timestamp.timestamp()),  # Convert to Unix timestamp
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
            "duration": self.get_total_duration(),
        }

        # Add backup type summary if available
        if self.backup_type_summary:
            result["backup_types"] = self.backup_type_summary

        # Add filesystem metrics if available
        if self.filesystem_metrics:
            result["filesystem_metrics"] = self.filesystem_metrics

        return result

    def get_total_duration(self) -> Optional[int]:
        """Calculate total duration of all backup actions"""
        if not self.actions:
            return None

        total_duration = 0
        for action in self.actions:
            if action.get("duration"):
                total_duration += action["duration"]

        return int(total_duration) if total_duration > 0 else None


class BackupLogParser:
    """Parser for BackupNinja log files"""

    def __init__(self, log_path: str = "/var/log/backupninja.log"):
        self.log_path = log_path

    def get_recent_logs(self, lines: int = 1000) -> List[str]:
        """Get recent log lines"""
        try:
            with open(self.log_path, "r") as f:
                all_lines = f.readlines()

            # Get the last N lines
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return [line.strip() for line in recent_lines]
        except Exception as e:
            logger.error(f"Error reading log file: {e}")
            return []

    def find_last_completed_backup(self, log_lines: List[str]) -> List[str]:
        """Find the most recent completed backup session using session markers"""
        # Find the last BACKUP_SESSION_END marker
        session_end_index = -1
        for i in range(len(log_lines) - 1, -1, -1):
            if "BACKUP_SESSION_END:" in log_lines[i]:
                session_end_index = i
                break

        if session_end_index == -1:
            # No completed backup session found, fall back to old method
            logger.info("No BACKUP_SESSION_END marker found, using fallback method")
            return self._find_last_completed_backup_fallback(log_lines)

        # Find the corresponding BACKUP_SESSION_START marker
        session_start_index = -1
        for i in range(session_end_index - 1, -1, -1):
            if "BACKUP_SESSION_START:" in log_lines[i]:
                session_start_index = i
                break

        if session_start_index == -1:
            # No start marker found, fall back to old method
            logger.info("No BACKUP_SESSION_START marker found, using fallback method")
            return self._find_last_completed_backup_fallback(log_lines)

        # Extract lines between start and end markers (inclusive)
        session_lines = log_lines[session_start_index : session_end_index + 1]

        logger.info(
            f"Found backup session with {len(session_lines)} log lines between markers"
        )
        return session_lines

    def _find_last_completed_backup_fallback(self, log_lines: List[str]) -> List[str]:
        """Fallback method for finding completed backup session (original implementation)"""
        # Find the last FINISHED line
        finished_index = -1
        for i in range(len(log_lines) - 1, -1, -1):
            if "FINISHED:" in log_lines[i]:
                finished_index = i
                break

        if finished_index == -1:
            # No completed backup found
            return []

        # Find the start of this backup session
        # Look backwards for the first action that doesn't belong to this session
        session_lines = []
        current_date = None

        for i in range(finished_index, -1, -1):
            line = log_lines[i]

            # Extract date from line
            date_match = re.match(r"(\w{3} \d{2})", line)
            if date_match:
                line_date = date_match.group(1)
                if current_date is None:
                    current_date = line_date
                elif line_date != current_date:
                    # We've gone back to a previous day, stop here
                    break

            # If this is a "starting action" from a different date, stop
            if "starting action" in line and current_date and date_match:
                line_date = date_match.group(1)
                if line_date != current_date:
                    break

            session_lines.insert(0, line)

        return session_lines

    def parse_backup_actions(self, log_lines: List[str]) -> List[BackupAction]:
        """Parse backup actions from log lines with enhanced borg statistics"""
        actions = []
        current_action = None

        for line in log_lines:
            # Starting action
            if ">>>> starting action" in line:
                match = re.search(r"starting action ([^\s]+)", line)
                if match:
                    action_name = match.group(1)
                    timestamp_match = re.match(r"(\w{3} \d{2} \d{2}:\d{2}:\d{2})", line)
                    timestamp = None
                    if timestamp_match:
                        timestamp = datetime.strptime(
                            timestamp_match.group(1), "%b %d %H:%M:%S"
                        ).replace(year=datetime.now().year)

                    current_action = BackupAction(
                        name=action_name, start_time=timestamp, status="RUNNING"
                    )

            # Finished action
            elif "<<<< finished action" in line:
                match = re.search(r"finished action ([^:]+): (\w+)", line)
                if match and current_action:
                    action_name = match.group(1)
                    status = match.group(2)
                    current_action.status = status

                    timestamp_match = re.match(r"(\w{3} \d{2} \d{2}:\d{2}:\d{2})", line)
                    if timestamp_match:
                        end_time = datetime.strptime(
                            timestamp_match.group(1), "%b %d %H:%M:%S"
                        ).replace(year=datetime.now().year)
                        current_action.end_time = end_time
                        if current_action.start_time:
                            current_action.duration = (
                                end_time - current_action.start_time
                            ).total_seconds()

                    actions.append(current_action)
                    current_action = None

            # Warning or error messages
            elif current_action and (
                "Warning:" in line or "Error:" in line or "Fatal:" in line
            ):
                current_action.messages.append(line)

        # Parse borg statistics and compact results for actions
        self._parse_borg_statistics(log_lines, actions)
        self._parse_compact_results(log_lines, actions)
        return actions

    def _collect_filesystem_metrics(self) -> Dict[str, Any]:
        """Collect filesystem usage metrics"""
        import re
        import subprocess

        logger.info("=== STARTING FILESYSTEM METRICS COLLECTION ===")
        filesystem_metrics = {}

        try:
            # Get filesystem usage with df -h
            df_result = subprocess.run(
                ["df", "-h"], capture_output=True, text=True, timeout=10
            )
            if df_result.returncode == 0:
                filesystem_usage = {}
                for line in df_result.stdout.strip().split("\n")[1:]:  # Skip header
                    parts = line.split()
                    if len(parts) >= 6:
                        filesystem = parts[0]
                        size = parts[1]
                        used = parts[2]
                        avail = parts[3]
                        use_pct = int(parts[4].replace("%", ""))
                        mount = parts[5]

                        # Identify key mounts
                        if mount == "/backup":
                            filesystem_usage["backup_storage"] = {
                                "device": filesystem,
                                "size": size,
                                "used": used,
                                "available": avail,
                                "usage_percent": use_pct,
                                "mount_point": mount,
                            }
                        elif "raid" in filesystem.lower() or mount.startswith("/opt"):
                            filesystem_usage["source_storage"] = {
                                "device": filesystem,
                                "size": size,
                                "used": used,
                                "available": avail,
                                "usage_percent": use_pct,
                                "mount_point": mount,
                            }

                filesystem_metrics["usage"] = filesystem_usage
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, Exception) as e:
            logger.warning(f"Failed to collect filesystem usage: {e}")

        try:
            # Get backup repository sizes with du -sh /backup/*
            du_backup_result = subprocess.run(
                ["du", "-sh", "/backup/*"],
                capture_output=True,
                text=True,
                timeout=10,
                shell=True,
            )
            if du_backup_result.returncode == 0:
                backup_sizes = {}
                for line in du_backup_result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            size = parts[0]
                            path = parts[1]
                            backup_type = path.split("/")[-1]
                            if backup_type not in ["extract"]:  # Skip extract directory
                                backup_sizes[backup_type] = size

                filesystem_metrics["backup_sizes"] = backup_sizes
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, Exception) as e:
            logger.warning(f"Failed to collect backup sizes: {e}")

        try:
            # Get source data sizes with du -sh /opt/isard/*
            du_source_result = subprocess.run(
                ["du", "-sh", "/opt/isard/*"],
                capture_output=True,
                text=True,
                timeout=10,
                shell=True,
            )
            if du_source_result.returncode == 0:
                source_sizes = {}
                for line in du_source_result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            size = parts[0]
                            path = parts[1]
                            source_type = path.split("/")[-1]
                            # Only include non-zero sizes
                            if size not in ["0", "4.0K"]:
                                source_sizes[source_type] = size

                filesystem_metrics["source_sizes"] = source_sizes
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, Exception) as e:
            logger.warning(f"Failed to collect source sizes: {e}")

        # Collect borg repository statistics
        # Note: This runs in the backup environment context where borg may not be accessible
        # The primary data should come from parsing borg output in backup logs
        try:
            backup_repo_stats = {}
            backup_base_path = "/backup"
            logger.info(
                f"Starting borg repository stats collection from {backup_base_path}"
            )

            # Set up environment for borg commands (copy from backup environment)
            borg_env = os.environ.copy()
            borg_env.update(
                {
                    "BORG_PASSPHRASE": "",  # Since encryption is set to 'none' in configs
                    "BORG_RELOCATED_REPO_ACCESS_IS_OK": "yes",
                    "BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK": "yes",
                }
            )

            if os.path.exists(backup_base_path):
                for repo_name in os.listdir(backup_base_path):
                    repo_path = os.path.join(backup_base_path, repo_name)
                    if os.path.isdir(repo_path) and repo_name not in ["extract"]:
                        try:
                            # Try to get borg info for this repository with proper environment
                            borg_info_result = subprocess.run(
                                ["borg", "info", repo_path, "--json"],
                                capture_output=True,
                                text=True,
                                timeout=15,
                                env=borg_env,
                            )
                            if borg_info_result.returncode == 0:
                                borg_info = json.loads(borg_info_result.stdout)
                                if "repository" in borg_info:
                                    backup_repo_stats[repo_name] = {
                                        "repository_id": borg_info["repository"].get(
                                            "id", "N/A"
                                        )[:16],
                                        "location": borg_info["repository"].get(
                                            "location", repo_path
                                        ),
                                    }

                                # Get list of archives to find the most recent one
                                borg_list_result = subprocess.run(
                                    ["borg", "list", repo_path, "--json"],
                                    capture_output=True,
                                    text=True,
                                    timeout=15,
                                    env=borg_env,
                                )
                                if borg_list_result.returncode == 0:
                                    archives_data = json.loads(borg_list_result.stdout)
                                    if (
                                        "archives" in archives_data
                                        and archives_data["archives"]
                                    ):
                                        # Find the most recent archive (should be the one just created)
                                        latest_archive = archives_data["archives"][-1]
                                        archive_name = latest_archive.get("name")

                                        # Get detailed statistics for the latest archive
                                        borg_info_archive_result = subprocess.run(
                                            [
                                                "borg",
                                                "info",
                                                f"{repo_path}::{archive_name}",
                                                "--json",
                                            ],
                                            capture_output=True,
                                            text=True,
                                            timeout=20,
                                            env=borg_env,
                                        )

                                        if borg_info_archive_result.returncode == 0:
                                            archive_info = json.loads(
                                                borg_info_archive_result.stdout
                                            )
                                            if (
                                                "archives" in archive_info
                                                and archive_info["archives"]
                                            ):
                                                archive_details = archive_info[
                                                    "archives"
                                                ][0]
                                                backup_repo_stats[repo_name][
                                                    "latest_archive"
                                                ] = {
                                                    "name": archive_name,
                                                    "start": archive_details.get(
                                                        "start", "N/A"
                                                    ),
                                                    "end": archive_details.get(
                                                        "end", "N/A"
                                                    ),
                                                    "duration": archive_details.get(
                                                        "duration", 0
                                                    ),
                                                    "stats": archive_details.get(
                                                        "stats", {}
                                                    ),
                                                }
                                                logger.debug(
                                                    f"Found detailed stats for {repo_name}::{archive_name}"
                                                )
                                            else:
                                                # Fallback to basic archive info without detailed stats
                                                backup_repo_stats[repo_name][
                                                    "latest_archive"
                                                ] = {
                                                    "name": archive_name,
                                                    "start": latest_archive.get(
                                                        "start", "N/A"
                                                    ),
                                                    "stats": {},
                                                }
                                        else:
                                            # Fallback if detailed info fails
                                            backup_repo_stats[repo_name][
                                                "latest_archive"
                                            ] = {
                                                "name": archive_name,
                                                "start": latest_archive.get(
                                                    "start", "N/A"
                                                ),
                                                "stats": {},
                                            }
                                            logger.debug(
                                                f"Could not get archive details for {repo_name}::{archive_name}: {borg_info_archive_result.stderr}"
                                            )
                                else:
                                    logger.debug(
                                        f"Could not list archives for {repo_name}: {borg_list_result.stderr}"
                                    )
                            else:
                                logger.debug(
                                    f"Could not get info for {repo_name}: {borg_info_result.stderr}"
                                )
                        except (
                            subprocess.SubprocessError,
                            json.JSONDecodeError,
                            Exception,
                        ) as e:
                            logger.debug(f"Could not access borg repo {repo_name}: {e}")
                            continue

                if backup_repo_stats:
                    filesystem_metrics["borg_repositories"] = backup_repo_stats
                    logger.info(
                        f"Collected borg stats for {len(backup_repo_stats)} repositories"
                    )
                else:
                    logger.warning("No borg repository statistics could be collected")
        except Exception as e:
            logger.error(f"Failed to collect borg repository stats: {e}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")

        return filesystem_metrics

    def _parse_structured_borg_statistics(
        self, log_lines: List[str], actions: List[BackupAction]
    ) -> None:
        """Parse structured borg statistics from our stats scripts"""
        for line in log_lines:
            # Look for structured borg statistics JSON output
            if "BORG_STATS_" in line and "STATS_JSON:" in line:
                try:
                    # Extract the backup type from the log prefix
                    backup_type_match = re.search(r"BORG_STATS_(\w+):", line)
                    if not backup_type_match:
                        continue

                    backup_type = backup_type_match.group(1).lower()

                    # Extract the JSON stats
                    json_match = re.search(r"STATS_JSON: (.+)$", line)
                    if not json_match:
                        continue

                    stats_json = json_match.group(1)
                    stats_data = json.loads(stats_json)

                    # Create borg statistics structure
                    stats_dict = stats_data.get("stats", {})
                    borg_stats = {
                        "repository": f"/backup/{backup_type}",
                        "backup_type": backup_type,
                        "file_count": stats_dict.get("nfiles"),
                        "original_size": self._format_bytes(
                            stats_dict.get("original_size", 0)
                        ),
                        "compressed_size": self._format_bytes(
                            stats_dict.get("compressed_size", 0)
                        ),
                        "deduplicated_size": self._format_bytes(
                            stats_dict.get("deduplicated_size", 0)
                        ),
                        "original_size_bytes": stats_dict.get("original_size", 0),
                        "compressed_size_bytes": stats_dict.get("compressed_size", 0),
                        "deduplicated_size_bytes": stats_dict.get(
                            "deduplicated_size", 0
                        ),
                    }

                    # Find the corresponding borg action to attach the statistics
                    for action in actions:
                        action_basename = (
                            action.name.split("/")[-1].lower()
                            if "/" in action.name
                            else action.name.lower()
                        )
                        if (
                            backup_type in action_basename
                            and "borg.borg" in action_basename
                            and not hasattr(action, "borg_statistics")
                        ):
                            action.borg_statistics = borg_stats
                            logger.info(f"Attached borg statistics to {action.name}")
                            break

                except (json.JSONDecodeError, KeyError, AttributeError, Exception) as e:
                    logger.warning(f"Failed to parse borg statistics from line: {e}")
                    continue

    def _parse_native_borg_statistics(
        self, log_lines: List[str], actions: List[BackupAction]
    ) -> None:
        """Parse borg statistics from native borg create --stats output"""
        i = 0
        while i < len(log_lines):
            line = log_lines[i]

            # Look for borg repository statistics block (starts with "Repository:")
            if "Repository: /backup/" in line:
                try:
                    # Extract repository path and backup type
                    repo_match = re.search(r"Repository: (/backup/(\w+))", line)
                    if not repo_match:
                        i += 1
                        continue

                    repository = repo_match.group(1)
                    backup_type = repo_match.group(2)

                    # Look for the archive name in the next few lines
                    archive_name = None
                    for j in range(i + 1, min(i + 5, len(log_lines))):
                        if "Archive name:" in log_lines[j]:
                            archive_match = re.search(
                                r"Archive name: (.+)$", log_lines[j]
                            )
                            if archive_match:
                                archive_name = archive_match.group(1).strip()
                                break

                    # Look for the statistics section in the following lines
                    stats_found = False
                    for j in range(i + 1, min(i + 20, len(log_lines))):
                        stats_line = log_lines[j]

                        # Look for lines like "This archive: 5.37 kB 2.42 kB 2.42 kB"
                        archive_stats_match = re.search(
                            r"This archive:\s+([0-9.]+\s*[KMG]?B)\s+([0-9.]+\s*[KMG]?B)\s+([0-9.]+\s*[KMG]?B)",
                            stats_line,
                        )

                        if archive_stats_match:
                            original_size = archive_stats_match.group(1)
                            compressed_size = archive_stats_match.group(2)
                            deduplicated_size = archive_stats_match.group(3)

                            # Look for file count in nearby lines
                            file_count = None
                            for k in range(max(0, j - 10), min(j + 5, len(log_lines))):
                                file_match = re.search(
                                    r"Number of files:\s+(\d+)", log_lines[k]
                                )
                                if file_match:
                                    file_count = int(file_match.group(1))
                                    break

                            # Create borg statistics structure
                            borg_stats = {
                                "repository": repository,
                                "backup_type": backup_type,
                                "archive_name": archive_name,
                                "file_count": file_count,
                                "original_size": original_size,
                                "compressed_size": compressed_size,
                                "deduplicated_size": deduplicated_size,
                            }

                            # Find the corresponding borg action to attach the statistics
                            for action in actions:
                                if (
                                    backup_type in action.name.lower()
                                    and "borg" in action.name.lower()
                                    and not hasattr(action, "borg_statistics")
                                ):
                                    action.borg_statistics = borg_stats
                                    logger.info(
                                        f"Attached native borg statistics to {action.name}"
                                    )
                                    break

                            stats_found = True
                            break

                    if stats_found:
                        i = j + 1  # Skip past the statistics block
                    else:
                        i += 1

                except Exception as e:
                    logger.warning(f"Failed to parse native borg statistics: {e}")
                    i += 1
            else:
                i += 1

    def _collect_basic_filesystem_metrics(self) -> Dict[str, Any]:
        """Collect basic filesystem usage metrics"""
        import subprocess

        filesystem_metrics = {}

        try:
            # Get basic filesystem usage with df -h
            df_result = subprocess.run(
                ["df", "-h"], capture_output=True, text=True, timeout=10
            )
            if df_result.returncode == 0:
                filesystem_usage = {}
                for line in df_result.stdout.strip().split("\n")[1:]:  # Skip header
                    parts = line.split()
                    if len(parts) >= 6:
                        filesystem = parts[0]
                        size = parts[1]
                        used = parts[2]
                        avail = parts[3]
                        use_pct = int(parts[4].replace("%", ""))
                        mount = parts[5]

                        # Identify key mounts
                        if mount == "/backup":
                            filesystem_usage["backup_storage"] = {
                                "device": filesystem,
                                "size": size,
                                "used": used,
                                "available": avail,
                                "usage_percent": use_pct,
                                "mount_point": mount,
                            }

                if filesystem_usage:
                    filesystem_metrics["usage"] = filesystem_usage
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, Exception) as e:
            logger.warning(f"Failed to collect filesystem usage: {e}")

        return filesystem_metrics

    def _parse_borg_statistics(
        self, log_lines: List[str], actions: List[BackupAction]
    ) -> None:
        """Parse borg repository statistics and attach to relevant actions"""
        # First, try to parse structured borg statistics from our stats scripts
        self._parse_structured_borg_statistics(log_lines, actions)

        # Parse native borg statistics from borg create --stats output
        self._parse_native_borg_statistics(log_lines, actions)

        # Then try original parsing method as fallback
        i = 0
        while i < len(log_lines):
            line = log_lines[i]

            # Look for repository statistics block
            if "Repository:" in line and "/backup/" in line:
                repo_match = re.search(r"Repository: (/backup/(\w+))", line)
                if repo_match:
                    repository = repo_match.group(1)
                    backup_type = repo_match.group(2)

                    # Parse the statistics block
                    stats = {"repository": repository, "backup_type": backup_type}
                    j = i + 1

                    # Look for statistics in following lines
                    while j < len(log_lines) and j < i + 20:  # Reasonable limit
                        stat_line = log_lines[j]

                        if "Archive name:" in stat_line:
                            archive_match = re.search(r"Archive name: (.+)", stat_line)
                            if archive_match:
                                stats["archive_name"] = archive_match.group(1)

                        elif "Archive fingerprint:" in stat_line:
                            fingerprint_match = re.search(
                                r"Archive fingerprint: (.+)", stat_line
                            )
                            if fingerprint_match:
                                stats["fingerprint"] = fingerprint_match.group(1)

                        elif "Duration:" in stat_line:
                            duration_match = re.search(r"Duration: (.+)", stat_line)
                            if duration_match:
                                stats["duration_text"] = duration_match.group(1)

                        elif "Number of files:" in stat_line:
                            files_match = re.search(
                                r"Number of files: (\d+)", stat_line
                            )
                            if files_match:
                                stats["file_count"] = int(files_match.group(1))

                        elif "This archive:" in stat_line:
                            size_match = re.search(
                                r"This archive:\s+([0-9.]+\s+\w+)\s+([0-9.]+\s+\w+)\s+([0-9.]+\s+\w+)",
                                stat_line,
                            )
                            if size_match:
                                stats["original_size"] = size_match.group(1)
                                stats["compressed_size"] = size_match.group(2)
                                stats["deduplicated_size"] = size_match.group(3)

                        elif "All archives:" in stat_line:
                            size_match = re.search(
                                r"All archives:\s+([0-9.]+\s+\w+)\s+([0-9.]+\s+\w+)\s+([0-9.]+\s+\w+)",
                                stat_line,
                            )
                            if size_match:
                                stats["total_original"] = size_match.group(1)
                                stats["total_compressed"] = size_match.group(2)
                                stats["total_deduplicated"] = size_match.group(3)

                        elif "Chunk index:" in stat_line:
                            chunk_match = re.search(
                                r"Chunk index:\s+(\d+)\s+(\d+)", stat_line
                            )
                            if chunk_match:
                                stats["unique_chunks"] = int(chunk_match.group(1))
                                stats["total_chunks"] = int(chunk_match.group(2))

                        # End of statistics block
                        elif "----------" in stat_line and len(stats) > 2:
                            break

                        j += 1

                    # Find the corresponding borg action and attach statistics
                    for action in actions:
                        if (
                            f"/{backup_type}-borg.borg" in action.name
                            or f"{backup_type}-borg.borg" in action.name
                        ):
                            if not hasattr(action, "borg_statistics"):
                                action.borg_statistics = stats
                                break

                    i = j  # Skip ahead
                    continue

            i += 1

    def _parse_compact_results(
        self, log_lines: List[str], actions: List[BackupAction]
    ) -> None:
        """Parse compact operation results and attach to relevant actions"""
        for i, line in enumerate(log_lines):
            # Look for compact operation results
            if (
                "compact succeeded" in line.lower()
                or "compaction completed" in line.lower()
            ):
                # Extract any metrics from compact operations
                compact_info = {
                    "operation": "compact",
                    "status": "success",
                    "message": line,
                }

                # Find the corresponding compact action
                for action in actions:
                    if "compact" in action.name.lower() and not hasattr(
                        action, "compact_results"
                    ):
                        action.compact_results = compact_info
                        break

            elif (
                "compact failed" in line.lower() or "compaction failed" in line.lower()
            ):
                compact_info = {
                    "operation": "compact",
                    "status": "failed",
                    "message": line,
                }

                # Find the corresponding compact action
                for action in actions:
                    if "compact" in action.name.lower() and not hasattr(
                        action, "compact_results"
                    ):
                        action.compact_results = compact_info
                        break

    def _categorize_actions_by_type(
        self, actions: List[BackupAction]
    ) -> Dict[str, List[BackupAction]]:
        """Categorize actions by backup type for detailed reporting"""
        categories = {"db": [], "redis": [], "stats": [], "config": [], "disks": []}

        for action in actions:
            # Extract backup type from action name
            action_match = re.search(r"(\d+)-(\w+)-", action.name)
            if action_match:
                backup_type = action_match.group(2)
                if backup_type in categories:
                    categories[backup_type].append(action)

        return categories

    def _generate_backup_type_summary(
        self,
        actions_by_type: Dict[str, List[BackupAction]],
        filesystem_metrics: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Generate summary statistics for each backup type"""
        type_summary = {}

        for backup_type, type_actions in actions_by_type.items():
            if not type_actions:
                continue

            summary = {
                "total_actions": len(type_actions),
                "successful": sum(1 for a in type_actions if a.status == "SUCCESS"),
                "warnings": sum(1 for a in type_actions if a.status == "WARNING"),
                "errors": sum(1 for a in type_actions if a.status == "ERROR"),
                "total_duration": sum(a.duration or 0 for a in type_actions),
                "actions": [],
            }

            # Add borg statistics summary for this backup type
            borg_stats = None

            # First try to get from individual actions
            for action in type_actions:
                if hasattr(action, "borg_statistics") and action.borg_statistics:
                    borg_stats = action.borg_statistics
                    break

            # If not found in actions, try to get from filesystem metrics borg repositories
            if (
                not borg_stats
                and filesystem_metrics
                and "borg_repositories" in filesystem_metrics
            ):
                repo_data = filesystem_metrics["borg_repositories"].get(backup_type)
                if repo_data and "latest_archive" in repo_data:
                    archive_stats = repo_data["latest_archive"].get("stats", {})
                    if archive_stats:
                        borg_stats = {
                            "repository": repo_data.get("location"),
                            "archive_name": repo_data["latest_archive"].get("name"),
                            "file_count": archive_stats.get("nfiles"),
                            "original_size": self._format_bytes(
                                archive_stats.get("original_size", 0)
                            ),
                            "compressed_size": self._format_bytes(
                                archive_stats.get("compressed_size", 0)
                            ),
                            "deduplicated_size": self._format_bytes(
                                archive_stats.get("deduplicated_size", 0)
                            ),
                            "unique_chunks": archive_stats.get("nunique_chunks"),
                            "total_chunks": archive_stats.get("nfiles"),
                        }

            if borg_stats:
                summary["borg_statistics"] = borg_stats

            # Add action details
            for action in type_actions:
                action_info = {
                    "name": (
                        action.name.split("/")[-1]
                        if "/" in action.name
                        else action.name
                    ),
                    "status": action.status,
                    "duration": action.duration,
                }
                summary["actions"].append(action_info)

            type_summary[backup_type] = summary

        return type_summary

    def _format_bytes(self, bytes_value):
        """Format bytes value to human readable string"""
        if not bytes_value or bytes_value == 0:
            return "0 B"

        for unit in ["B", "K", "M", "G", "T"]:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} P"

    def parse_finished_summary(self, log_lines: List[str]) -> Optional[Dict[str, Any]]:
        """Parse the FINISHED summary line and extract session info"""
        finished_summary = None
        session_info = None

        # Look for FINISHED summary
        for line in log_lines:
            if "FINISHED:" in line:
                finished_pattern = (
                    r"(?P<timestamp>\w{3} \d{2} \d{2}:\d{2}:\d{2}) Info: FINISHED: "
                    r"(?P<actions>\d+) actions run. "
                    r"(?P<fatal>\d+) fatal. "
                    r"(?P<error>\d+) error. "
                    r"(?P<warning>\d+) warning."
                )
                match = re.match(finished_pattern, line)
                if match:
                    log_dict = match.groupdict()
                    timestamp = datetime.strptime(
                        log_dict["timestamp"], "%b %d %H:%M:%S"
                    ).replace(year=datetime.now().year)

                    finished_summary = {
                        "timestamp": timestamp,
                        "total_actions": int(log_dict["actions"]),
                        "fatal": int(log_dict["fatal"]),
                        "error": int(log_dict["error"]),
                        "warning": int(log_dict["warning"]),
                    }
                    break

        # Look for session markers to extract backup type and additional info
        for line in log_lines:
            if "BACKUP_SESSION_START:" in line:
                session_pattern = (
                    r"(?P<timestamp>\w{3} \d{2} \d{2}:\d{2}:\d{2}) Info: BACKUP_SESSION_START: "
                    r"(?P<type>\w+)\s+(?P<scope>.*?)\s+backup.*"
                )
                match = re.match(session_pattern, line)
                if match:
                    session_dict = match.groupdict()
                    session_info = {
                        "backup_type": session_dict["type"],  # manual or automated
                        "backup_scope": session_dict[
                            "scope"
                        ],  # specific backup type or "all"
                    }
                    break

        # Look for disk types information (only relevant for disks backups)
        disk_types = None
        for line in log_lines:
            if "BACKUP_DISK_TYPES:" in line:
                disk_types_match = re.search(r"BACKUP_DISK_TYPES:(.+)$", line)
                if disk_types_match:
                    types_str = disk_types_match.group(1).strip()
                    if types_str:
                        disk_types = types_str.split()
                    break

        # Combine finished summary with session info and disk types
        if finished_summary:
            if session_info:
                finished_summary.update(session_info)
            if disk_types:
                finished_summary["disk_types"] = disk_types
            return finished_summary

        # If no FINISHED line but we have session info, create minimal summary
        if session_info:
            # Use session end timestamp if available
            for line in reversed(log_lines):
                if "BACKUP_SESSION_END:" in line:
                    timestamp_match = re.match(r"(\w{3} \d{2} \d{2}:\d{2}:\d{2})", line)
                    if timestamp_match:
                        timestamp = datetime.strptime(
                            timestamp_match.group(1), "%b %d %H:%M:%S"
                        ).replace(year=datetime.now().year)
                        session_info["timestamp"] = timestamp
                        break

            if disk_types:
                session_info["disk_types"] = disk_types

            return session_info

        return None

    def analyze_backup_types_status(
        self, actions: List[BackupAction]
    ) -> Dict[str, str]:
        """Analyze actions to determine the status of each backup type"""
        backup_types_status = {}

        # Initialize all backup types as not included
        all_backup_types = ["db", "redis", "stats", "config", "disks"]
        for backup_type in all_backup_types:
            backup_types_status[backup_type] = "not_included"

        # Analyze actions to determine which backup types were attempted and their results
        for action in actions:
            action_name = action.name.lower()
            backup_type = None

            # Determine which backup type this action belongs to
            if (
                "db" in action_name
                or "database" in action_name
                or "rethink" in action_name
            ):
                backup_type = "db"
            elif "redis" in action_name:
                backup_type = "redis"
            elif (
                "stats" in action_name
                or "prometheus" in action_name
                or "loki" in action_name
            ):
                backup_type = "stats"
            elif "config" in action_name:
                backup_type = "config"
            elif (
                "disk" in action_name
                or "template" in action_name
                or "group" in action_name
                or "media" in action_name
            ):
                backup_type = "disks"

            if backup_type:
                # Update status based on action result
                if action.status in ["ERROR", "FATAL", "FAILED"]:
                    backup_types_status[backup_type] = "failed"
                elif action.status in ["SUCCESS"]:
                    if backup_types_status[backup_type] not in ["failed"]:
                        backup_types_status[backup_type] = "success"
                else:  # WARNING or other status
                    if backup_types_status[backup_type] == "not_included":
                        backup_types_status[backup_type] = (
                            "success"  # Treat warnings as success
                        )

        return backup_types_status

    def generate_report(self) -> Optional[BackupReport]:
        """Generate complete backup report"""
        # Get recent logs and find the last completed backup
        recent_logs = self.get_recent_logs()
        backup_logs = self.find_last_completed_backup(recent_logs)

        if not backup_logs:
            logger.info("No completed backup found in recent logs")
            return None

        logger.info(f"Found {len(backup_logs)} log lines for backup session")

        # Parse actions
        actions = self.parse_backup_actions(backup_logs)
        finished_summary = self.parse_finished_summary(backup_logs)

        logger.info(
            f"Parsed {len(actions)} actions and finished_summary: {finished_summary is not None}"
        )

        # Collect basic filesystem metrics
        filesystem_metrics = self._collect_basic_filesystem_metrics()

        # Categorize actions by backup type for detailed reporting
        actions_by_type = self._categorize_actions_by_type(actions)
        backup_type_summary = self._generate_backup_type_summary(
            actions_by_type, filesystem_metrics
        )

        # Analyze backup types status for UI display
        backup_types_status = self.analyze_backup_types_status(actions)

        if finished_summary:
            # Use actual parsed actions count, not FINISHED summary which may only count backup types
            total_actions = len(actions)
            fatal_count = sum(1 for a in actions if a.status == "FATAL")
            error_count = sum(1 for a in actions if a.status in ["ERROR", "FAILED"])
            warning_count = sum(1 for a in actions if a.status == "WARNING")
            success_count = sum(1 for a in actions if a.status == "SUCCESS")

            # Determine overall status
            if fatal_count > 0:
                status = "CRITICAL"
                summary = f"Backup completed with {fatal_count} fatal errors"
            elif error_count > 0:
                status = "ERROR"
                summary = f"Backup completed with {error_count} errors"
            elif warning_count > 0:
                status = "WARNING"
                summary = f"Backup completed with {warning_count} warnings"
            else:
                status = "SUCCESS"
                summary = f"Backup completed successfully with {total_actions} actions"

            # Convert actions to dict format
            actions_dict = []
            for action in actions:
                action_dict = {
                    "name": action.name,
                    "status": action.status,
                    "duration": action.duration,
                    "messages": action.messages,
                }
                if action.start_time:
                    action_dict["start_time"] = action.start_time.isoformat()
                if action.end_time:
                    action_dict["end_time"] = action.end_time.isoformat()

                # Add borg statistics if available
                if hasattr(action, "borg_statistics") and action.borg_statistics:
                    action_dict["borg_statistics"] = action.borg_statistics

                # Add compact results if available
                if hasattr(action, "compact_results") and action.compact_results:
                    action_dict["compact_results"] = action.compact_results

                actions_dict.append(action_dict)

            return BackupReport(
                timestamp=finished_summary["timestamp"],
                status=status,
                total_actions=total_actions,
                successful_actions=success_count,
                failed_actions=error_count,
                warning_actions=warning_count,
                fatal_actions=fatal_count,
                actions=actions_dict,
                summary=summary,
                backup_type=finished_summary.get("backup_type"),
                backup_scope=finished_summary.get("backup_scope"),
                disk_types=finished_summary.get("disk_types"),
                backup_types_status=backup_types_status,
                backup_type_summary=backup_type_summary,
                filesystem_metrics=filesystem_metrics,
            )

        elif actions:
            # Fallback: count from parsed actions
            success_count = sum(1 for a in actions if a.status == "SUCCESS")
            warning_count = sum(1 for a in actions if a.status == "WARNING")
            error_count = sum(1 for a in actions if a.status in ["ERROR", "FAILED"])
            fatal_count = sum(1 for a in actions if a.status == "FATAL")

            total_actions = len(actions)

            # Determine overall status
            if fatal_count > 0:
                status = "CRITICAL"
                summary = f"Backup completed with {fatal_count} fatal errors"
            elif error_count > 0:
                status = "ERROR"
                summary = f"Backup completed with {error_count} errors"
            elif warning_count > 0:
                status = "WARNING"
                summary = f"Backup completed with {warning_count} warnings"
            else:
                status = "SUCCESS"
                summary = f"Backup completed successfully with {total_actions} actions"

            # Get timestamp from last action
            last_timestamp = datetime.now()
            for action in reversed(actions):
                if action.end_time:
                    last_timestamp = action.end_time
                    break
                elif action.start_time:
                    last_timestamp = action.start_time

            # Convert actions to dict format
            actions_dict = []
            for action in actions:
                action_dict = {
                    "name": action.name,
                    "status": action.status,
                    "duration": action.duration,
                    "messages": action.messages,
                }
                if action.start_time:
                    action_dict["start_time"] = action.start_time.isoformat()
                if action.end_time:
                    action_dict["end_time"] = action.end_time.isoformat()

                # Add borg statistics if available
                if hasattr(action, "borg_statistics") and action.borg_statistics:
                    action_dict["borg_statistics"] = action.borg_statistics

                # Add compact results if available
                if hasattr(action, "compact_results") and action.compact_results:
                    action_dict["compact_results"] = action.compact_results

                actions_dict.append(action_dict)

            return BackupReport(
                timestamp=last_timestamp,
                status=status,
                total_actions=total_actions,
                successful_actions=success_count,
                failed_actions=error_count,
                warning_actions=warning_count,
                fatal_actions=fatal_count,
                actions=actions_dict,
                summary=summary,
                backup_type=None,  # Will fall back to environment variable
                backup_scope=None,  # Will default to "full"
                disk_types=None,  # No disk types info available in fallback
                backup_types_status=backup_types_status,
                backup_type_summary=backup_type_summary,
                filesystem_metrics=filesystem_metrics,
            )

        else:
            logger.info("No backup actions found in today's logs")
            return None


# Script execution - called directly by backupninja
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Parse BackupNinja logs and send report to IsardVDI API"
    )
    parser.add_argument(
        "--log-path",
        default="/var/log/backupninja.log",
        help="Path to backupninja log file",
    )
    parser.add_argument(
        "--api-domain", help="Override API domain (defaults to API_DOMAIN env var)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON instead of sending to API",
    )

    args = parser.parse_args()

    # Use custom log path if specified
    log_parser = BackupLogParser(args.log_path)
    report = log_parser.generate_report()

    if not report:
        logger.info("No backup report generated")
        exit(0)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        # Send to API using ApiRest directly
        try:
            if args.api_domain and args.api_domain.startswith("http"):
                api = ApiRest(service="isard-api", base_url=args.api_domain)
            else:
                api = ApiRest(service="isard-api")

            result = api.post("/backups", data=report.to_dict())
            logger.info("Backup report sent successfully")
        except Exception as e:
            logger.error(f"Failed to send backup report: {e}")
            exit(1)
else:
    # Called as module (legacy behavior)
    log_parser = BackupLogParser()
    report = log_parser.generate_report()

    if not report:
        logger.info("No backup report generated")
        exit(0)

    # Send to API using ApiRest directly
    try:
        api = ApiRest(service="isard-api")
        result = api.post("/backups", data=report.to_dict())
        logger.info("Backup report sent successfully")
    except Exception as e:
        logger.error(f"Failed to send backup report: {e}")
        exit(1)
