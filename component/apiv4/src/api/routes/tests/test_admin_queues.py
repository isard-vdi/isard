# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/queues.py — RQ queue introspection (jobs by status,
consumer/worker list) plus the auto-delete-old-tasks lifecycle (config,
list, manual delete, auto delete, enable toggle, retention/registry
config). All endpoints sit on admin_router (admin-only).
"""

import json
import re
import time
from pathlib import Path

import pytest
from api.routes.tests.helpers import MockJWT
from api.schemas.admin.queues import GovernorGaugesResponse
from api.services.admin import queues as queues_service
from api.services.admin.queues import STORAGE_SCHEDULER_DEFAULTS
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/queues, /admin/queues/consumers
# ══════════════════════════════════════════════════════════════════════════


class TestListing:
    def test_queues(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_queues",
            staticmethod(lambda: [{"id": "default", "queued": 3}]),
        )
        response = test_client(url="/admin/items/queues", jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()[0]["id"] == "default"

    def test_consumers(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_consumers",
            staticmethod(lambda: [{"id": "w-1", "queue": "default"}]),
        )
        response = test_client(
            url="/admin/items/queues/consumers", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert response.json()[0]["id"] == "w-1"

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_queues",
            staticmethod(lambda: []),
        )
        response = test_client(url="/admin/items/queues", jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_queues",
            staticmethod(lambda: []),
        )
        response = test_client(
            url="/admin/items/queues", jwt=MockJWT(role_id="manager")
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/queues/old_tasks/config  AND  /admin/queues/old_tasks/{older_than}
# ══════════════════════════════════════════════════════════════════════════


class TestOldTasksRead:
    def test_config_returns_state(self, monkeypatch, test_client):
        """The /config endpoint MUST be declared before the
        /{older_than} catch-all — otherwise FastAPI tries to coerce
        "config" to an int and 422s. The fact that this test passes
        with status 200 (and does not 422 on parsing) is the regression
        guard.
        """
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_auto_delete_config",
            staticmethod(
                lambda: {"older_than": 86400, "queue_registries": [], "enabled": True}
            ),
        )
        response = test_client(
            url="/admin/item/queues/old_tasks/config",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is True

    def test_older_than_path_param(self, monkeypatch, test_client):
        captured = {}

        def fake(older_than):
            captured["older_than"] = older_than
            # Real service returns task keys (list[str]); the
            # response_model now enforces that shape.
            return ["rq:job:t-1"]

        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_old_tasks",
            staticmethod(fake),
        )
        response = test_client(
            url="/admin/items/queues/old_tasks/86400",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        # The Path param is typed `int` — pin that the coercion happens.
        assert captured["older_than"] == 86400
        assert isinstance(captured["older_than"], int)

    def test_non_int_older_than_rejected(self, test_client):
        response = test_client(
            url="/admin/items/queues/old_tasks/not-a-number",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code in (400, 422)


# ══════════════════════════════════════════════════════════════════════════
#  DELETE /admin/queues/old_tasks  (manual)
# ══════════════════════════════════════════════════════════════════════════


class TestManualDeleteOldTasks:
    URL = "/admin/items/queues/old_tasks"

    def test_admin_deletes(self, monkeypatch, test_client):
        captured = {}

        def fake(older_than):
            captured["older_than"] = older_than
            return {"ok": ["t-1"], "errors": []}

        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.delete_old_tasks",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="DELETE",
            jwt=MockJWT(role_id="admin"),
            body={"older_than": 86400},
        )
        assert response.status_code == 200
        assert captured["older_than"] == 86400
        assert response.json()["ok"] == ["t-1"]

    def test_zero_older_than_returns_400(self, monkeypatch, test_client):
        """The handler explicitly rejects falsy older_than (zero) with
        a typed bad_request — even though the Pydantic schema accepts
        0 as a valid int. This guards against a no-op request that
        would otherwise wipe nothing silently.
        """

        # Service must NOT be called for 0.
        def should_not_run(older_than):
            raise AssertionError("delete_old_tasks called with older_than=0")

        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.delete_old_tasks",
            staticmethod(should_not_run),
        )
        response = test_client(
            url=self.URL,
            method="DELETE",
            jwt=MockJWT(role_id="admin"),
            body={"older_than": 0},
        )
        assert response.status_code == 400

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.delete_old_tasks",
            staticmethod(lambda older_than: {}),
        )
        response = test_client(
            url=self.URL,
            method="DELETE",
            jwt=MockJWT(role_id="user"),
            body={"older_than": 86400},
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/queues/old_tasks/config/max_time/{max_time}
# ══════════════════════════════════════════════════════════════════════════


class TestSetMaxTime:
    def test_admin_sets_max_time(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.set_max_time",
            staticmethod(lambda mt: captured.update(max_time=mt) or {"older_than": mt}),
        )
        response = test_client(
            url="/admin/item/queues/old_tasks/config/max_time/172800",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured["max_time"] == 172800
        assert isinstance(captured["max_time"], int)


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/queues/old_tasks/config/queue_registries
# ══════════════════════════════════════════════════════════════════════════


class TestSetQueueRegistries:
    URL = "/admin/item/queues/old_tasks/config/queue_registries"

    def test_admin_sets_registries(self, monkeypatch, test_client):
        captured = {}

        def fake(regs):
            captured["regs"] = regs
            return {"queue_registries": regs}

        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.set_queue_registries",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"queue_registries": ["failed", "finished"]},
        )
        assert response.status_code == 200
        assert captured["regs"] == ["failed", "finished"]

    def test_null_registries_passes_empty_list(self, monkeypatch, test_client):
        """Schema default is [] but the handler reads `data.queue_registries
        or []` so explicit null (None) also coerces to []."""
        captured = {}

        def fake(regs):
            captured["regs"] = regs
            return {"queue_registries": regs}

        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.set_queue_registries",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"queue_registries": None},
        )
        assert response.status_code == 200
        assert captured["regs"] == []


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/queues/old_tasks/config/enabled
# ══════════════════════════════════════════════════════════════════════════


class TestSetEnabled:
    URL = "/admin/item/queues/old_tasks/config/enabled"

    def test_enable(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.set_auto_delete_enabled",
            staticmethod(
                lambda enabled: captured.update(enabled=enabled) or {"enabled": enabled}
            ),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"enabled": True},
        )
        assert response.status_code == 200
        assert captured["enabled"] is True

    def test_disable(self, monkeypatch, test_client):
        captured = {}

        def fake(enabled):
            captured["enabled"] = enabled
            return {"enabled": enabled}

        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.set_auto_delete_enabled",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"enabled": False},
        )
        assert response.status_code == 200
        assert captured["enabled"] is False

    def test_missing_enabled_field_rejected(self, test_client):
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={},
        )
        assert response.status_code in (400, 422)


# ══════════════════════════════════════════════════════════════════════════
#  DELETE /admin/queues/old_tasks/auto
# ══════════════════════════════════════════════════════════════════════════


class TestAutoDelete:
    URL = "/admin/items/queues/old_tasks/auto"

    def test_admin_runs_auto_delete(self, monkeypatch, test_client):
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.delete_old_tasks_auto",
            staticmethod(
                lambda: called.update(yes=True) or {"ok": ["t-1"], "errors": []}
            ),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert called["yes"] is True
        assert response.json()["ok"] == ["t-1"]

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.delete_old_tasks_auto",
            staticmethod(lambda: {}),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  GET / PUT /admin/item/queues/storage_scheduler/config  (live governor knobs)
# ══════════════════════════════════════════════════════════════════════════


class TestStorageSchedulerConfig:
    URL = "/admin/item/queues/storage_scheduler/config"

    def test_get_returns_config(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_storage_scheduler_config",
            staticmethod(
                lambda: {
                    "enabled": True,
                    "psi_limit": 40.0,
                    "max_heavy": 2,
                    "backoff": 3,
                }
            ),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()["max_heavy"] == 2

    def test_get_defaults_a_null_valued_block(self, monkeypatch, test_client):
        # Regression: a present-but-None config block (a partial or legacy
        # write — e.g. a leftover probe key with all-None siblings) must fall
        # back to the deployment defaults, NOT 500 on float(None)/int(None).
        # Mock only the DB + Redis boundaries so the REAL accessor logic runs;
        # test_get_returns_config above mocks the accessor itself, so it cannot
        # catch this — the class of gap the fix closes.
        monkeypatch.setattr(
            "api.services.admin.queues.Config.get_storage_scheduler_config",
            staticmethod(
                lambda: {
                    "_probe": None,
                    "enabled": None,
                    "psi_limit": None,
                    "max_heavy": None,
                    "backoff": None,
                    "category_weights": None,
                    "category_max_inflight": None,
                }
            ),
        )
        monkeypatch.setattr(
            "api.services.admin.queues.AdminQueuesService._publish_governor_config",
            staticmethod(lambda block: None),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] == STORAGE_SCHEDULER_DEFAULTS["enabled"]
        assert body["psi_limit"] == STORAGE_SCHEDULER_DEFAULTS["psi_limit"]
        assert body["max_heavy"] == STORAGE_SCHEDULER_DEFAULTS["max_heavy"]
        assert body["backoff"] == STORAGE_SCHEDULER_DEFAULTS["backoff"]
        assert (
            body["category_weights"] == STORAGE_SCHEDULER_DEFAULTS["category_weights"]
        )

    def test_admin_sets_partial(self, monkeypatch, test_client):
        captured = {}

        def fake(updates):
            captured["updates"] = updates
            return {"enabled": True, "psi_limit": 55.0, "max_heavy": 2, "backoff": 3}

        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.set_storage_scheduler_config",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"psi_limit": 55},
        )
        assert response.status_code == 200
        # exclude_none => only the supplied key is forwarded to the service
        assert captured["updates"] == {"psi_limit": 55.0}
        assert response.json()["psi_limit"] == 55.0

    def test_out_of_range_psi_rejected_by_schema(self, test_client):
        # schema bound (0..100) rejects before the service is reached -> 422
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"psi_limit": 250},
        )
        # the app maps request-body validation errors to 400 (bad_request)
        assert response.status_code == 400

    def test_zero_max_heavy_rejected_by_schema(self, test_client):
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"max_heavy": 0},
        )
        assert response.status_code == 400

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_storage_scheduler_config",
            staticmethod(lambda: {}),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_service_clamps_and_rejects(self, monkeypatch):
        # Direct service-layer test: defensive clamp/validate independent of the
        # schema (psi>100 -> 100, max_heavy 0 -> 1, bad enabled -> 400, empty ->
        # 400). Config writes are captured, not persisted.
        from api.services.admin.queues import AdminQueuesService
        from api.services.error import Error
        from isardvdi_common.models.config import Config

        captured = {}
        monkeypatch.setattr(
            Config,
            "update_storage_scheduler",
            staticmethod(lambda updates: captured.update(written=updates)),
        )
        monkeypatch.setattr(
            Config,
            "get_storage_scheduler_config",
            staticmethod(lambda: captured.get("written", {})),
        )
        # Capture the Redis mirror instead of hitting a real broker: the setter
        # must publish the fresh raw block to governor:config for the workers.
        monkeypatch.setattr(
            AdminQueuesService,
            "_publish_governor_config",
            staticmethod(lambda block: captured.update(published=block)),
        )
        out = AdminQueuesService.set_storage_scheduler_config(
            {"psi_limit": 250, "max_heavy": 0, "backoff": -3}
        )
        assert captured["written"] == {"psi_limit": 100.0, "max_heavy": 1, "backoff": 1}
        assert out["psi_limit"] == 100.0
        # the clamped raw block was mirrored to the workers' Redis key
        assert captured["published"] == {
            "psi_limit": 100.0,
            "max_heavy": 1,
            "backoff": 1,
        }
        with pytest.raises(Error):
            AdminQueuesService.set_storage_scheduler_config({"enabled": "yes"})
        with pytest.raises(Error):
            AdminQueuesService.set_storage_scheduler_config({})

    def test_service_clamps_upper_bounds(self, monkeypatch):
        # Review #11: over-range values must be clamped DOWN, not persisted raw —
        # backoff>=90 self-locks the fleet, an unbounded weight OOMs the worker.
        from api.services.admin.queues import AdminQueuesService
        from isardvdi_common.models.config import Config

        captured = {}
        monkeypatch.setattr(
            Config,
            "update_storage_scheduler",
            staticmethod(lambda updates: captured.update(written=updates)),
        )
        monkeypatch.setattr(
            Config,
            "get_storage_scheduler_config",
            staticmethod(lambda: captured.get("written", {})),
        )
        monkeypatch.setattr(
            AdminQueuesService,
            "_publish_governor_config",
            staticmethod(lambda block: None),
        )
        AdminQueuesService.set_storage_scheduler_config(
            {
                "max_heavy": 9999,
                "backoff": 100000,
                "category_weights": {"catA": 10**8},
                "category_default_max_inflight": 10**6,
            }
        )
        assert captured["written"]["max_heavy"] == 64
        assert captured["written"]["backoff"] == 60
        assert captured["written"]["category_weights"] == {"catA": 1000}
        assert captured["written"]["category_default_max_inflight"] == 1000

    def test_admin_sets_category_fairness_knobs(self, monkeypatch, test_client):
        # The per-category fairness knobs (weights / caps / default cap) must reach
        # the service through the schema — without this the fairness feature is
        # untunable via the API and only settable by writing governor:config raw.
        captured = {}

        def fake(updates):
            captured["updates"] = updates
            return {
                "enabled": True,
                "psi_limit": 40.0,
                "max_heavy": 2,
                "backoff": 3,
                "category_weights": {"catA": 3},
                "category_max_inflight": {"catB": 1},
                "category_default_max_inflight": 2,
            }

        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.set_storage_scheduler_config",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={
                "category_weights": {"catA": 3},
                "category_max_inflight": {"catB": 1},
                "category_default_max_inflight": 2,
            },
        )
        assert response.status_code == 200
        assert captured["updates"] == {
            "category_weights": {"catA": 3},
            "category_max_inflight": {"catB": 1},
            "category_default_max_inflight": 2,
        }
        assert response.json()["category_weights"] == {"catA": 3}

    def test_zero_category_weight_rejected_by_schema(self, test_client):
        # a per-category weight/cap < 1 is rejected at the schema edge (422 -> 400)
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"category_weights": {"catA": 0}},
        )
        assert response.status_code == 400

    def test_service_cleans_category_maps(self, monkeypatch):
        # Direct service-layer defence: category maps floored at 1, default cap
        # clamped, non-dict / non-numeric rejected, and the cleaned maps mirrored
        # to the workers' governor:config.
        from api.services.admin.queues import AdminQueuesService
        from api.services.error import Error
        from isardvdi_common.models.config import Config

        captured = {}
        monkeypatch.setattr(
            Config,
            "update_storage_scheduler",
            staticmethod(lambda updates: captured.update(written=updates)),
        )
        monkeypatch.setattr(
            Config,
            "get_storage_scheduler_config",
            staticmethod(lambda: captured.get("written", {})),
        )
        monkeypatch.setattr(
            AdminQueuesService,
            "_publish_governor_config",
            staticmethod(lambda block: captured.update(published=block)),
        )
        AdminQueuesService.set_storage_scheduler_config(
            {
                "category_weights": {"catA": 5, "catB": 0},
                "category_max_inflight": {"catC": 3},
                "category_default_max_inflight": 0,
            }
        )
        assert captured["written"] == {
            "category_weights": {"catA": 5, "catB": 1},
            "category_max_inflight": {"catC": 3},
            "category_default_max_inflight": 1,
        }
        assert captured["published"]["category_weights"] == {"catA": 5, "catB": 1}
        with pytest.raises(Error):
            AdminQueuesService.set_storage_scheduler_config(
                {"category_weights": [1, 2]}
            )
        with pytest.raises(Error):
            AdminQueuesService.set_storage_scheduler_config(
                {"category_max_inflight": {"catA": "big"}}
            )


# ══════════════════════════════════════════════════════════════════════════
#  STORAGE-GOVERNOR read layer (P2.4 §7/1) — lying-monitor guards.
#
#  fakeredis is not a dependency, so we drive the REAL service against a small
#  in-memory FakeRedis that implements only the exact commands the read paths
#  use, spy on the RQ boundary (Queue.get_job_ids / Job.fetch_many / registry
#  reads), and test the pure helpers (key-recovery, leak arithmetic, heartbeat
#  truth, degradation) directly — mocking at the Redis/rethink boundary and
#  exercising the real service (apiv4 skill B9).
# ══════════════════════════════════════════════════════════════════════════

from datetime import datetime, timedelta, timezone

from api.services.admin import queues as gov


def _utc(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class _FakePipeline:
    """Records queued commands and replays them against the parent FakeRedis on
    execute() — matches redis-py's ``with conn.pipeline() as pipe:`` usage."""

    def __init__(self, parent):
        self._parent = parent
        self._ops = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        def _queue(*args, **kwargs):
            self._ops.append((name, args, kwargs))
            return self

        return _queue

    def execute(self):
        return [
            getattr(self._parent, name)(*args, **kwargs)
            for (name, args, kwargs) in self._ops
        ]


