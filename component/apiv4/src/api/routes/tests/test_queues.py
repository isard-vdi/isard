#
#   Copyright © 2025 IsardVDI
#
#   This file is part of IsardVDI.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Route tests for :mod:`api.routes.admin.queues`.

Covers the admin queues endpoints that replaced the T1/queues v3_compat
shims (``/queues``, ``/queues/consumers``, ``/queues/old_tasks/config``
and the three ``/queues/old_tasks/config/*`` PUT endpoints). All
handlers are on ``admin_router`` so ``MockJWT()`` is enough.
"""

from api.routes.tests.helpers import MockJWT


def test_admin_queues_list(monkeypatch, test_client):
    jwt = MockJWT()
    # Real ``AdminQueuesService.get_queues`` returns ``list[{id, queued,
    # started, finished, failed, deferred, scheduled, canceled}]``;
    # the response_model now enforces that.
    stub = [
        {
            "id": "core",
            "queued": 3,
            "started": 1,
            "finished": 0,
            "failed": 0,
            "deferred": 0,
            "scheduled": 0,
            "canceled": 0,
        },
        {
            "id": "storage.default",
            "queued": 0,
            "started": 0,
            "finished": 0,
            "failed": 0,
            "deferred": 0,
            "scheduled": 0,
            "canceled": 0,
        },
    ]
    monkeypatch.setattr(
        "api.services.admin.queues.AdminQueuesService.get_queues",
        staticmethod(lambda: stub),
    )

    response = test_client(url="/admin/queues", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert {row["id"] for row in body} == {"core", "storage.default"}


def test_admin_queues_consumers(monkeypatch, test_client):
    jwt = MockJWT()
    # Real ``AdminQueuesService.get_consumers`` returns
    # ``list[{id, queue, queue_id, priority_id, priority, subscribers,
    # status}]`` (worker rows after _workers_with_subscribers); the
    # response_model now enforces that.
    stub = [
        {
            "id": "worker-1",
            "queue": "core",
            "queue_id": None,
            "priority_id": None,
            "priority": None,
            "subscribers": [],
            "status": "ok",
        },
        {
            "id": "worker-2",
            "queue": "storage",
            "queue_id": "default",
            "priority_id": "default",
            "priority": 2,
            "subscribers": ["sub-1"],
            "status": "ok",
        },
    ]
    monkeypatch.setattr(
        "api.services.admin.queues.AdminQueuesService.get_consumers",
        staticmethod(lambda: stub),
    )

    response = test_client(url="/admin/queues/consumers", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert {row["id"] for row in body} == {"worker-1", "worker-2"}


def test_admin_queues_get_old_tasks_config(monkeypatch, test_client):
    jwt = MockJWT()
    stub = {
        "older_than": 604800,
        "queue_registries": ["failed"],
        "enabled": True,
    }
    monkeypatch.setattr(
        "api.services.admin.queues.AdminQueuesService.get_auto_delete_config",
        staticmethod(lambda: stub),
    )

    response = test_client(url="/admin/queues/old_tasks/config", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_admin_queues_set_old_tasks_max_time(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []

    def fake_set_max_time(max_time):
        calls.append(max_time)
        return {"older_than": max_time}

    monkeypatch.setattr(
        "api.services.admin.queues.AdminQueuesService.set_max_time",
        staticmethod(fake_set_max_time),
    )

    response = test_client(
        url="/admin/queues/old_tasks/config/max_time/1209600",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"older_than": 1209600}
    assert calls == [1209600]


def test_admin_queues_set_queue_registries(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_set(registries):
        captured["registries"] = registries
        return {"queue_registries": registries}

    monkeypatch.setattr(
        "api.services.admin.queues.AdminQueuesService.set_queue_registries",
        staticmethod(fake_set),
    )

    response = test_client(
        url="/admin/queues/old_tasks/config/queue_registries",
        method="PUT",
        body={"queue_registries": ["failed", "finished"]},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured == {"registries": ["failed", "finished"]}


def test_admin_queues_set_old_tasks_enabled(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []

    def fake_set(enabled):
        calls.append(enabled)
        return {"enabled": enabled}

    monkeypatch.setattr(
        "api.services.admin.queues.AdminQueuesService.set_auto_delete_enabled",
        staticmethod(fake_set),
    )

    response = test_client(
        url="/admin/queues/old_tasks/config/enabled",
        method="PUT",
        body={"enabled": False},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"enabled": False}
    assert calls == [False]
