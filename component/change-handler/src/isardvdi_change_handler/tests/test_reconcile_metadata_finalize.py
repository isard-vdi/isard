# SPDX-License-Identifier: AGPL-3.0-or-later

"""Reconcile safety net for metadata finalize.

A metadata chain whose real (storage) work settled but whose finalize never
applied (the result event was lost) is pending yet not live work — the reconcile
must treat it as healable so Pass 2 recovers it from the storage's own reality,
the metadata analogue of the legacy core-tombstone reap.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from rq.job import JobStatus

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _task(*, finalize, job_status, ended_delta_s, storage_deps=()):
    task = SimpleNamespace()
    task.job = MagicMock()
    task.job.meta = {"core_finalize": finalize}
    task.job.ended_at = NOW - timedelta(seconds=ended_delta_s)
    task.job_status = job_status
    task.dependents = list(storage_deps)
    return task


def _core_step():
    from isardvdi_common.models.task import CoreStep

    return CoreStep({"id": "x", "task": "storage_update", "status": None}, None, None)


def test_orphaned_when_terminal_unstamped_and_aged():
    from isardvdi_change_handler.streams import reconcile

    task = _task(
        finalize=[{"status": None, "core_finalize": []}],
        job_status=JobStatus.FINISHED,
        ended_delta_s=1000,  # > 900
    )
    assert reconcile._metadata_finalize_orphaned(task, NOW, 900) is True


def test_not_orphaned_when_finalize_stamped():
    from isardvdi_change_handler.streams import reconcile

    task = _task(
        finalize=[{"status": "finished", "core_finalize": []}],
        job_status=JobStatus.FINISHED,
        ended_delta_s=1000,
    )
    assert reconcile._metadata_finalize_orphaned(task, NOW, 900) is False


def test_not_orphaned_when_storage_work_still_running():
    from isardvdi_change_handler.streams import reconcile

    task = _task(
        finalize=[{"status": None, "core_finalize": []}],
        job_status=JobStatus.STARTED,
        ended_delta_s=1000,
    )
    assert reconcile._metadata_finalize_orphaned(task, NOW, 900) is False


def test_not_orphaned_when_not_yet_aged():
    from isardvdi_change_handler.streams import reconcile

    task = _task(
        finalize=[{"status": None, "core_finalize": []}],
        job_status=JobStatus.FINISHED,
        ended_delta_s=100,  # < 900, inside the redelivery envelope
    )
    assert reconcile._metadata_finalize_orphaned(task, NOW, 900) is False


def test_not_orphaned_for_legacy_chain_without_core_finalize():
    from isardvdi_change_handler.streams import reconcile

    task = _task(finalize=[], job_status=JobStatus.FINISHED, ended_delta_s=1000)
    task.job.meta = {}  # a legacy chain has no core_finalize
    assert reconcile._metadata_finalize_orphaned(task, NOW, 900) is False


def test_finalize_has_unstamped_walks_nested():
    from isardvdi_change_handler.streams import reconcile

    nested = [{"status": "finished", "core_finalize": [{"status": None}]}]
    assert reconcile._finalize_has_unstamped(nested) is True
    done = [{"status": "finished", "core_finalize": [{"status": "failed"}]}]
    assert reconcile._finalize_has_unstamped(done) is False
