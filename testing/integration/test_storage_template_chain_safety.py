# SPDX-License-Identifier: AGPL-3.0-or-later

"""No operation on a template's disk breaks the desktops and templates derived from it.

Boots desktops, so it runs only on a staging box with KVM: ``-m staging``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field

import pytest
from isardvdi_apiv4_client.api.role_advanced import create_template
from isardvdi_apiv4_client.api.role_user import (
    create_desktop,
    force_stop_desktop,
    start_desktop,
)
from isardvdi_apiv4_client.models.allowed_base_input import AllowedBaseInput
from isardvdi_apiv4_client.models.create_desktop_request import CreateDesktopRequest
from isardvdi_apiv4_client.models.new_template_request import NewTemplateRequest

from .helpers.client import IsardClient
from .helpers.responses import created_id
from .helpers.waits import poll_for

rethinkdb = pytest.importorskip("rethinkdb")
from rethinkdb import r  # noqa: E402

log = logging.getLogger("integration.chain_safety")

pytestmark = [pytest.mark.staging]

SOURCE = os.environ.get("CHAIN_SOURCE_TEMPLATE", "r6cloud")
REPORT = os.environ.get("CHAIN_REPORT")
TASK_TIMEOUT = int(os.environ.get("CHAIN_TASK_TIMEOUT", "900"))
BOOT_TIMEOUT = int(os.environ.get("CHAIN_BOOT_TIMEOUT", "300"))
TASK_DONE = {"finished", "failed", "canceled"}
RUNNING = {"Started", "Starting", "Stopping", "Shutting-down", "Paused", "WaitingIP"}
VIRSH = ("virsh", "-c", "qemu:///system")
CTL_LEN = "64k"
MiB = 1 << 20


def _connect():
    host = os.environ.get("RETHINKDB_HOST", "isard-db")
    try:
        return r.connect(host=host, port=28015, db="isard")
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"RethinkDB not reachable at {host}: {exc}")


def _exec(container, *argv, timeout=1800):
    p = subprocess.run(
        ["docker", "exec", container, *argv],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return p.returncode, (p.stdout + p.stderr).strip()


def _storage(*argv, timeout=1800):
    return _exec("isard-storage", *argv, timeout=timeout)


def _hmp(domain_id, command):
    return _exec(
        "isard-hypervisor", *VIRSH, "qemu-monitor-command", domain_id, "--hmp", command
    )


def _view_sha(path):
    """sha256 of what a guest reads from ``path`` through its whole chain."""
    rc, out = _storage(
        "sh",
        "-c",
        'f=$(mktemp /tmp/chain.XXXXXX) && qemu-img convert -U -O raw "$1" "$f" '
        '&& sha256sum "$f" | cut -d" " -f1; s=$?; rm -f "$f"; exit $s',
        "sh",
        path,
    )
    assert rc == 0, out
    return out.splitlines()[-1]


def _check(path):
    rc, out = _storage("qemu-img", "check", "-U", "-q", path)
    return rc == 0, out


@dataclass
class Disk:
    name: str
    domain_id: str
    storage_id: str
    path: str
    kind: str  # "running", "stopped" or "template"
    vsize: int = 0
    pattern: int = 0x30
    sha: str | None = None

    @property
    def ctl_offset(self):
        return self.vsize - 8 * MiB


@dataclass
class Row:
    op: str
    expected: str
    outcome: str = ""
    detail: str = ""
    problems: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.problems


class Chain:
    def __init__(self, client: IsardClient, conn, ns: str):
        self.client = client
        self.conn = conn
        self.ns = ns
        self.disks: list[Disk] = []

    # --- building ------------------------------------------------------

    def desktop(self, template_id, name):
        did = created_id(
            create_desktop.sync_detailed(
                client=self.client.apiv4(),
                body=CreateDesktopRequest(
                    template_id=template_id, name=f"{self.ns}{name}", description=""
                ),
            )
        )
        self.client.poll_desktop_status(did, want={"Stopped"}, max_wait=300)
        return did

    def template(self, desktop_id, name):
        tid = created_id(
            create_template.sync_detailed(
                client=self.client.apiv4(),
                body=NewTemplateRequest(
                    desktop_id=desktop_id,
                    name=f"{self.ns}{name}",
                    description="",
                    allowed=AllowedBaseInput(users=False, groups=False),
                    enabled=True,
                ),
            )
        )
        self.client.wait_for_template_created(desktop_id, tid, max_wait=600)
        return tid

    def storage_of(self, domain_id):
        dom = r.table("domains").get(domain_id).run(self.conn)
        sid = dom["create_dict"]["hardware"]["disks"][0]["storage_id"]
        row = r.table("storage").get(sid).run(self.conn)
        return sid, f"{row['directory_path']}/{sid}.{row.get('type', 'qcow2')}"

    def add(self, name, domain_id, kind):
        sid, path = self.storage_of(domain_id)
        rc, out = _storage("qemu-img", "info", "-U", "--output=json", path)
        assert rc == 0, out
        disk = Disk(
            name, domain_id, sid, path, kind, vsize=json.loads(out)["virtual-size"]
        )
        self.disks.append(disk)
        return disk

    # --- the guest side ------------------------------------------------

    def node(self, disk):
        rc, out = _exec(
            "isard-hypervisor",
            *VIRSH,
            "qemu-monitor-command",
            disk.domain_id,
            '{"execute":"query-block"}',
        )
        assert rc == 0, out
        for dev in json.loads(out)["return"]:
            inserted = dev.get("inserted") or {}
            if disk.storage_id in (inserted.get("file") or ""):
                return inserted["node-name"]
        raise AssertionError(
            f"{disk.name}: its disk is not attached to its QEMU: {out}"
        )

    def qemu_io(self, disk, command):
        rc, out = _hmp(disk.domain_id, f'qemu-io {self.node(disk)} "{command}"')
        failed = rc != 0 or "fail" in out.lower() or "error" in out.lower()
        return not failed, out

    def guest_state(self, disk):
        problems = []
        _, state = _exec(
            "isard-hypervisor", *VIRSH, "domstate", disk.domain_id, "--reason"
        )
        if not state.startswith("running"):
            problems.append(f"{disk.name}: domain is {state!r}")
        _, errors = _exec("isard-hypervisor", *VIRSH, "domblkerror", disk.domain_id)
        if "No errors found" not in errors:
            problems.append(f"{disk.name}: block error {errors!r}")
        return problems

    def write_offline(self, disk):
        rc, out = _storage(
            "qemu-io",
            "-f",
            "qcow2",
            "-c",
            f"write -P {disk.pattern} {disk.ctl_offset} {CTL_LEN}",
            disk.path,
        )
        assert rc == 0, out

    def start(self, disk):
        start_desktop.sync_detailed(
            desktop_id=disk.domain_id, client=self.client.apiv4()
        )
        return self.client.poll_desktop_status(
            disk.domain_id,
            want={"Started", "WaitingIP", "Failed"},
            max_wait=BOOT_TIMEOUT,
        )

    def stop(self, disk):
        force_stop_desktop.sync_detailed(
            desktop_id=disk.domain_id, client=self.client.apiv4()
        )
        self.client.poll_desktop_status(
            disk.domain_id, want={"Stopped", "Failed"}, max_wait=120
        )

    # --- before and after an operation ---------------------------------

    def record(self):
        for disk in self.disks:
            if disk.kind != "running":
                disk.sha = _view_sha(disk.path)

    def verify(self, row: Row):
        for disk in self.disks:
            ok, out = _check(disk.path)
            if not ok:
                row.problems.append(f"{disk.name}: qemu-img check: {out[-200:]}")
            if disk.kind == "running":
                row.problems += self.guest_state(disk)
                ok, out = self.qemu_io(
                    disk, f"read -P {disk.pattern} {disk.ctl_offset} {CTL_LEN}"
                )
                if not ok:
                    row.problems.append(
                        f"{disk.name}: control pattern lost: {out[-200:]}"
                    )
                disk.pattern += 1
                for cmd in ("write", "read"):
                    ok, out = self.qemu_io(
                        disk, f"{cmd} -P {disk.pattern} {disk.ctl_offset} {CTL_LEN}"
                    )
                    if not ok:
                        row.problems.append(
                            f"{disk.name}: guest {cmd} failed: {out[-200:]}"
                        )
                row.problems += self.guest_state(disk)
            elif _view_sha(disk.path) != disk.sha:
                row.problems.append(f"{disk.name}: reads differently than before")
        for disk in self.disks:
            if disk.kind != "stopped":
                continue
            status = self.start(disk)
            if status == "Failed":
                row.problems.append(f"{disk.name}: does not start")
                continue
            ok, out = self.qemu_io(
                disk, f"read -P {disk.pattern} {disk.ctl_offset} {CTL_LEN}"
            )
            if not ok:
                row.problems.append(
                    f"{disk.name}: control pattern lost after boot: {out[-200:]}"
                )
            row.problems += self.guest_state(disk)
            self.stop(disk)


def _task(client, task_id):
    return poll_for(
        lambda: client.get(f"/api/v4/task/{task_id}"),
        accept=lambda t: (t or {}).get("status") in TASK_DONE,
        timeout=TASK_TIMEOUT,
        interval=3.0,
        message=f"task {task_id} did not end",
    )


def _ready(conn, storage_id):
    return poll_for(
        lambda: r.table("storage").get(storage_id).run(conn),
        accept=lambda s: s and s["status"] == "ready",
        timeout=TASK_TIMEOUT,
        interval=3.0,
        message=f"storage {storage_id} did not come back ready",
    )


def _ask(client, method, path, body=None):
    # a disk just touched may still be measured by the task that touched it
    return poll_for(
        lambda: client.raw(method, path, json=body),
        accept=lambda x: x.status_code != 428
        or x.json().get("description_code") != "storage_pending_task",
        timeout=TASK_TIMEOUT,
        interval=3.0,
        message=f"{path} kept answering storage_pending_task",
    )


@pytest.mark.slow
def test_no_operation_on_a_template_breaks_its_descendants(
    admin_client: IsardClient, test_namespace: str
):
    conn = _connect()
    if r.table("domains").get(SOURCE).run(conn) is None:
        pytest.skip(f"no bootable source template {SOURCE!r} (CHAIN_SOURCE_TEMPLATE)")
    chain = Chain(admin_client, conn, test_namespace)

    # T1 carries plain data, a run of zeros a dig gives back, and more data
    src = chain.desktop(SOURCE, "chain_src")
    _, src_path = chain.storage_of(src)
    rc, out = _storage(
        "qemu-io",
        "-f",
        "qcow2",
        "-c",
        "write -P 0xa1 1G 32M",
        "-c",
        "write -P 0 1056M 256M",
        "-c",
        "write -P 0xa2 1312M 32M",
        src_path,
    )
    assert rc == 0, out
    t1 = chain.template(src, "chain_t1")
    run1 = chain.desktop(t1, "chain_run1")
    stop1 = chain.desktop(t1, "chain_stop1")
    t2_src = chain.desktop(t1, "chain_t2_src")
    t2 = chain.template(t2_src, "chain_t2")
    run2 = chain.desktop(t2, "chain_run2")
    stop2 = chain.desktop(t2, "chain_stop2")

    base_id, base_path = chain.storage_of(t1)
    chain.add("T2", t2, "template")
    disks = [
        chain.add("D_run1", run1, "running"),
        chain.add("D_stop1", stop1, "stopped"),
        chain.add("D_run2", run2, "running"),
        chain.add("D_stop2", stop2, "stopped"),
    ]
    for disk in disks:
        chain.write_offline(disk)
    for disk in disks:
        if disk.kind == "running":
            assert chain.start(disk) != "Failed", f"{disk.name} does not boot"
    rc, out = _storage("qemu-img", "info", "-U", "--backing-chain", disks[2].path)
    log.info("chain of D_run2:\n%s", out)
    assert base_path in out, out

    url = f"/api/v4/item/storage/{base_id}"
    pool = r.table("storage").get(base_id)["directory_path"].run(conn)
    pool2 = f"{test_namespace}pool2"
    resp = admin_client.raw(
        "POST",
        "/api/v4/storage-pool",
        json={
            "id": pool2,
            "name": pool2,
            "description": "",
            "mountpoint": f"/isard/storage_pools/{pool2}",
        },
    )
    assert resp.status_code in (200, 201), resp.text

    def unwritten_tail():
        size = int(_storage("stat", "-c", "%s", base_path)[1])
        # unwritten extents inside the file, which the dig must give back
        rc, out = _storage("fallocate", "-o", str(size), "-l", "64M", base_path)
        assert rc == 0, out

    operations = [
        (
            "dig-holes",
            "accepted",
            None,
            "PUT",
            f"{url}/dig-holes/priority/default?verify=true",
            None,
        ),
        (
            "punch unwritten (dig)",
            "accepted",
            unwritten_tail,
            "PUT",
            f"{url}/dig-holes/priority/default?verify=true",
            None,
        ),
        (
            "move by path",
            "refused",
            None,
            "PUT",
            f"{url}/move/by-path",
            {"dest_path": f"{pool}/{base_id}-moved.qcow2"},
        ),
        (
            "move to another pool",
            "refused",
            None,
            "PUT",
            f"{url}/rsync/to-storage-pool",
            {"destination_storage_pool_id": pool2, "remove_source_file": True},
        ),
        (
            "rsync to path",
            "refused",
            None,
            "PUT",
            f"{url}/rsync/to-path",
            {"destination_path": f"{pool}/{base_id}-copy.qcow2"},
        ),
        (
            "convert",
            "refused",
            None,
            "POST",
            f"{url}/convert",
            {"new_storage_type": "qcow2"},
        ),
        ("sparsify", "refused", None, "PUT", f"{url}/sparsify/priority/default", None),
        (
            "disconnect",
            "refused",
            None,
            "PUT",
            f"{url}/disconnect/priority/default",
            None,
        ),
        ("delete storage", "refused", None, "DELETE", url, None),
        (
            "check",
            "accepted",
            None,
            "PUT",
            f"/api/v4/admin/item/storage/{base_id}/check",
            None,
        ),
        ("repair leaks", "refused", None, "PUT", f"{url}/repair/leaks", None),
        ("repair all", "refused", None, "PUT", f"{url}/repair/all", None),
    ]

    rows = []
    for name, expected, prepare, method, path, body in operations:
        row = Row(name, expected)
        rows.append(row)
        if prepare:
            prepare()
        chain.record()
        resp = _ask(admin_client, method, path, body)
        payload = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            row.outcome = "refused"
            row.detail = f"{resp.status_code} {payload.get('description_code')}"
        else:
            row.outcome = "accepted"
            task_id = payload.get("task_id")
            if task_id:
                task = _task(admin_client, task_id)
                result = task.get("result") or {}
                if isinstance(result, dict):
                    shown = {
                        k: result[k]
                        for k in ("reclaimed", "unwritten_punched", "verified")
                        if k in result
                    }
                else:
                    shown = {}
                row.detail = f"task {task['status']} {shown}"
                given_back = shown.get("reclaimed", 0) + shown.get(
                    "unwritten_punched", 0
                )
                if prepare is unwritten_tail and given_back < 64 * MiB:
                    row.problems.append("the unwritten tail was not given back")
                if task["status"] != "finished":
                    row.outcome = f"accepted, task {task['status']}"
            else:
                row.detail = str(payload)[:120]
        _ready(conn, base_id)
        if row.outcome != expected:
            row.problems.append(f"expected {expected}, was {row.outcome}")
        chain.verify(row)
        log.info(
            "%s: %s (%s) %s", row.op, row.outcome, row.detail, row.problems or "OK"
        )

    # the recycle bin takes T2 with its desktops; their files stay and T1's side is untouched
    row = Row("T2 to the recycle bin", "accepted")
    rows.append(row)
    chain.record()
    resp = admin_client.raw("DELETE", f"/api/v4/item/template/{t2}")
    row.outcome = "refused" if resp.status_code >= 400 else "accepted"
    row.detail = f"{resp.status_code} {(resp.json() or {}).get('message_code')}"
    binned = [d for d in chain.disks if d.name in ("T2", "D_run2", "D_stop2")]
    chain.disks = [d for d in chain.disks if d not in binned]
    for disk in binned:
        poll_for(
            lambda: r.table("domains").get(disk.domain_id).run(conn),
            accept=lambda d: d is None or d.get("status") not in RUNNING,
            timeout=300,
            interval=3.0,
            message=f"{disk.name} did not reach the recycle bin",
        )
        ok, out = _check(disk.path)
        if not ok:
            row.problems.append(f"{disk.name} in the bin: qemu-img check: {out[-200:]}")
        if disk.kind != "running" and _view_sha(disk.path) != disk.sha:
            row.problems.append(f"{disk.name} in the bin reads differently")
    if row.outcome != row.expected:
        row.problems.append(f"expected {row.expected}, was {row.outcome}")
    chain.verify(row)
    disks = [d for d in disks if d not in binned]
    log.info("%s: %s (%s) %s", row.op, row.outcome, row.detail, row.problems or "OK")

    table = [
        "| operation on T1 | expected | outcome | detail | descendants |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        verdict = "OK" if row.ok else "; ".join(row.problems)
        table.append(
            f"| {row.op} | {row.expected} | {row.outcome} | {row.detail} | {verdict} |"
        )
    report = "\n".join(table)
    log.info("chain safety:\n%s", report)
    if REPORT:
        with open(REPORT, "w") as f:
            f.write(report + "\n")
    for disk in disks:
        if disk.kind == "running":
            chain.stop(disk)
    admin_client.raw("DELETE", f"/api/v4/storage-pool/{pool2}")
    conn.close()
    assert all(row.ok for row in rows), report
