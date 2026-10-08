# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for POST /admin/storage/reconcile -- the admin endpoint the nightly
scheduler job calls to enqueue one ``reconcile_pool`` task per enabled storage
pool.

The per-pool enqueue and idempotency logic lives in
``StoragePoolsProcessed.enqueue_reconciles`` and is unit-tested there
(``_common`` ``test_reconcile_enqueue``). Here the ENDPOINT contract is pinned:
admin-gated, the ``apply`` flag is read from ``STORAGE_RECONCILE_APPLY`` (strict
``true``, default off so the nightly run is report-only unless an operator opts
in), and the response reports how many tasks were enqueued. The RQ/rethink
enqueue boundary is stubbed so no broker is needed.
"""

from tests.routes.helpers import MockJWT

URL = "/admin/storage/reconcile"
ADMIN = MockJWT(role_id="admin")


def _stub_enqueue(monkeypatch, captured, tasks=None):
    """Replace the enqueue boundary; record the ``apply`` it was called with."""
    if tasks is None:
        tasks = [{"pool": "p1", "path": "/isard", "task_id": "t1"}]

    def fake(apply=False, threshold=None, metrics_dir=None):
        captured["apply"] = apply
        return tasks

    monkeypatch.setattr(
        "api.services.admin.storage.StoragePoolsProcessed.enqueue_reconciles", fake
    )


def test_admin_enqueues_and_reports_the_count(monkeypatch, test_client):
    captured = {}
    _stub_enqueue(
        monkeypatch,
        captured,
        tasks=[
            {"pool": "p1", "path": "/isard", "task_id": "t1"},
            {"pool": "p2", "path": "/mnt/b", "task_id": "t2"},
        ],
    )
    resp = test_client(url=URL, method="POST", jwt=ADMIN)
    assert resp.status_code == 200
    assert resp.json()["enqueued"] == 2


def test_idempotent_count_reflects_pools_that_were_skipped(monkeypatch, test_client):
    # the endpoint reports the count actually enqueued, not the pool total
    captured = {}
    _stub_enqueue(
        monkeypatch, captured, tasks=[{"pool": "p2", "path": "/mnt/b", "task_id": "t2"}]
    )
    resp = test_client(url=URL, method="POST", jwt=ADMIN)
    assert resp.status_code == 200
    assert resp.json()["enqueued"] == 1


def test_user_is_forbidden(monkeypatch, test_client):
    captured = {}
    _stub_enqueue(monkeypatch, captured)
    resp = test_client(url=URL, method="POST", jwt=MockJWT(role_id="user"))
    assert resp.status_code == 403


def test_apply_is_false_by_default(monkeypatch, test_client):
    monkeypatch.delenv("STORAGE_RECONCILE_APPLY", raising=False)
    captured = {}
    _stub_enqueue(monkeypatch, captured)
    resp = test_client(url=URL, method="POST", jwt=ADMIN)
    assert resp.status_code == 200
    assert captured["apply"] is False
    assert resp.json()["apply"] is False


def test_apply_is_true_when_the_env_opts_in(monkeypatch, test_client):
    monkeypatch.setenv("STORAGE_RECONCILE_APPLY", "true")
    captured = {}
    _stub_enqueue(monkeypatch, captured)
    resp = test_client(url=URL, method="POST", jwt=ADMIN)
    assert resp.status_code == 200
    assert captured["apply"] is True
    assert resp.json()["apply"] is True


def test_apply_env_is_case_insensitive_but_strict(monkeypatch, test_client):
    # Any case of "true" opts in; anything else (1 / yes / empty) stays report-only
    # so a typo never silently starts auto-correcting disk sizes fleet-wide.
    captured = {}
    _stub_enqueue(monkeypatch, captured)

    monkeypatch.setenv("STORAGE_RECONCILE_APPLY", "TrUe")
    test_client(url=URL, method="POST", jwt=ADMIN)
    assert captured["apply"] is True

    monkeypatch.setenv("STORAGE_RECONCILE_APPLY", "1")
    test_client(url=URL, method="POST", jwt=ADMIN)
    assert captured["apply"] is False
