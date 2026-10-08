# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for POST /admin/storage/reconcile: admin-gated, apply from the body, count."""

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
    captured = {}
    _stub_enqueue(monkeypatch, captured)
    resp = test_client(url=URL, method="POST", jwt=ADMIN)
    assert resp.status_code == 200
    assert captured["apply"] is False
    assert resp.json()["apply"] is False


def test_apply_is_true_when_the_body_opts_in(monkeypatch, test_client):
    captured = {}
    _stub_enqueue(monkeypatch, captured)
    resp = test_client(url=URL, method="POST", jwt=ADMIN, body={"apply": True})
    assert resp.status_code == 200
    assert captured["apply"] is True
    assert resp.json()["apply"] is True


def test_apply_false_in_the_body_is_report_only(monkeypatch, test_client):
    captured = {}
    _stub_enqueue(monkeypatch, captured)
    resp = test_client(url=URL, method="POST", jwt=ADMIN, body={"apply": False})
    assert resp.status_code == 200
    assert captured["apply"] is False
    assert resp.json()["apply"] is False
