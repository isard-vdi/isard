# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin the LOGS_DELETE_BACKUP_DIR plumbing through
``AdminDomainsService._delete_logs_async``.

The destructive cron at 22:30 / 00:30 UTC deletes old session logs; the
env var (container path ``/backups`` per the apiv4 compose; host-overridable
via the matching ``LOGS_DELETE_BACKUP_DIR`` line in ``isardvdi.cfg``, default
``/opt/isard/backups``) opens a streaming JSONL.gz dump of every deleted row
so the operation is recoverable. The delete itself now runs as a paced,
index-bounded streamed loop (``LogsProcessed.delete_old_streamed``) instead of
materialising every id up front.
"""

import gzip
import json

import pytest
from fastapi import BackgroundTasks


@pytest.fixture
def patched_service(monkeypatch):
    """Stub the upstream `_common` calls + `notify_admins`. Return handles so
    each test can assert on the args the streamed delete saw and on the
    SocketIO payload notify_admins received.
    """
    from api.services.admin import domains as svc

    monkeypatch.setattr(
        svc.ApiAdmin,
        "get_old_entry_cutoff",
        classmethod(lambda cls, *a, **kw: "CUTOFF"),
    )
    monkeypatch.setattr(
        svc.LogsProcessed,
        "count_older",
        classmethod(lambda cls, *a, **kw: 3),
    )
    delete_calls = []

    def _fake_stream(table, cutoff, *, backup=None, **kw):
        # Simulate the real return_changes → write_rows order.
        if backup is not None:
            backup.write_rows([{"id": f"log-{i}"} for i in (1, 2, 3)])
        delete_calls.append({"table": table, "cutoff": cutoff, "backup": backup})
        return 3

    monkeypatch.setattr(
        svc.LogsProcessed,
        "delete_old_streamed",
        classmethod(lambda cls, *a, **kw: _fake_stream(*a, **kw)),
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
        assert payload["deleted"] == 3
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

        # delete_old_streamed ran with the BackupWriter passed in.
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
        # Nothing to delete → no file should be created (otherwise the daily
        # cron with no work to do leaves an empty .jsonl.gz cluttering the
        # bind mount).
        from api.services.admin import domains as svc

        monkeypatch.setattr(
            svc.LogsProcessed,
            "count_older",
            classmethod(lambda cls, *a, **kw: 0),
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
        # The streamed delete still ran (a cheap no-op when nothing matches),
        # with no backup arg.
        assert patched_service["delete_calls"][-1]["backup"] is None
