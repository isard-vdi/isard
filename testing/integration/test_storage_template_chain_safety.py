# SPDX-License-Identifier: AGPL-3.0-or-later

"""No operation on a template's disk breaks the desktops and templates derived from it.

Boots desktops, so it runs only on a staging box with KVM: ``-m staging``.
"""

from __future__ import annotations

import base64
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
#: the source template has qemu-guest-agent: check the descendants from inside
GUEST_AGENT = os.environ.get("CHAIN_GUEST_AGENT") == "1"
GUEST_FILE = "/var/tmp/chain-ctl"
#: summary counters a mounted filesystem keeps in memory; not damage
FSCK_BENIGN = ("count wrong", "Padding at end")


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


def _agent(domain_id, command, arguments=None, timeout=30):
    payload = {"execute": command}
    if arguments is not None:
        payload["arguments"] = arguments
    rc, out = _exec(
        "isard-hypervisor",
        *VIRSH,
        "qemu-agent-command",
        "--timeout",
        str(timeout),
        domain_id,
        json.dumps(payload),
    )
    if rc != 0:
        return None
    return json.loads(out).get("return")


def _guest_run(domain_id, script, timeout=300):
    """Run ``script`` with /bin/sh inside the guest: ``(exit code, output)``."""
    started = _agent(
        domain_id,
        "guest-exec",
        {"path": "/bin/sh", "arg": ["-c", script], "capture-output": True},
    )
    if not started:
        return None, "guest-exec refused"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = _agent(domain_id, "guest-exec-status", {"pid": started["pid"]})
        if status and status.get("exited"):
            out = ""
            for key in ("out-data", "err-data"):
                if status.get(key):
                    out += base64.b64decode(status[key]).decode(errors="replace")
            return status.get("exitcode"), out.strip()
        time.sleep(1)
    return None, "guest-exec did not end"


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
    #: sha256 of a file written inside the guest before the operations
    guest_sha: str | None = None

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

    def fill(self, domain_id, path, data, zeros):
        """Data, zeros and data on a disk; with an agent the guest writes them, raw offsets would hit its fs."""
        if not GUEST_AGENT:
            rc, out = _storage(
                "qemu-io",
                "-f",
                "qcow2",
                "-c",
                f"write -P 0xa1 1G {data}M",
                "-c",
                f"write -P 0 {1024 + data}M {zeros}M",
                "-c",
                f"write -P 0xa2 {1024 + data + zeros}M {data}M",
                path,
            )
            assert rc == 0, out
            return
        disk = Disk("source", domain_id, "", path, "stopped")
        assert self.start(disk) != "Failed", "the source desktop does not boot"
        problem = self.wait_agent(disk)
        assert problem is None, problem
        rc, out = _guest_run(
            domain_id,
            f"head -c {data}M /dev/urandom > /var/tmp/a1"
            f" && head -c {zeros}M /dev/zero > /var/tmp/zeros"
            f" && head -c {data}M /dev/urandom > /var/tmp/a2 && sync",
        )
        assert rc == 0, out
        self.stop(disk)

    def write_offline(self, disk):
        if GUEST_AGENT:
            return
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

    # --- inside the guest (CHAIN_GUEST_AGENT) ---------------------------

    def wait_agent(self, disk):
        try:
            poll_for(
                lambda: _agent(disk.domain_id, "guest-ping", timeout=5),
                accept=lambda answer: answer is not None,
                timeout=BOOT_TIMEOUT,
                interval=3.0,
                message=f"{disk.name}: the guest agent does not answer",
            )
        except Exception as exc:
            return str(exc)
        return None

    def guest_seed(self, disk):
        problem = self.wait_agent(disk)
        assert problem is None, problem
        rc, out = _guest_run(
            disk.domain_id,
            f"head -c 4194304 /dev/urandom > {GUEST_FILE} && sync"
            f" && sha256sum {GUEST_FILE} | cut -d' ' -f1",
        )
        assert rc == 0, out
        disk.guest_sha = out.splitlines()[-1]

    def seed_guests(self):
        """Write a file inside every desktop's guest, booting the stopped ones."""
        if not GUEST_AGENT:
            return
        for disk in self.disks:
            if disk.kind == "running":
                self.guest_seed(disk)
            elif disk.kind == "stopped":
                assert self.start(disk) != "Failed", f"{disk.name} does not boot"
                self.guest_seed(disk)
                self.stop(disk)

    def guest_check(self, disk):
        """From inside the guest: the file reads the same, no I/O error, a clean fsck."""
        if not GUEST_AGENT or disk.guest_sha is None:
            return []
        problem = self.wait_agent(disk)
        if problem:
            return [problem]
        problems = []
        rc, out = _guest_run(disk.domain_id, f"sha256sum {GUEST_FILE} | cut -d' ' -f1")
        if rc != 0 or out.splitlines()[-1:] != [disk.guest_sha]:
            problems.append(f"{disk.name}: the guest file reads differently: {out!r}")
        rc, out = _guest_run(
            disk.domain_id,
            "dmesg | grep -iE 'i/o error|ext4-fs error|blk_update_request'",
        )
        if out.strip():
            problems.append(f"{disk.name}: dmesg: {out.strip().splitlines()[-3:]}")
        # guest-exec is refused while frozen, so a sync stands in for a freeze
        rc, out = _guest_run(
            disk.domain_id, "sync; e2fsck -fn $(findmnt -no SOURCE /) 2>&1; echo rc=$?"
        )
        dev = "/"
        code, damage, skip = "?", [], False
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("rc="):
                code = line[3:]
            elif skip and line.startswith("Fix?"):
                skip = False
            elif any(benign in line for benign in FSCK_BENIGN):
                skip = True
            elif "?" in line or "error" in line.lower():
                damage.append(line)
                skip = False
        # 4 = "left uncorrected": a mounted root differs only in its summary counters
        if code not in ("0", "4") or damage:
            problems.append(f"{disk.name}: fsck -n of {dev}: rc={code} {damage[:3]}")
        return problems

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
            if disk.kind == "running" and GUEST_AGENT:
                row.problems += self.guest_state(disk)
                row.problems += self.guest_check(disk)
                self.guest_seed(disk)
            elif disk.kind == "running":
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
            if not GUEST_AGENT:
                ok, out = self.qemu_io(
                    disk, f"read -P {disk.pattern} {disk.ctl_offset} {CTL_LEN}"
                )
                if not ok:
                    row.problems.append(
                        f"{disk.name}: control pattern lost after boot: {out[-200:]}"
                    )
            row.problems += self.guest_state(disk)
            row.problems += self.guest_check(disk)
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
    chain.fill(src, src_path, data=32, zeros=256)
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
    chain.seed_guests()
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


