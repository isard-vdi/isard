# SPDX-License-Identifier: AGPL-3.0-or-later

"""A disk repair goes from the API through the storage worker and back to the row."""

from __future__ import annotations

import os
import time

import pytest
from isardvdi_apiv4_client.api.role_manager import admin_get_templates
from isardvdi_apiv4_client.api.role_user import create_desktop, get_desktop_details
from isardvdi_apiv4_client.models.create_desktop_request import CreateDesktopRequest

from .helpers.client import IsardClient
from .helpers.responses import created_id, expect
from .helpers.seed import derivable
from .helpers.waits import poll_for

rethinkdb = pytest.importorskip("rethinkdb")
from rethinkdb import r  # noqa: E402

CREATE_TIMEOUT = int(os.environ.get("E2E_CREATE_TIMEOUT", "180"))
REPAIR_TIMEOUT = int(os.environ.get("E2E_REPAIR_TIMEOUT", "180"))
TASK_DONE = {"finished", "failed", "canceled"}


def _connect():
    host = os.environ.get("RETHINKDB_HOST", "isard-db")
    port = int(os.environ.get("RETHINKDB_PORT", "28015"))
    try:
        return r.connect(
            host=host, port=port, db=os.environ.get("RETHINKDB_DB", "isard")
        )
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"RethinkDB not reachable at {host}:{port}: {exc}")


def _stopped_desktop_disk(client: IsardClient, name: str) -> tuple[str, str]:
    templates = derivable(
        expect(admin_get_templates.sync_detailed(client=client.apiv4()))
    )
    assert templates, "no derivable template seeded"
    desktop_id = created_id(
        create_desktop.sync_detailed(
            client=client.apiv4(),
            body=CreateDesktopRequest(
                template_id=templates[0].id, name=name, description=""
            ),
        )
    )
    client.poll_desktop_status(desktop_id, want={"Stopped"}, max_wait=CREATE_TIMEOUT)
    details = expect(
        get_desktop_details.sync_detailed(desktop_id=desktop_id, client=client.apiv4())
    )
    return desktop_id, details.disks[0].id


def _wait_task(client: IsardClient, task_id: str) -> dict:
    return poll_for(
        lambda: client.get(f"/api/v4/task/{task_id}"),
        accept=lambda t: (t or {}).get("status") in TASK_DONE,
        timeout=REPAIR_TIMEOUT,
        interval=2.0,
        message=f"task {task_id} did not end",
    )


def _wait_row(conn, storage_id: str, accept) -> dict:
    return poll_for(
        lambda: r.table("storage").get(storage_id).run(conn),
        accept=accept,
        timeout=REPAIR_TIMEOUT,
        interval=2.0,
        message=f"storage {storage_id} did not settle",
    )


@pytest.mark.real
def test_a_healthy_disk_without_a_mark_is_not_repaired(
    admin_client: IsardClient, test_namespace: str
):
    _, storage_id = _stopped_desktop_disk(admin_client, f"{test_namespace}repair_noop")
    resp = admin_client.raw("PUT", f"/api/v4/item/storage/{storage_id}/repair/leaks")
    assert resp.status_code == 428, resp.text
    assert "storage_not_repairable" in resp.text


@pytest.mark.real
@pytest.mark.slow
def test_a_leak_repair_clears_the_mark_and_hands_the_disk_back(
    admin_client: IsardClient, test_namespace: str
):
    conn = _connect()
    try:
        desktop_id, storage_id = _stopped_desktop_disk(
            admin_client, f"{test_namespace}repair_leaks"
        )
        now = int(time.time())
        r.table("storage").get(storage_id).update(
            {
                "pending_actions": {
                    "repair_leaks": {
                        "since": now,
                        "found_at": now,
                        "found_by": "integration test",
                        "detail": {},
                    }
                }
            }
        ).run(conn)

        task_id = admin_client.put(f"/api/v4/item/storage/{storage_id}/repair/leaks")[
            "task_id"
        ]
        task = _wait_task(admin_client, task_id)
        assert task["status"] == "finished", task
        assert task["result"]["ok"] is True, task["result"]

        row = _wait_row(
            conn,
            storage_id,
            lambda s: s["status"] == "ready"
            and "repair_leaks" not in (s.get("pending_actions") or {}),
        )
        assert not row.get("damage_reason")
        admin_client.poll_desktop_status(desktop_id, want={"Stopped"}, max_wait=60)
    finally:
        conn.close()


@pytest.mark.real
@pytest.mark.slow
def test_a_damaged_disk_that_checks_clean_comes_back_ready(
    admin_client: IsardClient, test_namespace: str
):
    conn = _connect()
    try:
        desktop_id, storage_id = _stopped_desktop_disk(
            admin_client, f"{test_namespace}repair_all"
        )
        r.table("storage").get(storage_id).update(
            {"status": "damaged", "damage_reason": "seeded by the integration test"}
        ).run(conn)
        r.table("domains").get(desktop_id).update({"status": "Failed"}).run(conn)

        task_id = admin_client.put(f"/api/v4/item/storage/{storage_id}/repair/all")[
            "task_id"
        ]
        assert _wait_task(admin_client, task_id)["status"] == "finished"

        row = _wait_row(conn, storage_id, lambda s: s["status"] == "ready")
        assert not row.get("damage_reason")
        admin_client.poll_desktop_status(desktop_id, want={"Stopped"}, max_wait=60)
    finally:
        conn.close()
