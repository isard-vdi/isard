# SPDX-License-Identifier: AGPL-3.0-or-later

"""Deletes keep running on a governed worker while the heavy cap is full."""

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
redis = pytest.importorskip("redis")
rq_job = pytest.importorskip("rq.job")
from rethinkdb import r  # noqa: E402

CREATE_TIMEOUT = int(os.environ.get("E2E_CREATE_TIMEOUT", "180"))
TASK_TIMEOUT = int(os.environ.get("E2E_RECLAIM_TIMEOUT", "300"))
# enough short heavy jobs to keep the maintenance queue busy while the deletes run
HEAVY_JOBS = int(os.environ.get("E2E_RECLAIM_HEAVY_JOBS", "8"))
DELETES = 3
CONFIG = "/api/v4/admin/item/queues/storage_scheduler/config"
GOVERNED_ROLES = ("storage-elastic:", "storage-template:")
FLOOR_ROLE = "storage-bgfloor:"  # ungoverned by design, it may take a delete too
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


def _redis():
    password = os.environ.get("REDIS_PASSWORD")
    if not password:
        pytest.skip("needs REDIS_PASSWORD to read the RQ jobs")
    return redis.Redis(
        host=os.environ.get("REDIS_HOST", "isard-redis"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        password=password,
    )


def _status(client: IsardClient, task_id: str) -> str | None:
    return (client.get(f"/api/v4/task/{task_id}") or {}).get("status")


def _assert_served_at_the_cap(workers: dict[str, str | None]) -> None:
    """Every delete ran on a pool worker, at least one of them governed."""
    names = [w or "" for w in workers.values()]
    assert all(w.startswith(GOVERNED_ROLES + (FLOOR_ROLE,)) for w in names), workers
    assert any(
        w.startswith(GOVERNED_ROLES) for w in names
    ), f"no governed worker served a delete at the cap: {workers}"


@pytest.mark.real
@pytest.mark.parametrize(
    "workers",
    [
        {
            "d1": "storage-elastic:a",
            "d2": "storage-elastic:b",
            "d3": "storage-template:c",
        },
        {
            "d1": "storage-bgfloor:a",
            "d2": "storage-elastic:b",
            "d3": "storage-elastic:c",
        },
    ],
)
def test_a_delete_on_the_floor_worker_is_accepted(workers):
    _assert_served_at_the_cap(workers)


@pytest.mark.real
@pytest.mark.parametrize(
    "workers",
    [
        {
            "d1": "storage-bgfloor:a",
            "d2": "storage-bgfloor:b",
            "d3": "storage-bgfloor:c",
        },
        {"d1": "storage-elastic:a", "d2": "storage-reserved:b", "d3": None},
    ],
)
def test_deletes_only_on_the_floor_or_off_the_pools_are_refused(workers):
    with pytest.raises(AssertionError):
        _assert_served_at_the_cap(workers)


def _drain(client: IsardClient, task_ids: list[str]) -> None:
    """Cancel the queued heavy jobs and wait for the rest, so none outlives the test."""
    for task_id in task_ids:
        if _status(client, task_id) not in TASK_DONE:
            client.raw("DELETE", f"/api/v4/task/{task_id}")
    poll_for(
        lambda: [_status(client, t) for t in task_ids],
        accept=lambda statuses: all(s in TASK_DONE for s in statuses),
        timeout=TASK_TIMEOUT,
        interval=1.0,
        message="the heavy jobs of the test did not end",
    )


def _stopped_disks(client: IsardClient, prefix: str, count: int) -> list[str]:
    templates = derivable(
        expect(admin_get_templates.sync_detailed(client=client.apiv4()))
    )
    assert templates, "no derivable template seeded"
    desktops = [
        created_id(
            create_desktop.sync_detailed(
                client=client.apiv4(),
                body=CreateDesktopRequest(
                    template_id=templates[0].id, name=f"{prefix}{i}", description=""
                ),
            )
        )
        for i in range(count)
    ]
    disks = []
    for desktop_id in desktops:
        client.poll_desktop_status(
            desktop_id, want={"Stopped"}, max_wait=CREATE_TIMEOUT
        )
        disks.append(
            expect(
                get_desktop_details.sync_detailed(
                    desktop_id=desktop_id, client=client.apiv4()
                )
            )
            .disks[0]
            .id
        )
    return disks


def _loose_disks(client: IsardClient, conn, parent_disk: str) -> list[str]:
    created = []
    for _ in range(DELETES):
        resp = client.raw(
            "POST",
            "/api/v4/item/storage/priority/default",
            json={
                "usage": "desktop",
                "storage_type": "qcow2",
                "parent": parent_disk,
                "size": "1G",
            },
        )
        assert resp.status_code == 200, resp.text
        created.append(resp.json()["storage_id"])
    for storage_id in created:
        poll_for(
            lambda: r.table("storage").get(storage_id)["status"].run(conn),
            accept=lambda s: s == "ready",
            timeout=CREATE_TIMEOUT,
            interval=1.0,
            message=f"storage {storage_id} was not created",
        )
    return created


@pytest.mark.real
@pytest.mark.slow
def test_deletes_finish_on_a_governed_worker_while_the_heavy_cap_is_full(
    admin_client: IsardClient, test_namespace: str
):
    conn = _connect()
    rq = _redis()
    saved = r.table("config").get(1)["storage_scheduler"].default(None).run(conn)
    heavy = []
    try:
        disks = _stopped_disks(admin_client, f"{test_namespace}heavy_", HEAVY_JOBS)
        parent_disk = r.table("storage").get(disks[0])["parent"].default(None).run(conn)
        assert parent_disk, "the seeded desktop disk has no parent to derive from"
        loose = _loose_disks(admin_client, conn, parent_disk)

        resp = admin_client.raw(
            "PUT",
            CONFIG,
            json={"enabled": True, "max_heavy": 1, "psi_limit": 100},
        )
        assert resp.status_code == 200, resp.text
        time.sleep(10)  # every governed worker re-reads the mirror on its next poll

        for storage_id in disks:
            resp = admin_client.raw(
                "PUT", f"/api/v4/item/storage/{storage_id}/sparsify/priority/default"
            )
            assert resp.status_code == 200, resp.text
            heavy.append(resp.json()["task_id"])
        poll_for(
            lambda: [_status(admin_client, t) for t in heavy],
            accept=lambda statuses: "started" in statuses,
            timeout=TASK_TIMEOUT,
            interval=0.5,
            message="no heavy job started",
        )

        deletes = []
        for storage_id in loose:
            resp = admin_client.raw("DELETE", f"/api/v4/item/storage/{storage_id}")
            assert resp.status_code == 200, resp.text
            deletes.append(resp.json()["tasks_ids"][0])
        poll_for(
            lambda: [_status(admin_client, t) for t in deletes],
            accept=lambda statuses: all(s in TASK_DONE for s in statuses),
            timeout=TASK_TIMEOUT,
            interval=0.5,
            message="the deletes did not end",
        )
        still_heavy = [t for t in heavy if _status(admin_client, t) not in TASK_DONE]

        workers = {}
        for task_id in deletes:
            assert _status(admin_client, task_id) == "finished", task_id
            workers[task_id] = rq_job.Job.fetch(task_id, connection=rq).worker_name
        _assert_served_at_the_cap(workers)
        assert still_heavy, "the deletes only ran once every heavy job had ended"
    finally:
        _drain(admin_client, heavy)
        if saved is None:
            r.table("config").get(1).replace(r.row.without("storage_scheduler")).run(
                conn
            )
        else:
            r.table("config").get(1).update(
                {"storage_scheduler": r.literal(saved)}
            ).run(conn)
        admin_client.raw("GET", CONFIG)  # publishes the restored block to the mirror
        conn.close()