class FakeRedis:
    """Minimal in-memory Redis for the governor read paths. Byte semantics where
    the real client returns bytes. keys()/pubsub_channels() are FORBIDDEN — they
    record + raise so a test can prove they were never called."""

    def __init__(
        self,
        *,
        rq_queues=None,
        lists=None,
        sets=None,
        hashes=None,
        zsets=None,
        strings=None,
        info=None,
        ping_error=None,
    ):
        # rq_queues: iterable of bare lane names -> stored as rq:queue:<name> keys
        self._sets = {}
        if rq_queues is not None:
            self._sets["rq:queues"] = {f"rq:queue:{n}".encode() for n in rq_queues}
        for k, v in (sets or {}).items():
            self._sets[k] = {
                (x if isinstance(x, bytes) else str(x).encode()) for x in v
            }
        self._lists = {k: list(v) for k, v in (lists or {}).items()}
        self._hashes = {k: dict(v) for k, v in (hashes or {}).items()}
        self._zsets = {k: list(v) for k, v in (zsets or {}).items()}
        self._strings = dict(strings or {})
        self._info = info or {
            "used_memory": 734003200,
            "maxmemory": 8589934592,
            "evicted_keys": 0,
        }
        self._ping_error = ping_error
        self.forbidden_calls = []
        self.set_calls = []
        self.srem_calls = []

    # --- context manager (mirrors redis.Redis) ---
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def close(self):
        pass

    # --- health ---
    def ping(self):
        if self._ping_error:
            raise self._ping_error
        return True

    def info(self, section=None):
        return dict(self._info)

    # --- sets ---
    def smembers(self, key):
        return set(self._sets.get(key, set()))

    def scard(self, key):
        return len(self._sets.get(key, set()))

    # --- lists ---
    def llen(self, key):
        return len(self._lists.get(key, []))

    def lrange(self, key, start, end):
        data = self._lists.get(key, [])
        if end == -1:
            return data[start:]
        return data[start : end + 1]

    # --- hashes ---
    def hgetall(self, key):
        return dict(self._hashes.get(key, {}))

    def hget(self, key, field):
        return self._hashes.get(key, {}).get(field)

    # --- zsets (registries) ---
    def zcard(self, key):
        return len(self._zsets.get(key, []))

    def zrange(self, key, start, end, *a, **k):
        data = self._zsets.get(key, [])
        if end == -1:
            return data[start:]
        return data[start : end + 1]

    # --- strings ---
    def get(self, key):
        return self._strings.get(key)

    def mget(self, keys):
        return [self._strings.get(k) for k in keys]

    # --- WRITES: must never be called by a read path ---
    def set(self, key, value, *a, **k):
        self.set_calls.append((key, value))

    def srem(self, key, *members):
        self.srem_calls.append((key, members))

    # --- FORBIDDEN enumerations ---
    def keys(self, pattern="*"):
        self.forbidden_calls.append(("keys", pattern))
        raise AssertionError(f"forbidden keys() glob called: {pattern}")

    def pubsub_channels(self, pattern="*"):
        self.forbidden_calls.append(("pubsub_channels", pattern))
        raise AssertionError("forbidden pubsub_channels() called")

    def pipeline(self):
        return _FakePipeline(self)


