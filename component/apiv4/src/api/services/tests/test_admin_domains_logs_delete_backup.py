# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin the LOGS_DELETE_BACKUP_DIR plumbing through
``AdminDomainsService._delete_logs_async``.

The destructive cron at 22:30 / 00:30 UTC deletes a year of session
logs every day with no recovery path; the env var (container path
``/backups`` per the apiv4 compose; host-overridable via the
matching ``LOGS_DELETE_BACKUP_DIR`` line in ``isardvdi.cfg``,
default ``/opt/isard/backups``) opens a streaming JSONL.gz dump
BEFORE the delete fires so the operation is recoverable.
"""

import gzip
import json
from unittest.mock import MagicMock

import pytest
from fastapi import BackgroundTasks


@pytest.fixture
def patched_service(monkeypatch):
    """Stub the upstream `_common` calls + `notify_admins`. Return
    handles so each test can assert on the args delete_batch saw and
    on the SocketIO payload notify_admins received.
    """
    from api.services.admin import domains as svc

    monkeypatch.setattr(
        svc.ApiAdmin,
        "get_older_than_old_entry_max_time",
        staticmethod(lambda *args: ["log-1", "log-2", "log-3"]),
    )
    delete_calls = []

    def _fake_delete(table, ids, batch_size=50000, *, backup=None):
        # Simulate the real fetch + write_rows + delete order.
        if backup is not None:
            backup.write_rows([{"id": _id} for _id in ids])
        delete_calls.append({"table": table, "ids": ids, "backup": backup})

    monkeypatch.setattr(
        svc.LogsProcessed,
        "delete_batch",
        classmethod(lambda cls, *a, **kw: _fake_delete(*a, **kw)),
    )

    notify_payloads = []
    monkeypatch.setattr(
        svc,
        "notify_admins",
        lambda event, payload: notify_payloads.append((event, payload)),
    )
    return {
        "svc": svc,
        "delete_calls": delete_calls,
        "notify_payloads": notify_payloads,
    }


class TestDeleteLogsAsyncBackup:
    def test_no_backup_when_env_unset(self, monkeypatch, patched_service):
        monkeypatch.delenv("LOGS_DELETE_BACKUP_DIR", raising=False)
        bg = BackgroundTasks()
        count = patched_service["svc"].AdminDomainsService._delete_logs_async(
            "logs_desktops", "logs_desktops_action", bg
        )
        assert count == 3
        # Run the queued task synchronously (FastAPI does this after the
        # response in production; the test runs it directly).
        for task in bg.tasks:
            task.func(*task.args, **task.kwargs)
        assert patched_service["delete_calls"][0]["backup"] is None
        event, payload = patched_service["notify_payloads"][-1]
        assert event == "logs_desktops_action"
        assert payload["status"] == "completed"
        assert "backup_path" not in payload  # no backup → no path field

    def test_backup_writes_jsonl_gz_when_env_set(
        self, monkeypatch, patched_service, tmp_path
    ):
        monkeypatch.setenv("LOGS_DELETE_BACKUP_DIR", str(tmp_path))
        bg = BackgroundTasks()
        count = patched_service["svc"].AdminDomainsService._delete_logs_async(
            "logs_desktops", "logs_desktops_action", bg
        )
        assert count == 3
        for task in bg.tasks:
            task.func(*task.args, **task.kwargs)

        # delete_batch ran with the BackupWriter passed in.
        assert patched_service["delete_calls"][0]["backup"] is not None

        # Backup file exists, is gzipped JSONL, and contains the row ids.
        backups = list(tmp_path.iterdir())
        assert len(backups) == 1
        assert backups[0].name.startswith("logs_desktops_delete_")
        assert backups[0].name.endswith(".jsonl.gz")
        with gzip.open(backups[0], "rt", encoding="utf-8") as fh:
            ids = [json.loads(line)["id"] for line in fh.read().strip().split("\n")]
        assert ids == ["log-1", "log-2", "log-3"]

        # SocketIO payload carries the backup_path for the UI toast.
        event, payload = patched_service["notify_payloads"][-1]
        assert event == "logs_desktops_action"
        assert payload["status"] == "completed"
        assert payload["backup_path"] == str(backups[0])

    def test_empty_old_logs_skips_backup_creation(
        self, monkeypatch, patched_service, tmp_path
    ):
        # No old logs → no file should be created (otherwise the
        # daily cron with no work to do leaves an empty .jsonl.gz
        # cluttering the bind mount).
        from api.services.admin import domains as svc

        monkeypatch.setattr(
            svc.ApiAdmin,
            "get_older_than_old_entry_max_time",
            staticmethod(lambda *args: []),
        )
        monkeypatch.setenv("LOGS_DELETE_BACKUP_DIR", str(tmp_path))
        bg = BackgroundTasks()
        count = svc.AdminDomainsService._delete_logs_async(
            "logs_users", "logs_users_action", bg
        )
        assert count == 0
        for task in bg.tasks:
            task.func(*task.args, **task.kwargs)
        assert list(tmp_path.iterdir()) == []  # no backup file written
        # delete_batch still ran (with empty ids), no backup arg.
        assert patched_service["delete_calls"][-1]["ids"] == []
        assert patched_service["delete_calls"][-1]["backup"] is None
