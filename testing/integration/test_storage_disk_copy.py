# SPDX-License-Identifier: AGPL-3.0-or-later

"""Disk copies through the storage worker keep the content and land on the file path."""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest
from isardvdi_apiv4_client.api.role_advanced import create_template
from isardvdi_apiv4_client.api.role_manager import admin_get_templates
from isardvdi_apiv4_client.api.role_user import create_desktop, get_desktop_details
from isardvdi_apiv4_client.models.allowed_base_input import AllowedBaseInput
from isardvdi_apiv4_client.models.create_desktop_request import CreateDesktopRequest
from isardvdi_apiv4_client.models.new_template_request import NewTemplateRequest

from .helpers.client import IsardClient
from .helpers.responses import created_id, expect
from .helpers.seed import derivable
from .helpers.waits import poll_for

rethinkdb = pytest.importorskip("rethinkdb")
redis = pytest.importorskip("redis")
from rethinkdb import r  # noqa: E402

pytestmark = pytest.mark.real

CREATE_TIMEOUT = int(os.environ.get("E2E_CREATE_TIMEOUT", "180"))
TASK_TIMEOUT = int(os.environ.get("E2E_DISK_COPY_TIMEOUT", "300"))
DEFAULT_POOL = "00000000-0000-0000-0000-000000000000"
# rsync/to-path resolves its destination inside the path's pool, so only another pool copies
COPY_POOL = "ci-move-plain"
INFLATE_MIB = int(os.environ.get("E2E_DISK_COPY_INFLATE_MIB", "128"))
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