class _FakeJob:
    def __init__(self, status=None, enqueued_at=None, started_at=None, timeout=None):
        self._status = status
        self.enqueued_at = enqueued_at
        self.started_at = started_at
        self.timeout = timeout
        self.origin = "storage.default.maintenance"

    def get_status(self, refresh=False):
        return self._status


@pytest.fixture()
def clean_gov_caches():
    gov.clear_governor_caches()
    yield
    gov.clear_governor_caches()


# ── (e) cross-pool running-key recovery ────────────────────────────────────
class TestKeyRecovery:
    def test_cross_pool_key(self):
        assert gov._parse_category_running_key("governor:running:src:dst:catX") == (
            "src:dst",
            "catX",
        )

    def test_simple_key(self):
        assert gov._parse_category_running_key("governor:running:default:9a3b") == (
            "default",
            "9a3b",
        )

    def test_non_running_key(self):
        assert gov._parse_category_running_key("governor:heavy_running") is None


# ── (d) leak scan: read-only, exception-safe, batched, capped ──────────────
class TestLeakScan:
    def test_missing_job_counts_leaked_no_srem(self, monkeypatch):
        conn = FakeRedis()
        calls = {"fetch_many": 0}

        def fake_fetch_many(ids, connection=None, serializer=None):
            calls["fetch_many"] += 1
            # a missing job id -> None (mirrors NoSuchjob); never raises
            return [None for _ in ids]

        monkeypatch.setattr(gov.Job, "fetch_many", staticmethod(fake_fetch_many))
        leaks, truncated = gov._leak_scan(
            conn, {gov.HEAVY_RUNNING_KEY: ["gone-1", "gone-2"]}
        )
        assert leaks[gov.HEAVY_RUNNING_KEY]["leaked"] == 2
        assert leaks[gov.HEAVY_RUNNING_KEY]["live"] == 0
        assert truncated == 0
        assert calls["fetch_many"] == 1  # batched (one fetch_many call)
        # NEVER SREM a set member during a read.
        assert conn.srem_calls == []

    def test_live_job_not_leaked(self, monkeypatch):
        monkeypatch.setattr(
            gov.Job,
            "fetch_many",
            staticmethod(
                lambda ids, connection=None, serializer=None: [
                    _FakeJob(status="started") for _ in ids
                ]
            ),
        )
        leaks, _t = gov._leak_scan(FakeRedis(), {gov.HEAVY_RUNNING_KEY: ["j1", "j2"]})
        assert leaks[gov.HEAVY_RUNNING_KEY]["leaked"] == 0
        assert leaks[gov.HEAVY_RUNNING_KEY]["live"] == 2

    def test_truncation_capped(self, monkeypatch):
        monkeypatch.setattr(gov, "MAX_INFLIGHT_SCAN", 2)
        monkeypatch.setattr(
            gov.Job,
            "fetch_many",
            staticmethod(
                lambda ids, connection=None, serializer=None: [
                    _FakeJob(status="started") for _ in ids
                ]
            ),
        )
        leaks, truncated = gov._leak_scan(
            FakeRedis(), {gov.HEAVY_RUNNING_KEY: ["a", "b", "c"]}
        )
        assert truncated == 1  # 3 unique - cap 2