# --- a template chain migrated between pools ---------------------------------

#: other pools of the box, in hop order, each served by a worker
POOLS = [p for p in os.environ.get("CHAIN_POOLS", "").split(",") if p]
MIGRATION_TIMEOUT = int(os.environ.get("CHAIN_MIGRATION_TIMEOUT", "1800"))
MIGRATION_DONE = {"completed", "completed_with_skips", "failed", "canceled"}
#: fail a hop whose copy allocates more than its source (the sparse copy)
NO_INFLATION = os.environ.get("CHAIN_NO_INFLATION") == "1"


def _allocated(path):
    rc, out = _storage("stat", "-c", "%b %B", path)
    assert rc == 0, out
    blocks, size = out.split()
    return int(blocks) * int(size)


def _fs(path):
    rc, out = _storage("stat", "-f", "-c", "%T", os.path.dirname(path))
    return out if rc == 0 else "?"


POOL_PATHS = {
    kind: [{"path": f"{kind}s", "weight": 100}]
    for kind in ("desktop", "template", "media", "volatile")
}


def _ensure_pool(client, pool_id):
    body = {"name": pool_id, "enabled": True, "paths": POOL_PATHS}
    if client.raw("GET", f"/api/v4/storage-pool/{pool_id}").status_code == 200:
        resp = client.raw("PUT", f"/api/v4/storage-pool/{pool_id}", json=body)
    else:
        body.update(
            id=pool_id, description="", mountpoint=f"/isard/storage_pools/{pool_id}"
        )
        resp = client.raw("POST", "/api/v4/storage-pool", json=body)
    assert resp.status_code in (200, 201), resp.text


def _pool_of(conn, directory_path):
    for pool in r.table("storage_pool").run(conn):
        mountpoint = pool.get("mountpoint") or f"/isard/storage_pools/{pool['id']}"
        if directory_path.startswith(mountpoint.rstrip("/") + "/"):
            return pool["id"]
    return None


def _migrate(client, tree_id, src_pool, dst_pool):
    resp = client.raw(
        "POST",
        "/api/v4/admin/storage/migrations",
        json={
            "selection": {
                "kind": "pool",
                "src_pool_id": src_pool,
                "dst_pool_id": dst_pool,
                "tree_ids": [tree_id],
            },
            "config": {
                "verify": True,
                "source_disposition": "delete",
                "min_free_pct": 0,
            },
        },
    )
    assert resp.status_code in (200, 201), resp.text
    migration_id = resp.json()["id"]
    resp = client.raw("POST", f"/api/v4/admin/storage/migrations/{migration_id}/start")
    assert resp.status_code in (200, 201), resp.text
    job = poll_for(
        lambda: client.raw(
            "GET", f"/api/v4/admin/storage/migrations/{migration_id}"
        ).json(),
        accept=lambda j: (j or {}).get("status") in MIGRATION_DONE,
        timeout=MIGRATION_TIMEOUT,
        interval=5.0,
        message=f"migration {migration_id} did not end",
    )
    items = client.raw(
        "GET", f"/api/v4/admin/storage/migrations/{migration_id}/items"
    ).json()
    if isinstance(items, dict):
        items = items.get("items") or []
    return job, items


