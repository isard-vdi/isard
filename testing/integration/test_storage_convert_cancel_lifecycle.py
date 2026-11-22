# SPDX-License-Identifier: AGPL-3.0-or-later

"""A convert cancelled mid-copy leaves no destination file and an untouched source."""

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
CONVERT_TIMEOUT = int(os.environ.get("E2E_CONVERT_TIMEOUT", "180"))
# incompressible data, so a compressed convert takes seconds, not milliseconds
FILL_MIB = int(os.environ.get("E2E_CONVERT_FILL_MIB", "192"))
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


def _in_storage(*argv: str, timeout: int = 300) -> subprocess.CompletedProcess:
    if shutil.which("docker") is None:
        pytest.skip("needs docker to reach isard-storage")
    return subprocess.run(
        ["docker", "exec", "isard-storage", *argv],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _exists(path: str) -> bool:
    return _in_storage("test", "-e", path).returncode == 0


def _sha256(path: str) -> str:
    out = _in_storage("sha256sum", path)
    assert out.returncode == 0, out.stderr
    return out.stdout.split()[0]


def _fill_with_random(path: str) -> None:
    out = _in_storage(
        "sh",
        "-c",
        f"head -c {FILL_MIB}M /dev/urandom > /tmp/ci-convert-fill && "
        f"qemu-io -f qcow2 -c 'write -s /tmp/ci-convert-fill 0 {FILL_MIB}M' {path}; "
        "rc=$?; rm -f /tmp/ci-convert-fill; exit $rc",
    )
    assert out.returncode == 0, out.stderr


@pytest.mark.real
@pytest.mark.slow
def test_a_convert_cancelled_mid_copy_leaves_nothing_behind(
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
                name=f"{test_namespace}convert_cancel",
                description="",
            ),
        )
    )
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped"}, max_wait=CREATE_TIMEOUT
    )
    storage_id = (
        expect(
            get_desktop_details.sync_detailed(
                desktop_id=desktop_id, client=admin_client.apiv4()
            )
        )
        .disks[0]
        .id
    )

    conn = _connect()
    try:
        row = r.table("storage").get(storage_id).run(conn)
        source = f"{row['directory_path']}/{storage_id}.qcow2"
        _fill_with_random(source)
        digest = _sha256(source)

        body = {"new_storage_type": "qcow2", "compress": True}
        resp = admin_client.raw(
            "POST", f"/api/v4/item/storage/{storage_id}/convert", json=body
        )
        assert resp.status_code == 200, resp.text
        new_id, task_id = resp.json()["new_storage_id"], resp.json()["task_id"]
        destination = f"{row['directory_path']}/{new_id}.qcow2"

        # mid-copy: qemu-img has started writing the destination
        poll_for(
            lambda: _exists(destination),
            accept=bool,
            timeout=CONVERT_TIMEOUT,
            interval=0.2,
            message=f"the convert never started writing {destination}",
        )
        second = admin_client.raw(
            "POST", f"/api/v4/item/storage/{storage_id}/convert", json=body
        )
        assert second.status_code >= 400, second.text

        cancel = admin_client.raw("DELETE", f"/api/v4/admin/task/{task_id}")
        assert cancel.status_code == 204, cancel.text
        task = poll_for(
            lambda: admin_client.get(f"/api/v4/task/{task_id}"),
            accept=lambda t: (t or {}).get("status") in TASK_DONE,
            timeout=CONVERT_TIMEOUT,
            interval=1.0,
            message=f"convert task {task_id} did not end",
        )
        assert task["status"] != "finished", task

        poll_for(
            lambda: (r.table("storage").get(new_id)["status"].default(None).run(conn)),
            accept=lambda status: status in (None, "deleted"),
            timeout=CONVERT_TIMEOUT,
            interval=1.0,
            message=f"the destination row {new_id} did not end deleted",
        )
        poll_for(
            lambda: not _exists(destination),
            accept=bool,
            timeout=CONVERT_TIMEOUT,
            interval=1.0,
            message=f"{destination} was left in the pool",
        )
        poll_for(
            lambda: r.table("storage").get(storage_id)["status"].run(conn),
            accept=lambda status: status == "ready",
            timeout=CONVERT_TIMEOUT,
            interval=1.0,
            message=f"the source {storage_id} did not come back ready",
        )
        assert _sha256(source) == digest, "the cancelled convert changed the source"
        # the refused second convert leaves no row of its own being created
        assert (
            r.table("storage")
            .filter({"converted_from": storage_id, "status": "creating"})
            .count()
            .run(conn)
            == 0
        )
    finally:
        conn.close()