# ── (c) heartbeat truth: SET-member-without-live-hash, not >840s ───────────
class TestHeartbeatTruth:
    def setup_method(self):
        self.now = datetime(2026, 7, 7, 12, 0, 0, tzinfo=timezone.utc)

    def test_absent_hash_is_down(self):
        row = gov._build_worker_row("w-absent", {}, {}, self.now)
        assert row["up"] is False
        assert row["hash_present"] is False

    def test_stale_hash_is_down(self):
        wh = {"last_heartbeat": _utc(self.now - timedelta(seconds=500))}
        row = gov._build_worker_row("w-stale", wh, {}, self.now)
        assert row["up"] is False
        assert row["hash_present"] is True

    def test_fresh_hash_is_up(self):
        wh = {
            "last_heartbeat": _utc(self.now - timedelta(seconds=2)),
            "queues": "storage.default.maintenance",
            "state": "busy",
        }
        row = gov._build_worker_row("w-fresh", wh, {}, self.now)
        assert row["up"] is True
        assert row["kind"] == "elastic"
        # governor:worker:<name> not published yet -> served/PSI degrade.
        assert row["served_known"] is False
        assert row["psi_cpu"] is None
        assert row["multitenancy"] is None


# ── multitenancy_active from the worker-reported flag (idle-P2 not blinded) ─
class TestMultitenancyFlag:
    def test_unknown_when_no_worker_reports(self):
        now = datetime(2026, 7, 7, 12, 0, 0, tzinfo=timezone.utc)
        wh = {"last_heartbeat": _utc(now - timedelta(seconds=1))}
        row = gov._build_worker_row("w", wh, {}, now)
        assert row["multitenancy"] is None  # -> service maps to "unknown"

    def test_true_from_flag_without_lanes(self):
        now = datetime(2026, 7, 7, 12, 0, 0, tzinfo=timezone.utc)
        wh = {"last_heartbeat": _utc(now - timedelta(seconds=1))}
        gh = {"multitenancy": "true"}
        row = gov._build_worker_row("w", wh, gh, now)
        assert row["up"] is True
        assert row["multitenancy"] is True


# ── psi_mem surfaced from the worker heartbeat (memory-PSI gate) ───────────
class TestPsiMem:
    now = datetime(2026, 7, 7, 12, 0, 0, tzinfo=timezone.utc)

    def test_psi_mem_surfaced_alongside_cpu_io(self):
        wh = {"last_heartbeat": _utc(self.now - timedelta(seconds=1))}
        gh = {"psi_cpu": "3.0", "psi_io": "4.0", "psi_mem": "7.5"}
        row = gov._build_worker_row("w", wh, gh, self.now)
        assert row["psi_cpu"] == 3.0
        assert row["psi_io"] == 4.0
        assert row["psi_mem"] == 7.5

    def test_psi_mem_none_on_rolling_upgrade_worker(self):
        # A worker on the old build publishes cpu/io but no psi_mem -> None, not a
        # crash (the read layer must degrade over a mixed-version fleet).
        wh = {"last_heartbeat": _utc(self.now - timedelta(seconds=1))}
        gh = {"psi_cpu": "3.0", "psi_io": "4.0"}
        row = gov._build_worker_row("w", wh, gh, self.now)
        assert row["psi_mem"] is None


# ── (a) oldest-age head-only + (f) cleanup=False on registry reads ─────────
class TestLaneStats:
    def test_oldest_age_head_only_and_empty_null(self, monkeypatch):
        seen = {}

        real_get_job_ids = gov.Queue.get_job_ids

        def spy_get_job_ids(self, offset=0, length=-1):
            seen["args"] = (offset, length)
            return []  # empty queue

        monkeypatch.setattr(gov.Queue, "get_job_ids", spy_get_job_ids)
        conn = FakeRedis()
        stats = gov._lane_stats(conn, "storage.default.maintenance", time.time())
        # HEAD ONLY: (0, 1) -> lrange 0 0. NEVER (0, 0) (a full LRANGE).
        assert seen["args"] == (0, 1)
        assert stats["oldest_queued_age_seconds"] is None  # empty -> null

    def test_registry_reads_pass_cleanup_false(self, monkeypatch):
        counts = {}

        def spy_count(self, cleanup=True):
            counts.setdefault("count_cleanup", []).append(cleanup)
            return 0

        def spy_started_ids(self, start=0, end=-1, desc=False, cleanup=True):
            counts.setdefault("started_cleanup", []).append(cleanup)
            return []

        monkeypatch.setattr(gov, "MAX_STARTED", 5)
        import rq.registry as rqreg

        monkeypatch.setattr(rqreg.BaseRegistry, "get_job_count", spy_count)
        monkeypatch.setattr(rqreg.StartedJobRegistry, "get_job_ids", spy_started_ids)
        monkeypatch.setattr(gov.Queue, "get_job_ids", lambda self, o=0, l=-1: [])
        gov._lane_stats(FakeRedis(), "storage.default.maintenance", time.time())
        # a StartedJobRegistry read with cleanup=True MOVES timed-out jobs to
        # FailedJobRegistry (a WRITE) — every read here must be cleanup=False.
        assert counts["count_cleanup"] and all(
            c is False for c in counts["count_cleanup"]
        )
        assert counts["started_cleanup"] == [False]


# ── the /admin/queues counters are a GET: they must not mutate RQ state ────
class TestQueueJobCountsAreReadOnly:
    QUEUE = "storage.default.maintenance"

    @pytest.fixture(autouse=True)
    def _clean(self):
        gov.clear_queue_data_caches()
        yield
        gov.clear_queue_data_caches()

    def _fake_redis(self):
        return FakeRedis(
            lists={f"rq:queue:{self.QUEUE}": ["a", "b", "c"]},
            zsets={
                f"rq:wip:{self.QUEUE}": ["s1", "s2"],
                f"rq:finished:{self.QUEUE}": ["f1"],
                f"rq:failed:{self.QUEUE}": ["e1", "e2", "e3"],
                f"rq:deferred:{self.QUEUE}": ["d1"],
                f"rq:scheduled:{self.QUEUE}": [],
                f"rq:canceled:{self.QUEUE}": ["c1", "c2", "c3", "c4"],
            },
        )

    def test_no_registry_cleanup_on_dashboard_read(self, monkeypatch):
        # StartedJobRegistry.cleanup() moves timed-out started jobs into
        # FailedJobRegistry, firing failure callbacks / retries / dependent
        # enqueues. A dashboard poll must never trigger it.
        import rq.registry as rqreg

        def boom(self, *a, **k):
            raise AssertionError(
                f"{type(self).__name__}.cleanup() called from a read path"
            )

        for cls in (
            rqreg.BaseRegistry,
            rqreg.StartedJobRegistry,
            rqreg.FinishedJobRegistry,
            rqreg.FailedJobRegistry,
            rqreg.DeferredJobRegistry,
        ):
            monkeypatch.setattr(cls, "cleanup", boom)
        monkeypatch.setattr(gov, "_connect_redis", self._fake_redis)

        gov.AdminQueuesService._get_queue_jobs(self.QUEUE)

    def test_registry_reads_pass_cleanup_false_and_counts_are_correct(
        self, monkeypatch
    ):
        import rq.registry as rqreg

        seen = []
        real = rqreg.BaseRegistry.get_job_count

        def spy(self, cleanup=True):
            seen.append(cleanup)
            return real(self, cleanup=cleanup)

        monkeypatch.setattr(rqreg.BaseRegistry, "get_job_count", spy)
        monkeypatch.setattr(gov, "_connect_redis", self._fake_redis)

        counts = gov.AdminQueuesService._get_queue_jobs(self.QUEUE)

        assert seen and all(c is False for c in seen)
        assert counts == {
            "queued": 3,
            "started": 2,
            "finished": 1,
            "failed": 3,
            "deferred": 1,
            "scheduled": 0,
            "canceled": 4,
        }