def _in_storage(*argv: str, timeout: int = 120) -> subprocess.CompletedProcess:
    if shutil.which("docker") is None:
        pytest.skip("no docker client to reach isard-storage")
    return subprocess.run(
        ["docker", "exec", "isard-storage", *argv],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _out(*argv: str) -> str:
    done = _in_storage(*argv)
    assert done.returncode == 0, f"{argv} -> {done.returncode}: {done.stderr[:500]}"
    return done.stdout


def _sha256(path: str) -> str:
    return _out("sha256sum", path).split()[0]


def _blocks(path: str) -> int:
    return int(_out("stat", "-c", "%b", path).strip())


@pytest.fixture
def conn():
    connection = _connect()
    yield connection
    connection.close()


def _stopped_desktop(admin: IsardClient, name: str) -> tuple[str, str]:
    templates = derivable(
        expect(admin_get_templates.sync_detailed(client=admin.apiv4()))
    )
    assert templates, "no derivable template seeded"
    desktop_id = created_id(
        create_desktop.sync_detailed(
            client=admin.apiv4(),
            body=CreateDesktopRequest(
                template_id=templates[0].id, name=name, description=""
            ),
        )
    )
    admin.poll_desktop_status(desktop_id, want={"Stopped"}, max_wait=CREATE_TIMEOUT)
    details = expect(
        get_desktop_details.sync_detailed(desktop_id=desktop_id, client=admin.apiv4())
    )
    return desktop_id, details.disks[0].id


def _not_pending(admin: IsardClient, method: str, url: str, **kw):
    """A fresh disk is still measured by the task its creation queued."""
    return poll_for(
        lambda: admin.raw(method, url, **kw),
        accept=lambda x: x.status_code != 428
        or x.json().get("description_code") != "storage_pending_task",
        timeout=TASK_TIMEOUT,
        interval=2.0,
        message=f"{url} kept answering storage_pending_task",
    )


def _task_finished(admin: IsardClient, task_id: str) -> dict:
    task = poll_for(
        lambda: admin.get(f"/api/v4/task/{task_id}"),
        accept=lambda t: (t or {}).get("status") in TASK_DONE,
        timeout=TASK_TIMEOUT,
        interval=2.0,
        message=f"task {task_id} did not end",
    )
    assert task["status"] == "finished", f"task {task_id} ended {task}"
    return task


def _served(pool_id: str) -> bool:
    password = os.environ.get("REDIS_PASSWORD")
    if not password:
        pytest.skip("needs REDIS_PASSWORD to read which pools the workers serve")
    conn = redis.Redis(
        host=os.environ.get("REDIS_HOST", "isard-redis"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        password=password,
    )
    return any(
        pool_id in (conn.hget(worker, "queues") or b"").decode()
        for worker in conn.smembers("rq:workers")
    )


def _move_to_pool(admin: IsardClient, conn, storage_id: str, pool_id: str) -> dict:
    resp = _not_pending(
        admin,
        "PUT",
        f"/api/v4/item/storage/{storage_id}/rsync/to-storage-pool",
        json={"destination_storage_pool_id": pool_id, "remove_source_file": True},
    )
    assert resp.status_code == 200, f"rsync -> {resp.status_code}: {resp.text[:500]}"
    _task_finished(admin, resp.json()["task_id"])
    prefix = (
        "/isard/groups"
        if pool_id == DEFAULT_POOL
        else f"/isard/storage_pools/{pool_id}/"
    )
    return poll_for(
        lambda: r.table("storage").get(storage_id).run(conn),
        accept=lambda s: s["status"] == "ready"
        and (s.get("directory_path") or "").startswith(prefix),
        timeout=TASK_TIMEOUT,
        interval=2.0,
        message=f"storage {storage_id} never pointed into {prefix}",
    )


@pytest.mark.slow
def test_a_copied_disk_keeps_its_content_and_no_more_blocks(
    admin_client, conn, test_namespace
):
    """The only real-file check of disk_copy: a written disk copied to another pool."""
    if not _served(COPY_POOL):
        pytest.skip(
            f"no storage worker serves {COPY_POOL}: add it to CAPABILITIES_STORAGE_POOLS "
            "of the stack under test"
        )
    _desktop_id, storage_id = _stopped_desktop(
        admin_client, f"{test_namespace}disk_copy"
    )
    row = r.table("storage").get(storage_id).run(conn)
    source = f"{row['directory_path']}/{storage_id}.{row.get('type', 'qcow2')}"
    _out(
        "dd",
        f"if={source}",
        f"of={source}",
        "bs=1M",
        f"count={INFLATE_MIB}",
        "conv=notrunc",
        "status=none",
    )
    digest, blocks = _sha256(source), _blocks(source)
    resp = admin_client.raw(
        "POST",
        "/api/v4/storage-pool",
        json={
            "id": COPY_POOL,
            "name": COPY_POOL,
            "description": "",
            "mountpoint": f"/isard/storage_pools/{COPY_POOL}",
            "enabled": False,
            "paths": {"desktop": [{"path": "groups", "weight": 100}]},
        },
    )
    assert resp.status_code in (200, 201), resp.text
    try:
        row = _move_to_pool(admin_client, conn, storage_id, COPY_POOL)
        target_dir = row["directory_path"]
        destination = f"{target_dir}/{storage_id}.{row.get('type', 'qcow2')}"
        assert destination != source, "the move did not change the disk's path"
        assert (
            _sha256(destination) == digest
        ), "the copy reads differently from the source"
        check = _in_storage("qemu-img", "check", destination)
        assert check.returncode == 0, f"qemu-img check: {check.stdout}{check.stderr}"
        assert (
            _blocks(destination) <= blocks
        ), f"the copy has {_blocks(destination)} blocks, the source had {blocks}"
        names = _out("ls", "-a", target_dir).split()
        temps = [n for n in names if n.startswith(f".{storage_id}.")]
        assert not temps, f"temporary siblings left beside the copy: {temps}"
        assert _in_storage("test", "-e", source).returncode != 0, "the source stayed"
    finally:
        _move_to_pool(admin_client, conn, storage_id, DEFAULT_POOL)
        resp = admin_client.raw("DELETE", f"/api/v4/storage-pool/{COPY_POOL}")
        assert resp.status_code == 204, resp.text


@pytest.mark.slow
def test_a_converted_template_disk_lands_on_its_file_path(
    admin_client, conn, test_namespace
):
    """a main: the disk is moved onto a directory, the row's filename is that directory."""
    desktop_id, _sid = _stopped_desktop(admin_client, f"{test_namespace}conv_src")
    template_id = created_id(
        create_template.sync_detailed(
            client=admin_client.apiv4(),
            body=NewTemplateRequest(
                desktop_id=desktop_id,
                name=f"{test_namespace}conv_template",
                description="",
                allowed=AllowedBaseInput(users=False, groups=False),
                enabled=True,
            ),
        )
    )
    admin_client.wait_for_template_created(
        source_desktop_id=desktop_id, template_id=template_id, max_wait=TASK_TIMEOUT
    )
    template = r.table("domains").get(template_id).run(conn)
    storage_id = template["create_dict"]["hardware"]["disks"][0]["storage_id"]

    resp = admin_client.raw(
        "DELETE", f"/api/v4/item/desktop/{desktop_id}", params={"permanent": "true"}
    )
    assert resp.status_code in (
        200,
        202,
        204,
    ), f"permanent delete -> {resp.status_code}: {resp.text[:500]}"
    poll_for(
        lambda: r.table("storage")
        .filter({"parent": storage_id})
        .filter(r.row["status"] != "deleted")
        .count()
        .run(conn),
        accept=lambda n: n == 0,
        timeout=TASK_TIMEOUT,
        interval=2.0,
        message=f"the template disk {storage_id} kept a live child",
    )

    resp = poll_for(
        lambda: admin_client.raw(
            "POST",
            f"/api/v4/item/template/{template_id}/convert-to-desktop",
            json={"name": f"{test_namespace}conv"},
        ),
        accept=lambda x: x.status_code != 428,
        timeout=TASK_TIMEOUT,
        interval=2.0,
        message=f"template {template_id} kept refusing the conversion",
    )
    assert resp.status_code == 200, f"convert -> {resp.status_code}: {resp.text[:500]}"

    row = poll_for(
        lambda: r.table("storage").get(storage_id).run(conn),
        accept=lambda s: s["status"] in ("ready", "failed", "deleted")
        and "/templates" not in (s.get("directory_path") or "/templates"),
        timeout=TASK_TIMEOUT,
        interval=2.0,
        message=f"storage {storage_id} never left the templates directory",
    )
    path = f"{row['directory_path']}/{storage_id}.{row.get('type', 'qcow2')}"
    filename = (row.get("qemu-img-info") or {}).get("filename")
    assert row["status"] == "ready", f"the converted disk is {row['status']}: {row}"
    assert filename == path, f"qemu-img-info.filename is {filename!r}, not {path}"
    assert _in_storage("test", "-f", path).returncode == 0, f"{path} is not a file"
    admin_client.poll_desktop_status(template_id, want={"Stopped"}, max_wait=60)
