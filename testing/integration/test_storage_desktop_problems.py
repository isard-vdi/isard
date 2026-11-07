# SPDX-License-Identifier: AGPL-3.0-or-later

"""A desktop's disk problems are reported, fixed from the desktop and cleared."""

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
FIX_TIMEOUT = int(os.environ.get("E2E_STORAGE_FIX_TIMEOUT", "180"))
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


@pytest.fixture
def stopped_desktop(admin_client: IsardClient, test_namespace: str, request):
    templates = derivable(
        expect(admin_get_templates.sync_detailed(client=admin_client.apiv4()))
    )
    assert templates, "no derivable template seeded"
    desktop_id = created_id(
        create_desktop.sync_detailed(
            client=admin_client.apiv4(),
            body=CreateDesktopRequest(
                template_id=templates[0].id,
                name=f"{test_namespace}{request.node.name[5:25]}",
                description="",
            ),
        )
    )
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped"}, max_wait=CREATE_TIMEOUT
    )
    details = expect(
        get_desktop_details.sync_detailed(
            desktop_id=desktop_id, client=admin_client.apiv4()
        )
    )
    return desktop_id, details.disks[0].id


def _problems(admin_client, desktop_id, storage_id):
    report = admin_client.get(f"/api/v4/item/desktop/{desktop_id}/storage-problems")
    disk = next(d for d in report["disks"] if d["storage_id"] == storage_id)
    return {p["code"]: p for p in disk["problems"]}


@pytest.mark.real
@pytest.mark.slow
def test_a_leak_mark_is_reported_fixed_from_the_desktop_and_cleared(
    admin_client: IsardClient, stopped_desktop
):
    desktop_id, storage_id = stopped_desktop
    assert _problems(admin_client, desktop_id, storage_id) == {}

    conn = _connect()
    try:
        r.table("storage").get(storage_id).update(
            {
                "pending_actions": {
                    "repair_leaks": {
                        "since": int(time.time()),
                        "found_by": "integration-test",
                        "detail": {"leaks": 1},
                    }
                }
            }
        ).run(conn)

        leak = _problems(admin_client, desktop_id, storage_id)["storage_leaks"]
        assert leak["fix"] == "repair_leaks", leak
        assert leak["blocks_start"] is False, leak
        assert leak["mode"] == "quick", leak
        assert leak["allowed"] is True, leak
        assert leak["pending_since"], leak

        resp = admin_client.raw(
            "PUT",
            f"/api/v4/item/desktop/{desktop_id}/storage/{storage_id}/fix/check",
        )
        assert resp.status_code == 428, resp.text
        assert resp.json()["description_code"] == "storage_fix_not_needed"

        url = f"/api/v4/item/desktop/{desktop_id}/storage/{storage_id}/fix"
        # a fresh disk is still measured by the task its creation queued
        resp = poll_for(
            lambda: admin_client.raw("PUT", f"{url}/repair_leaks"),
            accept=lambda x: x.status_code != 428
            or x.json().get("description_code") != "storage_fix_in_progress",
            timeout=FIX_TIMEOUT,
            interval=2.0,
            message=f"storage {storage_id} kept a task in progress",
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["task_id"], body
        task = poll_for(
            lambda: admin_client.get(f"/api/v4/task/{body['task_id']}"),
            accept=lambda t: (t or {}).get("status") in TASK_DONE,
            timeout=FIX_TIMEOUT,
            interval=2.0,
            message=f"repair task {body['task_id']} did not end",
        )
        assert task["status"] == "finished", task

        poll_for(
            lambda: r.table("storage").get(storage_id).run(conn),
            accept=lambda s: s["status"] == "ready"
            and "repair_leaks" not in (s.get("pending_actions") or {}),
            timeout=FIX_TIMEOUT,
            interval=2.0,
            message=f"storage {storage_id} kept its leak mark",
        )
        assert _problems(admin_client, desktop_id, storage_id) == {}
        admin_client.poll_desktop_status(desktop_id, want={"Stopped"}, max_wait=60)
    finally:
        conn.close()


@pytest.mark.real
def test_the_repairs_of_a_desktop_run_only_once_an_admin_turns_them_on(
    admin_client: IsardClient, stopped_desktop
):
    desktop_id, _ = stopped_desktop
    sweep = "/api/v4/admin/storage/sweep/config"
    before = admin_client.get(sweep)["desktop_disk_repairs"]
    url = f"/api/v4/item/desktop/{desktop_id}/storage-problems"
    try:
        admin_client.put(sweep, json_body={"desktop_disk_repairs": False})
        resp = admin_client.raw("PUT", url)
        assert resp.status_code == 428, resp.text
        assert resp.json()["description_code"] == "storage_desktop_repairs_disabled"

        admin_client.put(sweep, json_body={"desktop_disk_repairs": True})
        resp = admin_client.raw("PUT", url)
        assert resp.status_code == 200, resp.text
        assert resp.json()["quick_fixes"] == [], resp.text
    finally:
        admin_client.put(sweep, json_body={"desktop_disk_repairs": before})


@pytest.mark.real
def test_a_disk_of_another_desktop_is_not_found(
    admin_client: IsardClient, stopped_desktop
):
    desktop_id, _ = stopped_desktop
    resp = admin_client.raw(
        "PUT",
        f"/api/v4/item/desktop/{desktop_id}/storage/does-not-exist/fix/check",
    )
    assert resp.status_code == 404, resp.text