# ── (g) category name map: friendly labels, one read, no N+1 ───────────────
class TestCategoryNameMap:
    def test_resolves_and_reads_once(self, monkeypatch, clean_gov_caches):
        calls = {"n": 0}

        def fake_map():
            calls["n"] += 1
            return {"9a3b": "Formacio Professional"}

        monkeypatch.setattr(
            gov.CommonCategories, "get_id_name_map", staticmethod(fake_map)
        )
        names = gov.AdminQueuesService._category_name_map()
        # cached -> a second call does NOT re-read the DB (no N+1)
        gov.AdminQueuesService._category_name_map()
        assert calls["n"] == 1
        assert names[gov.NULL_CATEGORY] == "No category / system"
        assert names["9a3b"] == "Formacio Professional"
        resolve = gov.AdminQueuesService._resolve_category_name
        assert resolve(gov.NULL_CATEGORY, names) == "No category / system"
        assert resolve(None, names) == "_none"
        assert resolve("deleted-owner", names) == "deleted-owner"  # raw-id fallback


# ── (b) bounded enumeration + forbidden calls never made + truncation ──────
class TestBoundedEnumeration:
    def test_no_glob_no_queue_all_and_truncation(self, monkeypatch, clean_gov_caches):
        # 4 storage lanes; cap at 2 -> truncated_lanes == 2.
        monkeypatch.setattr(gov, "MAX_LANES", 2)
        lanes = [
            "storage.default.maintenance",
            "storage.default.bulk",
            "storage.pool2.maintenance",
            "storage.pool3.bulk",
        ]
        conn = FakeRedis(rq_queues=lanes)
        monkeypatch.setattr(gov, "_connect_redis", lambda: conn)
        monkeypatch.setattr(
            gov.CommonCategories, "get_id_name_map", staticmethod(lambda: {})
        )
        monkeypatch.setattr(
            gov.Config, "get_storage_scheduler_config", staticmethod(lambda: {})
        )
        # Queue.all() must NEVER be called by the new code.
        qall_calls = []
        monkeypatch.setattr(
            gov.Queue,
            "all",
            classmethod(
                lambda cls, *a, **k: qall_calls.append(1)
                or (_ for _ in ()).throw(AssertionError("Queue.all called"))
            ),
        )
        data = gov.AdminQueuesService.get_governor()
        assert data["redis"]["up"] is True  # NOT degraded -> forbidden paths unused
        assert data["truncated_lanes"] == 2
        assert conn.forbidden_calls == []  # keys()/pubsub_channels() never called
        assert qall_calls == []
        # read-only: a governor poll writes nothing.
        assert conn.set_calls == []
        assert conn.srem_calls == []


# ── (h) read-only config: a /governor poll leaves governor:config byte-equal ─
class TestReadOnlyConfig:
    def test_governor_config_untouched(self, monkeypatch, clean_gov_caches):
        raw = json.dumps({"enabled": True, "psi_limit": 40.0, "max_heavy": 2})
        conn = FakeRedis(
            rq_queues=["storage.default.maintenance"],
            strings={gov.GOVERNOR_CONFIG_KEY: raw},
        )
        monkeypatch.setattr(gov, "_connect_redis", lambda: conn)
        monkeypatch.setattr(
            gov.CommonCategories, "get_id_name_map", staticmethod(lambda: {})
        )
        monkeypatch.setattr(
            gov.Config,
            "get_storage_scheduler_config",
            staticmethod(lambda: {"enabled": True, "psi_limit": 40.0, "max_heavy": 2}),
        )
        gov.AdminQueuesService.get_governor()
        # governor:config was READ, never re-published.
        assert conn.set_calls == []
        assert conn._strings[gov.GOVERNOR_CONFIG_KEY] == raw  # byte-identical


# ── configured categories always surfaced on a P2 install (idle-safe) ──────
class TestConfiguredCategorySeed:
    """A per-category (P2) install must show its categories even at idle:
    discovery GC's idle fair lanes, so without the seed the per-category
    fairness panels would read "No data" on a single-``default`` install."""

    def _p2_worker_conn(self, now, multitenancy):
        name = "storage.default.maintenance.w1"
        return FakeRedis(
            rq_queues=[],  # NO fair lanes -> discovery finds zero categories
            sets={"rq:workers": {f"rq:worker:{name}".encode()}},
            hashes={
                f"rq:worker:{name}": {
                    b"last_heartbeat": _utc(now).encode(),
                    b"queues": b"storage.default.maintenance",
                    b"state": b"idle",
                },
                gov._GOVERNOR_WORKER_PREFIX
                + name: {
                    b"multitenancy": b"true" if multitenancy else b"false",
                    b"pool": b"default",
                },
            },
        )

    def test_default_seeded_at_idle_on_p2(self, monkeypatch, clean_gov_caches):
        now = datetime.now(timezone.utc)
        conn = self._p2_worker_conn(now, multitenancy=True)
        monkeypatch.setattr(gov, "_connect_redis", lambda: conn)
        monkeypatch.setattr(
            gov.CommonCategories, "get_id_name_map", staticmethod(lambda: {})
        )
        monkeypatch.setattr(
            gov.Config, "get_storage_scheduler_config", staticmethod(lambda: {})
        )
        data = gov.AdminQueuesService.get_governor()
        assert data["multitenancy_active"] is True
        pools = {p["pool"]: p for p in data["pools"]}
        assert "default" in pools, "fair pool must exist even with no live lanes"
        cats = {c["category_id"]: c for c in pools["default"]["categories"]}
        # the install's default category is present with a zero baseline
        assert "default" in cats
        assert cats["default"]["inflight"] == 0
        assert cats["default"]["weight"] == 1
        assert cats["default"]["cap"] is None
        # read-only: seeding never writes back to Redis.
        assert conn.set_calls == []
        assert conn.srem_calls == []

    def test_not_seeded_on_flat_install(self, monkeypatch, clean_gov_caches):
        now = datetime.now(timezone.utc)
        conn = self._p2_worker_conn(now, multitenancy=False)
        monkeypatch.setattr(gov, "_connect_redis", lambda: conn)
        monkeypatch.setattr(
            gov.CommonCategories, "get_id_name_map", staticmethod(lambda: {})
        )
        monkeypatch.setattr(
            gov.Config, "get_storage_scheduler_config", staticmethod(lambda: {})
        )
        data = gov.AdminQueuesService.get_governor()
        # flat/P1 install: no per-category scheduling -> panels stay empty.
        assert data["multitenancy_active"] is False
        assert data["pools"] == []


