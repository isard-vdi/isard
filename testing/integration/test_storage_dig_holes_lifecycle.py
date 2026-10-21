# SPDX-License-Identifier: AGPL-3.0-or-later

"""dig-holes goes from the API through the storage worker and back to the row."""

from __future__ import annotations

import os
import shutil
import subprocess

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
DIG_TIMEOUT = int(os.environ.get("E2E_DIG_HOLES_TIMEOUT", "180"))
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


def _in_storage(*argv: str) -> str | None:
    if shutil.which("docker") is None:
        return None
    try:
        out = subprocess.run(
            ["docker", "exec", "isard-storage", *argv],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout


def _sha256(path: str) -> str | None:
    out = _in_storage("sha256sum", path)
    return out.split()[0] if out else None


def _inflate(path: str) -> None:
    # same bytes, but every zero block becomes allocated
    _in_storage(
        "sh",
        "-c",
        f"dd if={path} of={path}.inflate bs=1M status=none && "
        f"dd if={path}.inflate of={path} bs=1M conv=notrunc status=none && "
        f"rm -f {path}.inflate",
    )


@pytest.mark.real
@pytest.mark.slow
def test_dig_holes_keeps_the_content_and_hands_the_disk_back(
    admin_client: IsardClient, test_namespace: str
):
    templates = derivable(
        expect(admin_get_templates.sync_detailed(client=admin_client.apiv4()))
    )
    assert templates, "no derivable template seeded"
    desktop_id = created_id(
        create_desktop.sync_detailed(
            client=admin_client.apiv4(),
            body=CreateDesktopRequest(
                template_id=templates[0].id,
                name=f"{test_namespace}dig_holes",
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
    storage_id = details.disks[0].id

    conn = _connect()
    try:
        row = r.table("storage").get(storage_id).run(conn)
        path = f"{row['directory_path']}/{storage_id}.{row.get('type', 'qcow2')}"
        _inflate(path)
        digest = _sha256(path)

        url = f"/api/v4/item/storage/{storage_id}/dig-holes/priority/default"
        # a fresh disk is still measured by the task its creation queued
        resp = poll_for(
            lambda: admin_client.raw("PUT", f"{url}?verify=true"),
            accept=lambda x: x.status_code != 428
            or x.json().get("description_code") != "storage_pending_task",
            timeout=DIG_TIMEOUT,
            interval=2.0,
            message=f"storage {storage_id} kept a pending task",
        )
        assert resp.status_code == 200, resp.text
        task_id = resp.json()["task_id"]
        task = poll_for(
            lambda: admin_client.get(f"/api/v4/task/{task_id}"),
            accept=lambda t: (t or {}).get("status") in TASK_DONE,
            timeout=DIG_TIMEOUT,
            interval=2.0,
            message=f"dig_holes task {task_id} did not end",
        )
        assert task["status"] == "finished", task
        result = task["result"]
        assert result["verified"] is True, result
        assert result["after"] <= result["before"], result
        assert result["reclaimed"] == result["before"] - result["after"], result

        row = poll_for(
            lambda: r.table("storage").get(storage_id).run(conn),
            accept=lambda s: s["status"] == "ready"
            and (s.get("qemu-img-info") or {}).get("actual-size") == result["after"],
            timeout=DIG_TIMEOUT,
            interval=2.0,
            message=f"storage {storage_id} did not come back measured",
        )
        assert "dig_holes" not in (row.get("pending_actions") or {})
        admin_client.poll_desktop_status(desktop_id, want={"Stopped"}, max_wait=60)

        if digest is not None:
            assert _sha256(path) == digest, "dig_holes changed what the disk reads"
    finally:
        conn.close()


@pytest.mark.real
def test_dig_holes_refuses_an_unknown_priority(admin_client: IsardClient):
    resp = admin_client.raw(
        "PUT", "/api/v4/item/storage/does-not-exist/dig-holes/priority/urgent"
    )
    assert resp.status_code == 400, resp.text


def _template_disk(admin_client: IsardClient, conn) -> str:
    templates = derivable(
        expect(admin_get_templates.sync_detailed(client=admin_client.apiv4()))
    )
    assert templates, "no derivable template seeded"
    domain = r.table("domains").get(templates[0].id).run(conn)
    return domain["create_dict"]["hardware"]["disks"][0]["storage_id"]


@pytest.mark.real
def test_dig_holes_refuses_a_templates_disk_and_says_why(admin_client: IsardClient):
    conn = _connect()
    try:
        storage_id = _template_disk(admin_client, conn)
        resp = admin_client.raw(
            "PUT", f"/api/v4/item/storage/{storage_id}/dig-holes/priority/low"
        )
        assert resp.status_code == 428, resp.text
        # a template's disk is read-only, and a template uses it: either says why
        assert resp.json()["description_code"] in {
            "storage_read_only",
            "storage_used_by_template",
        }, resp.text
        assert r.table("storage").get(storage_id)["status"].run(conn) == "ready"
    finally:
        conn.close()


@pytest.mark.real
def test_a_batch_dig_answers_each_id(admin_client: IsardClient):
    conn = _connect()
    try:
        storage_id = _template_disk(admin_client, conn)
        body = admin_client.put(
            "/api/v4/items/storage/dig-holes",
            json_body={"ids": [storage_id, "does-not-exist"]},
        )
        assert body["queued"] == 0, body
        assert [x["storage_id"] for x in body["results"]] == [
            storage_id,
            "does-not-exist",
        ]
        assert all(x["description_code"] for x in body["results"]), body
        assert all(x["task_id"] is None for x in body["results"]), body
    finally:
        conn.close()
