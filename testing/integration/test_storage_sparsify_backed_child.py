# SPDX-License-Identifier: AGPL-3.0-or-later

"""Sparsifying a child of an ext4 base never makes it bigger, and still shrinks one with garbage."""

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
SPARSIFY_TIMEOUT = int(os.environ.get("E2E_SPARSIFY_TIMEOUT", "600"))
# big enough that the L2 tables a trim over the base's clusters needs are MBs
BASE_SIZE = os.environ.get("E2E_SPARSIFY_BASE_SIZE", "120G")
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


def _storage(script: str, timeout: int = 600) -> str:
    if shutil.which("docker") is None:
        pytest.skip("needs docker to build the chain in isard-storage")
    out = subprocess.run(
        ["docker", "exec", "-e", "LIBGUESTFS_BACKEND=direct", "isard-storage"]
        + ["sh", "-c", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    return out.stdout


def _blocks(path: str) -> int:
    return int(_storage(f"stat -c %b {path}").strip())


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


@pytest.mark.real
@pytest.mark.slow
@pytest.mark.parametrize("child", ["nothing_to_give_back", "deleted_data"])
def test_sparsify_of_a_child_of_an_ext4_base(
    admin_client: IsardClient, test_namespace: str, child: str
):
    conn = _connect()
    storage_id = _stopped_disk(admin_client, f"{test_namespace}sp_{child[:4]}")
    row = r.table("storage").get(storage_id).run(conn)
    path = f"{row['directory_path']}/{storage_id}.qcow2"
    base = f"{row['directory_path']}/.{test_namespace}{child}-base.qcow2"
    forget = "sync : rm /mine : sync" if child == "deleted_data" else "sync"
    try:
        _storage(
            f"mv {path} {path}.orig"
            f" && qemu-img create -q -f qcow2 {base} {BASE_SIZE}"
            f" && guestfish -a {base} run : part-disk /dev/sda mbr : mkfs ext4 /dev/sda1"
            " : mount /dev/sda1 / : fill-pattern base 67108864 /big : rm /big"
            f" && qemu-img create -q -f qcow2 -b {base} -F qcow2 {path}"
            f" && guestfish -a {path} run : mount /dev/sda1 /"
            f" : fill-pattern child 67108864 /mine : {forget}"
        )
        before = _blocks(path)

        resp = admin_client.raw(
            "PUT", f"/api/v4/item/storage/{storage_id}/sparsify/priority/default"
        )
        assert resp.status_code == 200, resp.text
        task_id = resp.json()["task_id"]
        task = poll_for(
            lambda: admin_client.get(f"/api/v4/task/{task_id}"),
            accept=lambda t: (t or {}).get("status") in TASK_DONE,
            timeout=SPARSIFY_TIMEOUT,
            interval=2.0,
            message=f"sparsify task {task_id} did not end",
        )
        assert task["status"] == "finished", task
        after = _blocks(path)
        result = task.get("result") or {}
        if child == "nothing_to_give_back":
            assert (
                after <= before
            ), f"sparsify grew the child: {before} -> {after} blocks"
            assert result.get("kept_original") is True, result
        else:
            assert after < before, f"sparsify gave nothing back: {before} -> {after}"
            assert not result.get("kept_original"), result
        assert "No errors were found" in _storage(f"qemu-img check -U {path} || true")
    finally:
        _storage(
            f"rm -f {path} {base}; [ -e {path}.orig ] && mv {path}.orig {path}; true"
        )
        poll_for(
            lambda: r.table("storage").get(storage_id)["status"].run(conn),
            accept=lambda status: status != "maintenance",
            timeout=SPARSIFY_TIMEOUT,
            interval=2.0,
            message=f"storage {storage_id} stayed in maintenance",
        )
        conn.close()