# ── (h2) shed / defer counters surfaced in the governor payload ────────────
#
# A shed 429 is seen only by the rejected caller and ``deferring`` is a
# point-in-time gauge, so without these fields a shed storm or an oscillating
# defer storm is invisible to every operator view.
class TestShedDeferCounters:
    def _conn(self, **strings):
        from isardvdi_common.lib import governor_counters as gcnt

        minute = int(time.time() // 60)
        return FakeRedis(
            rq_queues=["storage.default.maintenance"],
            hashes={
                gcnt.totals_key(gcnt.SHED): {
                    b"total": b"7",
                    b"reason:no_consumer": b"5",
                    b"reason:overloaded": b"2",
                    b"tier:interactive": b"7",
                    b"last_reason": b"no_consumer",
                    b"last_pool": b"default",
                    b"last_tier": b"interactive",
                },
                gcnt.totals_key(gcnt.DEFER): {
                    b"total": b"3",
                    b"reason:psi": b"3",
                    b"last_worker": b"storage-1",
                },
            },
            strings={
                f"{gcnt.COUNTERS_PREFIX}:{gcnt.SHED}:m:{minute}": b"4",
                f"{gcnt.COUNTERS_PREFIX}:{gcnt.DEFER}:m:{minute}": b"3",
            },
        )

    def test_counters_in_payload(self, monkeypatch, clean_gov_caches):
        conn = self._conn()
        monkeypatch.setattr(gov, "_connect_redis", lambda: conn)
        monkeypatch.setattr(
            gov.CommonCategories, "get_id_name_map", staticmethod(lambda: {})
        )
        monkeypatch.setattr(
            gov.Config, "get_storage_scheduler_config", staticmethod(lambda: {})
        )
        data = gov.AdminQueuesService.get_governor()
        assert data["shed"]["total"] == 7
        assert data["shed"]["recent"] == 4
        assert data["shed"]["by_reason"] == {"no_consumer": 5, "overloaded": 2}
        assert data["shed"]["by_tier"] == {"interactive": 7}
        assert data["shed"]["last_pool"] == "default"
        assert data["defer"]["total"] == 3
        assert data["defer"]["recent"] == 3
        assert data["defer"]["last_worker"] == "storage-1"
        # still read-only: reading a counter must never write one.
        assert conn.set_calls == []
        assert conn.forbidden_calls == []

    def test_counters_zeroed_when_degraded(self):
        data = gov.AdminQueuesService._degraded_governor(1751884800.0)
        assert data["shed"]["total"] == 0
        assert data["defer"]["total"] == 0
        assert data["shed"]["last_reason"] is None

    def test_counters_validate_against_the_response_model(self):
        data = gov.AdminQueuesService._degraded_governor(1751884800.0)
        model = GovernorGaugesResponse(**data)
        assert model.shed.total == 0
        assert model.defer.window_minutes == data["defer"]["window_minutes"]


# ── (i) 200 + redis.up=false when Redis is down (never raise) ──────────────
class TestDegradesOnRedisDown:
    def test_service_degrades_not_raises(self, monkeypatch, clean_gov_caches):
        from redis.exceptions import ConnectionError as RedisConnError

        conn = FakeRedis(ping_error=RedisConnError("down"))
        monkeypatch.setattr(gov, "_connect_redis", lambda: conn)
        data = gov.AdminQueuesService.get_governor()  # must NOT raise
        assert data["redis"]["up"] is False
        assert data["multitenancy_active"] == "unknown"
        assert data["pools"] == []
        assert data["workers"] == []

    def test_consumers_degrade_to_empty(self, monkeypatch, clean_gov_caches):
        from redis.exceptions import ConnectionError as RedisConnError

        def boom():
            raise RedisConnError("down")

        monkeypatch.setattr(gov, "_connect_redis", boom)
        assert gov.AdminQueuesService.get_consumers() == []


# ── worker enumeration via rq:workers SET + HGETALL, never a keys glob ─────
class TestWorkerEnumeration:
    def test_consumers_read_via_smembers_hgetall(self, monkeypatch, clean_gov_caches):
        now = datetime.now(timezone.utc)
        conn = FakeRedis(
            sets={"rq:workers": {b"rq:worker:storage.default.maintenance.w1"}},
            hashes={
                "rq:worker:storage.default.maintenance.w1": {
                    b"last_heartbeat": _utc(now).encode(),
                    b"queues": b"storage.default.maintenance",
                    b"state": b"busy",
                },
                # governor:worker:<name> is absent -> served/PSI degrade.
            },
        )
        monkeypatch.setattr(gov, "_connect_redis", lambda: conn)
        rows = gov.AdminQueuesService.get_consumers()
        assert conn.forbidden_calls == []  # never a keys("rq:workers:*") glob
        assert len(rows) == 1
        assert rows[0]["name"] == "storage.default.maintenance.w1"
        assert rows[0]["up"] is True
        assert rows[0]["served_known"] is False


# ── (j) auth + route shape: user AND manager -> 403 ────────────────────────
class TestGovernorRouteAuth:
    def test_governor_admin_200(self, monkeypatch, test_client):
        sample = gov.AdminQueuesService._degraded_governor(1751884800.0)
        sample["redis"] = {"up": True, "ping_ms": 0.4}
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_governor",
            staticmethod(lambda: sample),
        )
        response = test_client(
            url="/admin/items/queues/governor", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        body = response.json()
        assert body["generated_at"] == 1751884800.0
        assert body["redis"]["up"] is True
        # data_age_seconds is recomputed at response time (frozen-cache honesty)
        assert body["data_age_seconds"] >= 0.0

    def test_governor_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_governor",
            staticmethod(lambda: {}),
        )
        response = test_client(
            url="/admin/items/queues/governor", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403

    def test_governor_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_governor",
            staticmethod(lambda: {}),
        )
        response = test_client(
            url="/admin/items/queues/governor", jwt=MockJWT(role_id="manager")
        )
        assert response.status_code == 403


