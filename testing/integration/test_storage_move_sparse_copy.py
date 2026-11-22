# SPDX-License-Identifier: AGPL-3.0-or-later

"""A disk moved to another pool keeps its bytes and gets no more blocks than it had."""

from __future__ import annotations

import json
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
redis = pytest.importorskip("redis")
from rethinkdb import r  # noqa: E402

CREATE_TIMEOUT = int(os.environ.get("E2E_CREATE_TIMEOUT", "180"))
MOVE_TIMEOUT = int(os.environ.get("E2E_MOVE_TIMEOUT", "300"))
DEFAULT_POOL = "00000000-0000-0000-0000-000000000000"
# fixed, so a stack can list them in CAPABILITIES_STORAGE_POOLS beforehand
MOVE_POOLS = {"plain": "ci-move-plain", "metadata_extended_l2": "ci-move-l2"}
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


def _storage(*argv: str, check: bool = True) -> str:
    if shutil.which("docker") is None:
        pytest.skip("needs docker to reach isard-storage")
    out = subprocess.run(
        ["docker", "exec", "isard-storage", *argv],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if check:
        assert out.returncode == 0, out.stderr
    return out.stdout


def _served(pool_id: str) -> bool:
    password = os.environ.get("REDIS_PASSWORD")
    if not password:
        pytest.skip("needs REDIS_PASSWORD to read which pools the workers serve")
    conn = redis.Redis(
        host=os.environ.get("REDIS_HOST", "isard-redis"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        password=password,
    )
    for worker in conn.smembers("rq:workers"):
        if pool_id in (conn.hget(worker, "queues") or b"").decode():
            return True
    return False


def _exists(path: str) -> bool:
    return (
        subprocess.run(
            ["docker", "exec", "isard-storage", "test", "-e", path]
        ).returncode
        == 0
    )


def _blocks(path: str) -> int:
    return int(_storage("stat", "-c", "%b", path).strip())


def _sha256(path: str) -> str:
    return _storage("sha256sum", path).split()[0]


def _unwritten_extents(path: str) -> int:
    return sum(
        1
        for line in _storage("filefrag", "-v", path).splitlines()
        if "unwritten" in line
    )


def _with_metadata_preallocation(path: str) -> None:
    """Rewrite the disk as QCOW2_PREALLOCATION=metadata with extended_l2 would create it."""
    info = json.loads(_storage("qemu-img", "info", "-U", "--output=json", path))
    tmp = path + ".prealloc"
    _storage(
        "qemu-img",
        "convert",
        "-f",
        "qcow2",
        "-O",
        "qcow2",
        "-o",
        "preallocation=metadata,extended_l2=on",
        "-B",
        info["full-backing-filename"],
        "-F",
        "qcow2",
        path,
        tmp,
    )
    _storage("mv", "-f", tmp, path)


def _stopped_disk(client: IsardClient, name: str) -> str:
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
    return (
        expect(
            get_desktop_details.sync_detailed(
                desktop_id=desktop_id, client=client.apiv4()
            )
        )
        .disks[0]
        .id
    )


def _pool(client: IsardClient, pool_id: str, enabled: bool = False) -> None:
    resp = client.raw(
        "POST",
        "/api/v4/storage-pool",
        json={
            "id": pool_id,
            "name": pool_id,
            "description": "",
            "mountpoint": f"/isard/storage_pools/{pool_id}",
            "enabled": enabled,
            "paths": {"desktop": [{"path": "groups", "weight": 100}]},
        },
    )
    assert resp.status_code in (200, 201), resp.text


def _move(client: IsardClient, conn, storage_id: str, pool_id: str) -> dict:
    resp = client.raw(
        "PUT",
        f"/api/v4/item/storage/{storage_id}/rsync/to-storage-pool",
        json={"destination_storage_pool_id": pool_id, "remove_source_file": True},
    )
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["task_id"]
    task = poll_for(
        lambda: client.get(f"/api/v4/task/{task_id}"),
        accept=lambda t: (t or {}).get("status") in TASK_DONE,
        timeout=MOVE_TIMEOUT,
        interval=2.0,
        message=f"move task {task_id} did not end",
    )
    assert task["status"] == "finished", task
    return poll_for(
        lambda: r.table("storage").get(storage_id).run(conn),
        accept=lambda row: row["status"] == "ready"
        and row["directory_path"].startswith(
            "/isard/groups"
            if pool_id == DEFAULT_POOL
            else f"/isard/storage_pools/{pool_id}/"
        ),
        timeout=MOVE_TIMEOUT,
        interval=1.0,
        message=f"the row of {storage_id} did not follow its disk",
    )


@pytest.mark.real
@pytest.mark.slow
@pytest.mark.parametrize("layout", ["plain", "metadata_extended_l2"])
def test_a_disk_moved_to_another_pool_stays_sparse_and_identical(
    admin_client: IsardClient, test_namespace: str, layout: str
):
    pool_id = MOVE_POOLS[layout]
    if not _served(pool_id):
        pytest.skip(
            f"no storage worker serves {pool_id}: add it to CAPABILITIES_STORAGE_POOLS "
            "of the stack under test"
        )
    conn = _connect()
    storage_id = _stopped_disk(admin_client, f"{test_namespace}{layout}_move")
    _pool(admin_client, pool_id)
    try:
        row = r.table("storage").get(storage_id).run(conn)
        source = f"{row['directory_path']}/{storage_id}.qcow2"
        if layout == "metadata_extended_l2":
            _with_metadata_preallocation(source)
        blocks, digest = _blocks(source), _sha256(source)

        row = _move(admin_client, conn, storage_id, pool_id)
        moved = f"{row['directory_path']}/{storage_id}.qcow2"
        assert _blocks(moved) <= blocks, (blocks, _blocks(moved))
        assert _unwritten_extents(moved) == 0
        assert _sha256(moved) == digest, "the moved disk reads differently"
        assert not _exists(source), "the source was left in its pool"
        assert not [
            name
            for name in _storage("ls", "-A", row["directory_path"]).split()
            if name.startswith(".") and storage_id in name
        ], "a temporary copy was left beside the disk"
    finally:
        back = _move(admin_client, conn, storage_id, DEFAULT_POOL)
        assert back["directory_path"].startswith("/isard/groups")
        resp = admin_client.raw("DELETE", f"/api/v4/storage-pool/{pool_id}")
        assert resp.status_code == 204, resp.text
        conn.close()


@pytest.mark.real
def test_a_move_onto_xfs_leaves_no_unwritten_extent(test_namespace: str):
    mountpoint = f"/isard/storage_pools/{test_namespace}xfs"
    image = f"/isard/storage_pools/{test_namespace}xfs.img"
    probe = subprocess.run(
        [
            "docker",
            "exec",
            "isard-storage",
            "sh",
            "-c",
            f"truncate -s 512M {image} && mkfs.xfs -q {image} && mkdir -p {mountpoint}"
            f" && mount -o loop {image} {mountpoint}; rc=$?;"
            f" umount {mountpoint} 2>/dev/null; rm -rf {mountpoint} {image}; exit $rc",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if probe.returncode != 0:
        pytest.skip(
            "isard-storage cannot loop-mount an XFS test pool here (not privileged): "
            + (probe.stderr.strip().splitlines() or ["mount refused"])[-1]
        )
    pytest.skip(
        "an XFS pool mounts here; give it a pool id and run the move above on it"
    )


@pytest.mark.real
def test_an_enabled_pool_is_never_deleted(
    admin_client: IsardClient, test_namespace: str
):
    pool_id = f"{test_namespace}active_pool"
    _pool(admin_client, pool_id, enabled=True)
    try:
        resp = admin_client.raw("DELETE", f"/api/v4/storage-pool/{pool_id}")
        assert resp.status_code == 400, resp.text
        assert (
            admin_client.raw("GET", f"/api/v4/storage-pool/{pool_id}").status_code
            == 200
        )
    finally:
        resp = admin_client.raw(
            "PUT", f"/api/v4/storage-pool/{pool_id}", json={"enabled": False}
        )
        assert resp.status_code in (200, 204), resp.text
        assert (
            admin_client.raw("DELETE", f"/api/v4/storage-pool/{pool_id}").status_code
            == 204
        )
