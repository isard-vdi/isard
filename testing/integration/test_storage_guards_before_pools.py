# SPDX-License-Identifier: AGPL-3.0-or-later

"""A disk's own refusal comes before any pool or lane lookup, on the live stack."""

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
TASK_TIMEOUT = int(os.environ.get("E2E_STORAGE_TASK_TIMEOUT", "180"))
TASK_DONE = {"finished", "failed", "canceled"}
OWNER = "local-default-admin-admin"


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


def _code(resp):
    try:
        return (resp.json() or {}).get("description_code")
    except ValueError:
        return None


def _create_disk(client: IsardClient, parent: str = "") -> str:
    body = client.post(
        "/api/v4/item/storage/priority/default",
        json_body={
            "usage": "desktop",
            "storage_type": "qcow2",
            "parent": parent,
            "size": "1G",
            "user_id": OWNER,
        },
    )
    storage_id = body["storage_id"]
    poll_for(
        lambda: client.raw(
            "GET", f"/api/v4/admin/item/storage/search-info/{storage_id}"
        ),
        accept=lambda x: x.status_code == 200 and x.json().get("status") == "ready",
        timeout=READY_TIMEOUT,
        interval=2.0,
        message=f"storage {storage_id} never reached ready",
    )
    return storage_id


def _wait_task(client: IsardClient, task_id: str) -> dict:
    return poll_for(
        lambda: client.get(f"/api/v4/task/{task_id}"),
        accept=lambda t: (t or {}).get("status") in TASK_DONE,
        timeout=TASK_TIMEOUT,
        interval=2.0,
        message=f"task {task_id} did not end",
    )


def _discard(client: IsardClient, conn, storage_ids: list[str]) -> None:
    """Delete children first, each gone before its parent is asked; never raises."""
    for storage_id in storage_ids:
        try:
            poll_for(
                lambda: r.table("storage").get(storage_id).run(conn) or {},
                accept=lambda s: s.get("status") != "maintenance",
                timeout=TASK_TIMEOUT,
                interval=2.0,
            )
            client.raw("DELETE", f"/api/v4/item/storage/{storage_id}")
            poll_for(
                lambda: r.table("storage").get(storage_id).run(conn) or {},
                accept=lambda s: s.get("status") in (None, "deleted"),
                timeout=TASK_TIMEOUT,
                interval=2.0,
            )
        except Exception:
            pass


@pytest.fixture
def conn():
    connection = _connect()
    yield connection
    connection.close()


@pytest.fixture
def parent_and_child(admin_client: IsardClient, conn) -> Iterator[tuple[str, str]]:
    created: list[str] = []
    try:
        parent = _create_disk(admin_client)
        created.insert(0, parent)
        child = _create_disk(admin_client, parent=parent)
        created.insert(0, child)
        yield parent, child
    finally:
        _discard(admin_client, conn, created)


@pytest.fixture
def new_pool(admin_client: IsardClient, test_namespace: str) -> Iterator[str]:
    pool_id = f"{test_namespace}guards_pool"
    resp = admin_client.raw(
        "POST",
        "/api/v4/storage-pool",
        json={
            "id": pool_id,
            "name": pool_id,
            "description": "",
            "mountpoint": f"/isard/storage_pools/{pool_id}",
        },
    )
    assert resp.status_code in (200, 201), f"pool create: {_said(resp)}"
    yield pool_id
    admin_client.raw("DELETE", f"/api/v4/storage-pool/{pool_id}")


def test_a_disk_without_a_parent_is_not_disconnected(
    admin_client: IsardClient, conn, parent_and_child
):
    """On main: 200, and a full rewrite of a disk with nothing to fold is queued."""
    parent, child = parent_and_child
    resp = admin_client.raw(
        "PUT", f"/api/v4/item/storage/{parent}/disconnect/priority/default"
    )
    assert resp.status_code == 428, f"wanted 428, got {_said(resp)}"
    assert _code(resp) == "storage_has_no_parent", _said(resp)
    row = r.table("storage").get(parent).run(conn)
    assert row["status"] == "ready", row

    resp = admin_client.raw(
        "PUT", f"/api/v4/item/storage/{child}/disconnect/priority/default"
    )
    assert resp.status_code == 200, f"a derived disk must disconnect: {_said(resp)}"
    task = _wait_task(admin_client, resp.json()["task_id"])
    assert task["status"] == "finished", task


def test_a_base_with_children_is_refused_before_the_destination(
    admin_client: IsardClient, conn, parent_and_child, new_pool
):
    """On main: 500 towards a pool without paths, and 409 conflict for to-path."""
    parent, _ = parent_and_child
    resp = admin_client.raw(
        "PUT",
        f"/api/v4/item/storage/{parent}/rsync/to-storage-pool",
        json={"destination_storage_pool_id": new_pool, "remove_source_file": False},
    )
    assert resp.status_code == 428, f"wanted 428, got {_said(resp)}"
    assert _code(resp) == "storage_has_children", _said(resp)

    directory = r.table("storage").get(parent)["directory_path"].run(conn)
    resp = admin_client.raw(
        "PUT",
        f"/api/v4/item/storage/{parent}/rsync/to-path",
        json={"destination_path": f"{directory}/{parent}-copy.qcow2"},
    )
    assert resp.status_code == 428, f"wanted 428, got {_said(resp)}"
    assert _code(resp) == "storage_has_children", _said(resp)
    assert r.table("storage").get(parent)["status"].run(conn) == "ready"


def test_a_movable_disk_to_a_pool_without_paths_is_refused_and_stays_ready(
    admin_client: IsardClient, conn, parent_and_child, new_pool
):
    """On main: 500 on the pool's null paths instead of a refusal naming the cause."""
    _, child = parent_and_child
    resp = admin_client.raw(
        "PUT",
        f"/api/v4/item/storage/{child}/rsync/to-storage-pool",
        json={"destination_storage_pool_id": new_pool, "remove_source_file": False},
    )
    assert resp.status_code in (400, 429), f"wanted 400/429, got {_said(resp)}"
    assert _code(resp) in (
        "storage_pool_usage_without_path",
        "storage_no_consumer_retry_later",
    ), _said(resp)
    assert r.table("storage").get(child)["status"].run(conn) == "ready"