@pytest.mark.slow
def test_a_template_chain_migrated_between_pools_keeps_its_descendants(
    admin_client: IsardClient, test_namespace: str
):
    if not POOLS:
        pytest.skip("no CHAIN_POOLS: the box has no other pool with a worker")
    conn = _connect()
    if r.table("domains").get(SOURCE).run(conn) is None:
        pytest.skip(f"no bootable source template {SOURCE!r} (CHAIN_SOURCE_TEMPLATE)")
    for pool_id in POOLS:
        _ensure_pool(admin_client, pool_id)
    chain = Chain(admin_client, conn, test_namespace)

    # T1 carries data and a run of zeros; T2 derives from T1; three desktops
    src = chain.desktop(SOURCE, "mig_src")
    _, src_path = chain.storage_of(src)
    chain.fill(src, src_path, data=32, zeros=128)
    t1 = chain.template(src, "mig_t1")
    stop1 = chain.desktop(t1, "mig_stop1")
    t2_src = chain.desktop(t1, "mig_t2_src")
    t2 = chain.template(t2_src, "mig_t2")
    stop2 = chain.desktop(t2, "mig_stop2")
    base_id, base_path = chain.storage_of(t1)
    chain.add("T1", t1, "template")
    chain.add("T2", t2, "template")
    chain.add("D_t2_src", t2_src, "stopped")
    chain.add("D_stop1", stop1, "stopped")
    chain.add("D_stop2", stop2, "stopped")
    for disk in chain.disks:
        if disk.kind == "stopped":
            chain.write_offline(disk)
    chain.seed_guests()
    home = _pool_of(conn, os.path.dirname(base_path))
    assert home, base_path

    rows = []
    for src_pool, dst_pool in zip([home] + POOLS, POOLS + [home]):
        row = Row(f"migrate {src_pool} -> {dst_pool}", "completed")
        rows.append(row)
        chain.record()
        before = {
            d.name: (d.path, _allocated(d.path), _fs(d.path)) for d in chain.disks
        }
        job, items = _migrate(admin_client, base_id, src_pool, dst_pool)
        row.outcome = job["status"]
        excluded = (job.get("totals") or {}).get("excluded_trees") or []
        if excluded:
            row.problems.append(
                f"trees left out: {[t.get('reason') for t in excluded]}"
            )
        stuck = [
            (i.get("storage_id"), i.get("state"), i.get("error"))
            for i in items
            if i.get("state") != "released"
        ]
        if stuck:
            row.problems.append(f"items not released: {stuck}")
        if row.outcome != row.expected:
            row.problems.append(f"expected {row.expected}, was {row.outcome}")
        sizes = []
        for disk in chain.disks:
            _ready(conn, disk.storage_id)
            _, disk.path = chain.storage_of(disk.domain_id)
            now = _pool_of(conn, os.path.dirname(disk.path))
            if now != dst_pool:
                row.problems.append(f"{disk.name}: in pool {now}, not {dst_pool}")
            old_path, old_alloc, old_fs = before[disk.name]
            if old_path != disk.path and _storage("test", "-e", old_path)[0] == 0:
                row.problems.append(f"{disk.name}: source file left at {old_path}")
            new_alloc = _allocated(disk.path)
            sizes.append(
                f"{disk.name} {old_alloc // MiB}->{new_alloc // MiB} MiB"
                f" ({old_fs}->{_fs(disk.path)})"
            )
            # a copy must not inflate the file: its zeros stay holes
            if NO_INFLATION and new_alloc > old_alloc + 16 * MiB:
                row.problems.append(
                    f"{disk.name}: grew from {old_alloc // MiB} to "
                    f"{new_alloc // MiB} MiB"
                )
        row.detail = "; ".join(sizes)
        leaf = next(d for d in chain.disks if d.name == "D_stop2")
        rc, out = _storage("qemu-img", "info", "-U", "--backing-chain", leaf.path)
        if rc != 0:
            row.problems.append(f"D_stop2: its chain does not resolve: {out[-200:]}")
        chain.verify(row)
        log.info(
            "%s: %s (%s) %s", row.op, row.outcome, row.detail, row.problems or "OK"
        )

    table = [
        "| migration of the T1 tree | expected | outcome"
        " | allocated before->after (fs) | descendants |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        verdict = "OK" if row.ok else "; ".join(row.problems)
        table.append(
            f"| {row.op} | {row.expected} | {row.outcome} | {row.detail} | {verdict} |"
        )
    report = "\n".join(table)
    log.info("chain migration:\n%s", report)
    if REPORT:
        with open(REPORT.replace(".md", "-migration.md"), "w") as f:
            f.write(report + "\n")
    conn.close()
    assert all(row.ok for row in rows), report
