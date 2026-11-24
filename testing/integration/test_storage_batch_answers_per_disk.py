# SPDX-License-Identifier: AGPL-3.0-or-later

"""Every mass disk action answers for each disk, on the live stack."""

from __future__ import annotations

import os
from typing import Iterator

import pytest

from .helpers.client import IsardClient
from .helpers.waits import poll_for

rethinkdb = pytest.importorskip("rethinkdb")
from rethinkdb import r  # noqa: E402

pytestmark = pytest.mark.real

READY_TIMEOUT = int(os.environ.get("E2E_CREATE_TIMEOUT", "180"))
TASK_TIMEOUT = int(os.environ.get("E2E_STORAGE_TASK_TIMEOUT", "120"))
TASK_DONE = {"finished", "failed", "canceled"}
OWNER = "local-default-admin-admin"
NO_SUCH_STATUS = "e2e-no-disk-has-this-status"


def _connect():
    host = os.environ.get("RETHINKDB_HOST", "isard-db")
    port = int(os.environ.get("RETHINKDB_PORT", "28015"))
    try:
        return r.connect(
            host=host, port=port, db=os.environ.get("RETHINKDB_DB", "isard")
        )
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"RethinkDB not reachable at {host}:{port}: {exc}")


def _said(resp) -> str:
    return f"HTTP {resp.status_code}: {resp.text[:300]}"


@pytest.mark.parametrize("action", ["find", "sparsify", "status"])
def test_a_batch_by_ids_reports_each_refused_disk(
    admin_client: IsardClient, action: str
):
    """On main: 204, and sparsify drops them in silence while find aborts on the first."""
    ids = ["does-not-exist-1", "does-not-exist-2"]
    resp = admin_client.raw("PUT", f"/api/v4/items/storage/{action}", json={"ids": ids})
    assert resp.status_code == 200, f"wanted 200 with a body, got {_said(resp)}"
    body = resp.json()
    assert body["queued"] == 0, body
    assert [x["storage_id"] for x in body["results"]] == ids, body
    assert all(x["task_id"] is None for x in body["results"]), body
    assert all(x["description_code"] for x in body["results"]), body


@pytest.mark.parametrize(
    "path",
    [
        "/api/v4/items/storage/find/{status}",
        "/api/v4/items/storage/sparsify/{status}",
        "/api/v4/items/storage/status/{status}",
        "/api/v4/admin/items/storage/zero-scan/{status}",
        "/api/v4/admin/items/storage/check/{status}",
    ],
)
def test_a_batch_by_status_answers_at_once_with_its_count(
    admin_client: IsardClient, path: str
):
    """On main: 204 or a bare {queued} count, after queueing every disk in the request."""
    resp = admin_client.raw("PUT", path.format(status=NO_SUCH_STATUS))
    assert resp.status_code == 202, f"wanted 202 with a count, got {_said(resp)}"
    assert resp.json() == {"status": NO_SUCH_STATUS, "accepted": 0}, _said(resp)


@pytest.fixture
def ready_disk(admin_client: IsardClient) -> Iterator[str]:
    body = admin_client.post(
        "/api/v4/item/storage/priority/default",
        json_body={
            "usage": "desktop",
            "storage_type": "qcow2",
            "parent": "",
            "size": "1G",
            "user_id": OWNER,
        },
    )
    storage_id = body["storage_id"]
    conn = _connect()
    try:
        poll_for(
            lambda: r.table("storage").get(storage_id).run(conn) or {},
            accept=lambda s: s.get("status") == "ready",
            timeout=READY_TIMEOUT,
            interval=2.0,
            message=f"storage {storage_id} never reached ready",
        )
        yield storage_id
    finally:
        try:
            poll_for(
                lambda: r.table("storage").get(storage_id).run(conn) or {},
                accept=lambda s: s.get("status") != "maintenance",
                timeout=TASK_TIMEOUT,
                interval=2.0,
            )
        except TimeoutError:
            pass
        admin_client.raw("DELETE", f"/api/v4/item/storage/{storage_id}")
        conn.close()


def test_a_batch_find_rides_the_bulk_lane_and_finishes(
    admin_client: IsardClient, ready_disk: str
):
    """On main: no per-disk task id, and the find rides the foreground lane."""
    body = poll_for(
        lambda: admin_client.put(
            "/api/v4/items/storage/find", json_body={"ids": [ready_disk]}
        ),
        accept=lambda b: (b or {}).get("results", [{}])[0].get("description_code")
        != "storage_pending_task",
        timeout=TASK_TIMEOUT,
        interval=2.0,
        message=f"storage {ready_disk} kept a pending task",
    )
    assert isinstance(body, dict) and "results" in body, body
    assert body["queued"] == 1, body
    task_id = body["results"][0]["task_id"]
    assert task_id, body
    task = admin_client.get(f"/api/v4/task/{task_id}")
    assert (task.get("queue") or "").endswith(".bulk"), task
    task = poll_for(
        lambda: admin_client.get(f"/api/v4/task/{task_id}"),
        accept=lambda t: (t or {}).get("status") in TASK_DONE,
        timeout=TASK_TIMEOUT,
        interval=2.0,
        message=f"bulk find {task_id} did not end: no consumer on the bulk lane?",
    )
    assert task["status"] == "finished", task
