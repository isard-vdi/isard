# SPDX-License-Identifier: AGPL-3.0-or-later

"""A base's descendants, by database row or only by qcow2 header, guard it on the live stack."""

from __future__ import annotations

import os
import uuid
from typing import Iterator

import pytest

from .helpers.client import IsardClient
from .helpers.waits import poll_for

rethinkdb = pytest.importorskip("rethinkdb")
from rethinkdb import r  # noqa: E402

pytestmark = pytest.mark.real

READY_TIMEOUT = int(os.environ.get("E2E_CREATE_TIMEOUT", "180"))
TASK_TIMEOUT = int(os.environ.get("E2E_DIG_HOLES_TIMEOUT", "180"))
TASK_DONE = {"finished", "failed", "canceled"}
OWNER = "local-default-admin-admin"
STALE_RECLAIMABLE = 123 * 1024 * 1024


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


def _row(conn, storage_id: str) -> dict:
    return r.table("storage").get(storage_id).run(conn) or {}


def _delete(client: IsardClient, conn, storage_id: str):
    poll_for(
        lambda: _row(conn, storage_id),
        accept=lambda s: s.get("status") != "maintenance",
        timeout=TASK_TIMEOUT,
        interval=2.0,
        message=f"storage {storage_id} stayed in maintenance",
    )
    resp = client.raw("DELETE", f"/api/v4/item/storage/{storage_id}")
    if resp.status_code < 400:
        poll_for(
            lambda: _row(conn, storage_id),
            accept=lambda s: s.get("status") in (None, "deleted"),
            timeout=TASK_TIMEOUT,
            interval=2.0,
            message=f"storage {storage_id} was not deleted",
        )
    return resp


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
        created.append(parent)
        child = _create_disk(admin_client, parent=parent)
        created.insert(0, child)
        yield parent, child
    finally:
        if len(created) == 2:
            r.table("storage").get(created[0]).update({"parent": created[1]}).run(conn)
        for storage_id in created:
            if _row(conn, storage_id).get("status") not in (None, "deleted"):
                try:
                    _delete(admin_client, conn, storage_id)
                except Exception:
                    pass


def test_a_child_only_the_qcow2_header_knows_guards_its_base(
    admin_client: IsardClient, conn, parent_and_child
):
    """On main: the base is sparsified, moved and deleted under a header-only child."""
    parent, child = parent_and_child
    r.table("storage").get(child).update({"parent": None}).run(conn)
    url = f"/api/v4/item/storage/{parent}"
    directory = _row(conn, parent)["directory_path"]

    for method, path, body in (
        ("PUT", f"{url}/sparsify/priority/default", None),
        ("PUT", f"{url}/move/by-path", {"dest_path": f"{directory}/e2e_moved"}),
        ("DELETE", url, None),
    ):
        resp = admin_client.raw(method, path, json=body)
        assert resp.status_code == 428, f"{method} {path}: wanted 428, {_said(resp)}"
        assert _code(resp) == "storage_has_children", f"{path}: {_said(resp)}"
        assert _row(conn, parent)["status"] == "ready", _row(conn, parent)

    r.table("storage").get(child).update({"parent": parent}).run(conn)
    resp = _delete(admin_client, conn, child)
    assert resp.status_code < 400, f"child delete: {_said(resp)}"
    resp = _delete(admin_client, conn, parent)
    assert (
        resp.status_code < 400
    ), f"with its child gone the base deletes: {_said(resp)}"


@pytest.fixture
def descendant_desktop(conn, parent_and_child, test_namespace) -> Iterator[str]:
    _, child = parent_and_child
    domain_id = f"{test_namespace}dig_gate_{uuid.uuid4().hex[:8]}"
    r.table("domains").insert(
        {
            "id": domain_id,
            "kind": "desktop",
            "name": domain_id,
            "status": "Started",
            "user": OWNER,
            "create_dict": {"hardware": {"disks": [{"storage_id": child}]}},
        }
    ).run(conn)
    try:
        yield domain_id
    finally:
        r.table("domains").get(domain_id).delete().run(conn)


def test_a_base_is_dug_only_once_every_descendant_is_stopped(
    admin_client: IsardClient, conn, parent_and_child, descendant_desktop
):
    """On main: the dig is accepted while a descendant runs, and the zeros figure stays stale."""
    parent, _ = parent_and_child
    url = f"/api/v4/item/storage/{parent}/dig-holes/priority/low"

    resp = admin_client.raw("PUT", url)
    assert resp.status_code == 428, f"wanted 428, got {_said(resp)}"
    assert _code(resp) == "storage_descendants_not_stopped", _said(resp)
    batch = admin_client.put(
        "/api/v4/items/storage/dig-holes", json_body={"ids": [parent]}
    )
    assert batch["queued"] == 0, batch
    assert batch["results"][0]["task_id"] is None, batch
    assert (
        batch["results"][0]["description_code"] == "storage_descendants_not_stopped"
    ), batch
    assert _row(conn, parent)["status"] == "ready", _row(conn, parent)

    r.table("domains").get(descendant_desktop).update({"status": "Stopped"}).run(conn)
    stale_at = 1_000_000_000
    r.table("storage").get(parent).update(
        {
            "health": {
                "checks": {
                    "zeros": {
                        "at": stale_at,
                        "result": "ok",
                        "reclaimable_bytes": STALE_RECLAIMABLE,
                        "actual_size_at_scan": STALE_RECLAIMABLE,
                    }
                }
            }
        }
    ).run(conn)
    resp = poll_for(
        lambda: admin_client.raw("PUT", url),
        accept=lambda x: _code(x) != "storage_pending_task",
        timeout=TASK_TIMEOUT,
        interval=2.0,
        message=f"storage {parent} kept a pending task",
    )
    assert resp.status_code == 200, f"all descendants stopped: {_said(resp)}"
    task = _wait_task(admin_client, resp.json()["task_id"])
    assert task["status"] == "finished", task
    assert task["result"]["verified"] is True, task

    row = poll_for(
        lambda: _row(conn, parent),
        accept=lambda s: s.get("status") == "ready"
        and ((s.get("health") or {}).get("checks") or {}).get("zeros", {}).get("at", 0)
        > stale_at,
        timeout=TASK_TIMEOUT,
        interval=2.0,
        message=f"storage {parent} kept the zeros figure from before the dig",
    )
    assert row["health"]["checks"]["zeros"]["reclaimable_bytes"] == 0, row["health"]
