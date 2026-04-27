# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_queues.py``."""

import pytest
from api.schemas.admin_queues import (
    AutoDeleteConfigResponse,
    AutoDeleteEnabledRequest,
    DeleteOldTasksRequest,
    DeleteOldTasksResult,
    QueueConsumerResponse,
    QueueJobsListResponse,
    QueueJobsResponse,
    QueueRegistriesRequest,
)
from pydantic import ValidationError


class TestQueueJobsResponse:
    def test_id_required(self):
        with pytest.raises(ValidationError):
            QueueJobsResponse()

    def test_status_counts_default_zero(self):
        """All status counters default to 0 — pin so the wire shape
        always carries an integer (not None)."""
        r = QueueJobsResponse(id="default")
        for field in (
            "queued",
            "started",
            "finished",
            "failed",
            "deferred",
            "scheduled",
            "canceled",
        ):
            assert getattr(r, field) == 0

    def test_round_trip(self):
        r = QueueJobsResponse(id="default", queued=3, finished=10)
        assert QueueJobsResponse(**r.model_dump()) == r


class TestQueueJobsListResponse:
    def test_queues_required(self):
        with pytest.raises(ValidationError):
            QueueJobsListResponse()

    def test_accepts_empty(self):
        assert QueueJobsListResponse(queues=[]).queues == []


class TestQueueConsumerResponse:
    def test_id_and_queue_required(self):
        with pytest.raises(ValidationError):
            QueueConsumerResponse()
        with pytest.raises(ValidationError):
            QueueConsumerResponse(id="w-1")

    def test_accepts_minimal(self):
        c = QueueConsumerResponse(id="w-1", queue="default")
        assert c.id == "w-1"
        assert c.priority is None
        assert c.subscribers is None

    def test_accepts_full(self):
        c = QueueConsumerResponse(
            id="w-1",
            queue="default",
            queue_id="q-1",
            priority_id="p-1",
            priority=10,
            subscribers=["sub-a", "sub-b"],
            status="busy",
        )
        assert c.priority == 10
        assert c.subscribers == ["sub-a", "sub-b"]


class TestDeleteOldTasksRequest:
    def test_older_than_required(self):
        with pytest.raises(ValidationError):
            DeleteOldTasksRequest()

    def test_accepts_int(self):
        r = DeleteOldTasksRequest(older_than=86400)
        assert r.older_than == 86400

    def test_accepts_zero(self):
        """Schema allows 0 — the route handler then rejects it with
        bad_request (pinned in test_admin_queues.py). Pin the schema
        side too so the layered guard stays explicit."""
        r = DeleteOldTasksRequest(older_than=0)
        assert r.older_than == 0


class TestDeleteOldTasksResult:
    def test_both_lists_required(self):
        with pytest.raises(ValidationError):
            DeleteOldTasksResult()
        with pytest.raises(ValidationError):
            DeleteOldTasksResult(ok=[])

    def test_accepts_empty_lists(self):
        r = DeleteOldTasksResult(ok=[], errors=[])
        assert r.ok == []
        assert r.errors == []

    def test_string_lists(self):
        r = DeleteOldTasksResult(ok=["t-1"], errors=["t-2"])
        assert r.ok == ["t-1"]


class TestQueueRegistriesRequest:
    def test_default_empty_list(self):
        """Default is [] (NOT None) — the handler reads
        `data.queue_registries or []` so both [] and None coerce. Pin
        the default to [] so the schema's exclude_unset shape stays
        sane."""
        r = QueueRegistriesRequest()
        assert r.queue_registries == []

    def test_accepts_explicit_none(self):
        r = QueueRegistriesRequest(queue_registries=None)
        assert r.queue_registries is None

    def test_accepts_list(self):
        r = QueueRegistriesRequest(queue_registries=["failed", "finished"])
        assert r.queue_registries == ["failed", "finished"]


class TestAutoDeleteEnabledRequest:
    def test_enabled_required(self):
        with pytest.raises(ValidationError):
            AutoDeleteEnabledRequest()

    def test_accepts_true(self):
        assert AutoDeleteEnabledRequest(enabled=True).enabled is True

    def test_accepts_false(self):
        assert AutoDeleteEnabledRequest(enabled=False).enabled is False


class TestAutoDeleteConfigResponse:
    def test_all_optional(self):
        """Defaults: older_than=None, queue_registries=[], enabled=False."""
        r = AutoDeleteConfigResponse()
        assert r.older_than is None
        assert r.queue_registries == []
        assert r.enabled is False

    def test_accepts_full(self):
        r = AutoDeleteConfigResponse(
            older_than=86400,
            queue_registries=["failed"],
            enabled=True,
        )
        assert r.enabled is True