class TestBacklogRouteAuth:
    def test_backlog_admin_200(self, monkeypatch, test_client):
        rows = [
            {
                "pool": "default",
                "category_id": "_nocat",
                "category_name": "No category / system",
                "tier": "maintenance",
                "queued": 33,
                "started": 1,
                "started_over_timeout": 0,
                "failed": 2,
                "deferred": 0,
                "oldest_queued_age_seconds": 902.0,
                "has_consumer": True,
                "coverage_known": True,
                "stranded": False,
            }
        ]
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_backlog_rollup",
            staticmethod(lambda: rows),
        )
        response = test_client(
            url="/admin/items/queues/backlog", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert response.json()[0]["queued"] == 33

    def test_backlog_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_backlog_rollup",
            staticmethod(lambda: []),
        )
        response = test_client(
            url="/admin/items/queues/backlog", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403

    def test_backlog_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_backlog_rollup",
            staticmethod(lambda: []),
        )
        response = test_client(
            url="/admin/items/queues/backlog", jwt=MockJWT(role_id="manager")
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  PROBLEM-TASK listing (P2.4 §7/3) — bounded, dangling-safe, kind-filtered.
#
#  Drives the REAL service against FakeRedis + fake RQ jobs, mocking only at
#  the Redis / Job.fetch / registry boundary (apiv4 skill B9): the composite-id
#  parse, the over-timeout and pending==False filters, cleanup=False on every
#  registry read, dangling-id survival, and exc_string-only-for-FAILED.
# ══════════════════════════════════════════════════════════════════════════

from rq.exceptions import NoSuchJobError
from rq.results import Result as _RqResult


class _ProblemResult:
    def __init__(self, type_, exc_string=None):
        self.type = type_
        self.exc_string = exc_string


class _ProblemJob:
    """A minimal RQ-job stand-in carrying just the attributes the problem-task
    row builder + the Task chain properties read."""

    def __init__(
        self,
        id,
        *,
        status="failed",
        enqueued_at=None,
        started_at=None,
        ended_at=None,
        timeout=None,
        retries_left=None,
        origin="storage.default.9a3b.maintenance",
        func_name="task.convert",
        meta=None,
        result=None,
    ):
        self.id = id
        self._status = status
        self.enqueued_at = enqueued_at
        self.started_at = started_at
        self.ended_at = ended_at
        self.timeout = timeout
        self.retries_left = retries_left
        self.origin = origin
        self.func_name = func_name
        self.meta = meta or {}
        self._result = result
        self.args = []
        self.kwargs = {}

    def get_status(self, refresh=False):
        return self._status

    def get_position(self):
        return None

    def latest_result(self, timeout=0):
        return self._result


def _install_jobs(monkeypatch, jobs_by_id):
    """Patch the shared RQ ``Job`` class so ``Task(id=...)`` resolves against an
    in-memory job map (a missing id raises ``NoSuchJobError``, mirroring an
    evicted job hash)."""

    def fake_fetch(job_id, connection=None, serializer=None):
        if job_id in jobs_by_id:
            return jobs_by_id[job_id]
        raise NoSuchJobError(job_id)

    monkeypatch.setattr(gov.Job, "fetch", staticmethod(fake_fetch))
    monkeypatch.setattr(
        gov.Job,
        "exists",
        staticmethod(lambda job_id, connection=None: job_id in jobs_by_id),
    )


def _patch_registry(monkeypatch, cls_name, ids, spy=None):
    """Replace one registry class's ``get_job_ids`` with a bounded slice over a
    preset id list, recording the ``cleanup`` flag of every read."""
    import rq.registry as rqreg

    def fake(self, start=0, end=-1, desc=False, cleanup=True):
        if spy is not None:
            spy.setdefault("cleanup", []).append(cleanup)
        if end == -1:
            return list(ids[start:])
        return list(ids[start : end + 1])

    monkeypatch.setattr(getattr(rqreg, cls_name), "get_job_ids", fake)


class TestProblemTasksService:
    LANE = "storage.default.9a3b.maintenance"

    def _conn(self, monkeypatch):
        conn = FakeRedis(rq_queues=[self.LANE])
        monkeypatch.setattr(gov, "_connect_redis", lambda: conn)
        monkeypatch.setattr(
            gov.CommonCategories,
            "get_id_name_map",
            staticmethod(lambda: {"9a3b": "FP"}),
        )
        return conn

    # (a) bounded — a registry with >cap ids sets truncated
    def test_bounded_truncated(self, monkeypatch, clean_gov_caches):
        now = datetime.now(timezone.utc)
        ids = [f"f{i}" for i in range(5)]
        jobs = {
            jid: _ProblemJob(
                jid, status="failed", enqueued_at=now - timedelta(seconds=10 * n)
            )
            for n, jid in enumerate(ids)
        }
        self._conn(monkeypatch)
        _install_jobs(monkeypatch, jobs)
        _patch_registry(monkeypatch, "FailedJobRegistry", ids)
        data = gov.AdminQueuesService.list_problem_tasks(
            "failed", None, None, None, 2, 0
        )
        assert data["truncated"] is True
        assert data["count"] == 2
        assert all(
            t["kind"] == "failed" and t["retryable"] is True and t["cancelable"] is True
            for t in data["tasks"]
        )

    # (b) stuck_running keeps only over-timeout jobs and parses composite ids
    def test_stuck_running_over_timeout_and_composite(
        self, monkeypatch, clean_gov_caches
    ):
        now = datetime.now(timezone.utc)
        jobs = {
            "jobA": _ProblemJob(
                "jobA",
                status="started",
                started_at=now - timedelta(seconds=100),
                timeout=10,
            ),
            "jobB": _ProblemJob(
                "jobB",
                status="started",
                started_at=now - timedelta(seconds=5),
                timeout=600,
            ),
        }
        self._conn(monkeypatch)
        _install_jobs(monkeypatch, jobs)
        # composite {job_id}:{execution_id} members must be parsed before fetch
        _patch_registry(monkeypatch, "StartedJobRegistry", ["jobA:exec1", "jobB:exec2"])
        data = gov.AdminQueuesService.list_problem_tasks(
            "stuck_running", None, None, None, 50, 0
        )
        assert {t["id"] for t in data["tasks"]} == {"jobA"}
        row = data["tasks"][0]
        assert row["kind"] == "stuck_running"
        assert row["cancelable"] is True and row["retryable"] is False

    # (c) deferred_orphan keeps only pending==False (orphans)
    def test_deferred_orphan_keeps_only_settled(self, monkeypatch, clean_gov_caches):
        now = datetime.now(timezone.utc)
        jobs = {
            "orphanA": _ProblemJob(
                "orphanA", status="deferred", enqueued_at=now - timedelta(seconds=60)
            ),
            "waitingB": _ProblemJob(
                "waitingB",
                status="deferred",
                enqueued_at=now - timedelta(seconds=60),
                meta={"dependency_ids": ["depB"]},
            ),
            # depB is still deferred -> waitingB is legitimately pending, NOT an
            # orphan, so it must be filtered out.
            "depB": _ProblemJob("depB", status="deferred"),
        }
        self._conn(monkeypatch)
        _install_jobs(monkeypatch, jobs)
        _patch_registry(monkeypatch, "DeferredJobRegistry", ["orphanA", "waitingB"])
        data = gov.AdminQueuesService.list_problem_tasks(
            "deferred_orphan", None, None, None, 50, 0
        )
        assert {t["id"] for t in data["tasks"]} == {"orphanA"}
        assert data["tasks"][0]["pending"] is False

    # (d) cleanup=False asserted on the registry read (a cleanup read is a WRITE)
    def test_registry_read_cleanup_false(self, monkeypatch, clean_gov_caches):
        now = datetime.now(timezone.utc)
        jobs = {"f0": _ProblemJob("f0", status="failed", enqueued_at=now)}
        self._conn(monkeypatch)
        _install_jobs(monkeypatch, jobs)
        spy = {}
        _patch_registry(monkeypatch, "FailedJobRegistry", ["f0"], spy=spy)
        gov.AdminQueuesService.list_problem_tasks("failed", None, None, None, 50, 0)
        assert spy["cleanup"] and all(c is False for c in spy["cleanup"])

    # (e) _tasks_from_source_ids dangling id skipped, listing survives
    def test_dangling_id_skipped_listing_survives(self, monkeypatch, clean_gov_caches):
        now = datetime.now(timezone.utc)
        jobs = {"good": _ProblemJob("good", status="failed", enqueued_at=now)}
        self._conn(monkeypatch)
        _install_jobs(monkeypatch, jobs)
        # "gone" has no job hash -> NoSuchJobError -> skipped, not aborting.
        _patch_registry(monkeypatch, "FailedJobRegistry", ["good", "gone"])
        data = gov.AdminQueuesService.list_problem_tasks(
            "failed", None, None, None, 50, 0
        )
        assert {t["id"] for t in data["tasks"]} == {"good"}

    # (f) exc_string only for a FAILED result
    def test_exc_string_only_for_failed_result(self, monkeypatch, clean_gov_caches):
        now = datetime.now(timezone.utc)
        jobs = {
            "withexc": _ProblemJob(
                "withexc",
                status="failed",
                enqueued_at=now,
                result=_ProblemResult(_RqResult.Type.FAILED, "Traceback: boom"),
            ),
            "noexc": _ProblemJob(
                "noexc",
                status="failed",
                enqueued_at=now - timedelta(seconds=1),
                result=_ProblemResult(_RqResult.Type.SUCCESSFUL, "ignored"),
            ),
        }
        self._conn(monkeypatch)
        _install_jobs(monkeypatch, jobs)
        _patch_registry(monkeypatch, "FailedJobRegistry", ["withexc", "noexc"])
        data = gov.AdminQueuesService.list_problem_tasks(
            "failed", None, None, None, 50, 0
        )
        by_id = {t["id"]: t for t in data["tasks"]}
        assert by_id["withexc"]["exc_string"] == "Traceback: boom"
        assert by_id["noexc"]["exc_string"] is None

    # (i) service degrades to 200 + empty on Redis down (never raises)
    def test_degrades_on_redis_down(self, monkeypatch, clean_gov_caches):
        from redis.exceptions import ConnectionError as RedisConnError

        def boom():
            raise RedisConnError("down")

        monkeypatch.setattr(gov, "_connect_redis", boom)
        data = gov.AdminQueuesService.list_problem_tasks("all", None, None, None, 50, 0)
        assert data["count"] == 0
        assert data["tasks"] == []
        assert data["truncated"] is False
        assert data["generated_at"] > 0


# ── (g) route param validation + (h) auth ──────────────────────────────────
class TestProblemTasksRoute:
    URL = "/admin/items/queues/tasks/problems"

    def _mock_ok(self, monkeypatch):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.list_problem_tasks",
            staticmethod(
                lambda *a, **k: {
                    "generated_at": 1751884800.0,
                    "truncated": False,
                    "count": 0,
                    "tasks": [],
                }
            ),
        )

    def test_admin_200(self, monkeypatch, test_client):
        self._mock_ok(monkeypatch)
        r = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_user_forbidden(self, monkeypatch, test_client):
        self._mock_ok(monkeypatch)
        r = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert r.status_code == 403

    def test_manager_forbidden(self, monkeypatch, test_client):
        self._mock_ok(monkeypatch)
        r = test_client(url=self.URL, jwt=MockJWT(role_id="manager"))
        assert r.status_code == 403

    # request-validation errors are mapped to 400 by the app (see
    # api/__init__.py:295) — accept 400/422 so the guard is mapping-agnostic.
    def test_bad_kind_rejected(self, test_client):
        r = test_client(url=self.URL + "?kind=bogus", jwt=MockJWT(role_id="admin"))
        assert r.status_code in (400, 422)

    def test_bad_tier_rejected(self, test_client):
        r = test_client(url=self.URL + "?tier=nope", jwt=MockJWT(role_id="admin"))
        assert r.status_code in (400, 422)

    def test_limit_too_high_rejected(self, test_client):
        r = test_client(url=self.URL + "?limit=201", jwt=MockJWT(role_id="admin"))
        assert r.status_code in (400, 422)

    def test_limit_zero_rejected(self, test_client):
        r = test_client(url=self.URL + "?limit=0", jwt=MockJWT(role_id="admin"))
        assert r.status_code in (400, 422)

    def test_negative_offset_rejected(self, test_client):
        r = test_client(url=self.URL + "?offset=-1", jwt=MockJWT(role_id="admin"))
        assert r.status_code in (400, 422)


# ══════════════════════════════════════════════════════════════════════════
#  Gauge-cache TTL vs the stats-go scrape period
# ══════════════════════════════════════════════════════════════════════════

_REPO_ROOT = Path(__file__).resolve().parents[6]
_ALLOY_METRICS = _REPO_ROOT / "docker" / "grafana-alloy" / "metrics.alloy"
_GOVERNOR_RULES = (
    _REPO_ROOT / "docker" / "vmalert" / "rules" / "storage_governor.rules.yml"
)


def _alloy_stats_go_scrape_period():
    """Seconds between two consecutive isard-stats-go scrapes, read from the
    Alloy config that performs them: the ``metrics_containers`` job, whose
    discovery keeps the isard-stats-go container."""
    if not _ALLOY_METRICS.is_file():
        pytest.skip(f"{_ALLOY_METRICS} not available in this test environment")
    config = _ALLOY_METRICS.read_text()

    discovery = re.search(
        r'discovery\.relabel "containers_with_metrics"\s*\{(.*?)\n\}', config, re.S
    )
    assert discovery, "containers_with_metrics discovery block not found"
    assert "stats-go" in discovery.group(
        1
    ), "isard-stats-go is no longer discovered by the metrics_containers job"

    scrape = re.search(
        r'prometheus\.scrape "metrics_containers"\s*\{(.*?)\n\}', config, re.S
    )
    assert scrape, "metrics_containers scrape block not found"
    interval = re.search(r'scrape_interval\s*=\s*"(\d+)s"', scrape.group(1))
    assert interval, "metrics_containers has no explicit scrape_interval"
    return int(interval.group(1))


def _governor_data_stale_threshold():
    """The ``data_age_seconds`` ceiling above which GovernorDataStale warns."""
    if not _GOVERNOR_RULES.is_file():
        pytest.skip(f"{_GOVERNOR_RULES} not available in this test environment")
    threshold = re.search(
        r"isardvdi_storage_governor_data_age_seconds\s*>\s*(\d+)",
        _GOVERNOR_RULES.read_text(),
    )
    assert threshold, "GovernorDataStale threshold not found"
    return int(threshold.group(1))


class TestGaugeCacheTtlVsScrapePeriod:
    """The stats-go ``storage_governor`` collector is the only automated caller
    of ``get_governor``, and it calls it exactly once per Alloy scrape. A TTL
    that does not outlive the scrape period therefore never serves a hit — every
    scrape recomputes — so the cache would be pure bookkeeping. These caches must
    outlive one scrape, while staying under the payload-age ceiling the
    GovernorDataStale alert enforces (a warm serve reports its true age)."""

    @pytest.mark.parametrize("cache_name", ["governor_cache", "category_names_cache"])
    def test_collector_driven_cache_outlives_one_scrape(self, cache_name):
        cache = getattr(queues_service, cache_name)
        assert cache.ttl > _alloy_stats_go_scrape_period()

    def test_governor_cache_stays_under_the_stale_payload_threshold(self):
        assert queues_service.governor_cache.ttl < _governor_data_stale_threshold()

    @pytest.mark.parametrize("cache_name", ["backlog_cache", "problem_tasks_cache"])
    def test_operator_driven_caches_stay_short(self, cache_name):
        """Nothing scrapes these two endpoints; an operator refreshing them right
        after a retry or a cancel must not be served a scrape-period-old list."""
        cache = getattr(queues_service, cache_name)
        assert cache.ttl <= _alloy_stats_go_scrape_period()


# ── a worker-hash read failure must not read as "every worker dead" ─────────
class TestWorkerHashReadFailureIsDistinguishable:
    """A PARTIAL Redis failure — PING alive, the worker-hash HGETALL pipeline
    read fails — must not paint every worker up=false while redis reads healthy.
    That combination is what fires WorkerHeartbeatLost against a LIVE Redis. The
    read must propagate so the governor degrades to its honest posture instead.

    NoStorageWorkers is deliberately NOT covered by that: it runs
    noDataState=Alerting, so it pages on an empty worker_up series by design.
    What this pins down is the lie — redis.up=true alongside a dead fleet."""

    class _WorkerPipeBoom(FakeRedis):
        """PING/INFO and the lane (LLEN) pipeline work; only the worker-hash
        HGETALL pipeline raises."""

        def pipeline(self):
            class _Boom(_FakePipeline):
                def execute(self_inner):
                    if any(
                        name == "hgetall"
                        and args
                        and str(args[0]).startswith("rq:worker:")
                        for name, args, _ in self_inner._ops
                    ):
                        from redis.exceptions import ConnectionError as RedisConnError

                        raise RedisConnError("worker-hash pipeline down")
                    return _FakePipeline.execute(self_inner)

            return _Boom(self)

    def _conn(self):
        now = datetime.now(timezone.utc)
        return self._WorkerPipeBoom(
            sets={"rq:workers": {b"rq:worker:storage.default.maintenance.w1"}},
            hashes={
                "rq:worker:storage.default.maintenance.w1": {
                    b"last_heartbeat": _utc(now).encode(),
                    b"queues": b"storage.default.maintenance",
                    b"state": b"busy",
                },
            },
        )

    def test_worker_health_rows_propagates_the_read_failure(self):
        # The specific error, not just "something raised": a bare Exception
        # match would also pass on a broken double, proving nothing.
        from redis.exceptions import ConnectionError as RedisConnError

        with pytest.raises(RedisConnError):
            gov.AdminQueuesService._worker_health_rows(self._conn())

    def test_governor_never_reports_redis_up_with_every_worker_dead(
        self, monkeypatch, clean_gov_caches
    ):
        conn = self._conn()
        monkeypatch.setattr(gov, "_connect_redis", lambda: conn)
        data = gov.AdminQueuesService.get_governor()  # must NOT raise
        # The condition WorkerHeartbeatLost keys off: redis healthy AND every
        # worker dead must never coexist. Without the fix redis.up=true while
        # the one live worker reads up=false.
        assert not (data["redis"]["up"] and data["workers"]) or any(
            w["up"] for w in data["workers"]
        ), (
            "redis.up=true while every worker reads up=false — a partial Redis "
            "read failure is firing WorkerHeartbeatLost against a live Redis"
        )
        # And positively: the degraded posture the fix actually produces, so a
        # future change that swallows the read again cannot pass this vacuously.
        assert data["redis"]["up"] is False
        assert data["workers"] == []
