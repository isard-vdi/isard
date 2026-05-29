#!/usr/bin/env python3
"""
IsardVDI Template Transfer Tool

Port a TEMPLATE (its flattened qcow2 disk, its ``domains`` + ``storage`` docs and,
if present, its user card) from one IsardVDI installation to another over SSH.

Design (see sysadm/TEMPLATE_TRANSFER.md for the full rationale):

- The export is **read-only on the source**: the disk is flattened into a *copy*
  (qemu-img convert -U to a new file); the source disk and its derived desktops are
  never touched, and the source database is never written.
- **All RethinkDB access runs inside the ``isard-storage`` container** (local and
  remote, via ``docker exec``), honouring ``RETHINKDB_HOST/PORT/DB`` from
  ``isardvdi.cfg`` (sourced from /usr/local/etc/environment) or the documented
  defaults. The host needs only ``docker`` + ``ssh`` -- no python rethinkdb driver.
- **Fail-closed pre-flight gates** run before any mutation (and are the whole body
  of ``--dry-run``): conflicts, remote user existence, free space, source lock and
  referential integrity of every hardware id referenced by the template.
- Transfers are **resumable** (rsync --partial --append-verify; convert is reused if
  a valid copy already exists) and **fast** (no compression of qcow2, whole-file,
  SSH multiplexing, fast cipher; optional plaintext nc transport for trusted LANs).

Host paths are ``/opt/isard/...``; inside ``isard-storage`` they are ``/isard/...``.
"""

import argparse
import base64
import json
import logging
import shlex
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# The rethinkdb driver is only needed by the legacy local dump/restore commands.
# The main transfer path talks to RethinkDB exclusively through isard-storage.
try:
    from rethinkdb import r
except ImportError:
    r = None

# ============================================================================
# Configuration
# ============================================================================

# Staging area for converted (flattened) disks. Lives under the templates mount
# so it is visible inside isard-storage as /isard/templates/dump/converting.
DUMP_BASE_FOLDER = Path("/opt/isard/templates/dump")
CONVERTING_FOLDER = DUMP_BASE_FOLDER / "converting"
LOG_FOLDER = Path("/opt/isard-local/logs/storage")

for _folder in [DUMP_BASE_FOLDER, CONVERTING_FOLDER]:
    try:
        _folder.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

# Console always; file handler only if the log dir is writable (don't crash on import).
_handlers = [logging.StreamHandler()]
try:
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    _handlers.insert(0, logging.FileHandler(LOG_FOLDER / "template_transfer.log"))
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=_handlers,
)
logger = logging.getLogger(__name__)

# Container used for qemu + DB operations on both sides. Overridable via CLI.
CONTAINER = "isard-storage"

# SSH behaviour, populated by main() from CLI args. Read-only after start-up.
SSH_CONFIG = {
    "cipher": None,  # e.g. aes128-gcm@openssh.com
    "compression": False,  # ssh-level compression (off: bad for qcow2)
    "multiplex": True,  # reuse a single SSH connection
    "strict_hostkey": False,  # default: do not verify host keys (ops tool)
}

# Hardware reference kinds checked against the destination. None of these block an
# import: any id absent on the destination is pruned (or replaced by the IsardVDI
# default) by the restore step, with a warning. Only true conflicts/space/user/source
# problems abort (see gate_check).
REF_KINDS = ("interfaces", "graphics", "videos", "media", "vgpus", "hypervisors_pools")

# Privilege prefixes resolved by preflight_connectivity() (auto-sudo fallback): each
# side tries plain docker first and falls back to `sudo -n docker` if that is denied.
# REMOTE_SUDO gates rsync/mkdir on the destination (root-owned data dir). --no-sudo
# forbids escalation. The host needs only docker (direct or via passwordless sudo).
LOCAL_DOCKER = ["docker"]
REMOTE_DOCKER = ["docker"]
REMOTE_SUDO = False
ALLOW_SUDO = True


# ============================================================================
# Path translation helpers (host <-> isard-storage container)
# ============================================================================


def host_to_container_path(host_path):
    """Map a host path (/opt/isard/...) to its path inside isard-storage (/isard/...)."""
    path_str = str(host_path)
    if path_str.startswith("/opt/isard/templates"):
        return path_str.replace("/opt/isard/templates", "/isard/templates", 1)
    elif path_str.startswith("/opt/isard/groups"):
        return path_str.replace("/opt/isard/groups", "/isard/groups", 1)
    elif path_str.startswith("/opt/isard/media"):
        return path_str.replace("/opt/isard/media", "/isard/media", 1)
    elif path_str.startswith("/opt/isard/volatile"):
        return path_str.replace("/opt/isard/volatile", "/isard/volatile", 1)
    elif path_str.startswith("/opt/isard/storage_pools"):
        return path_str.replace("/opt/isard/storage_pools", "/isard/storage_pools", 1)
    elif path_str.startswith("/opt/isard-local/logs/storage"):
        return path_str.replace("/opt/isard-local/logs/storage", "/logs", 1)
    logger.warning(f"Path not in a known isard-storage mount: {path_str}")
    return path_str


def container_to_host_path(container_path):
    """Map an isard-storage container path (/isard/...) back to its host path (/opt/isard/...)."""
    path_str = str(container_path)
    if path_str.startswith("/isard/templates"):
        return path_str.replace("/isard/templates", "/opt/isard/templates", 1)
    elif path_str.startswith("/isard/groups"):
        return path_str.replace("/isard/groups", "/opt/isard/groups", 1)
    elif path_str.startswith("/isard/media"):
        return path_str.replace("/isard/media", "/opt/isard/media", 1)
    elif path_str.startswith("/isard/volatile"):
        return path_str.replace("/isard/volatile", "/opt/isard/volatile", 1)
    elif path_str.startswith("/isard/storage_pools"):
        return path_str.replace("/isard/storage_pools", "/opt/isard/storage_pools", 1)
    elif path_str.startswith("/logs"):
        return path_str.replace("/logs", "/opt/isard-local/logs/storage", 1)
    return path_str


# ============================================================================
# SSH / exec primitives
# ============================================================================

# Fixed inner command: source the container env (so RETHINKDB_HOST etc. from
# isardvdi.cfg are honoured), cd to /utils so storage_lib is importable, then run
# the python program that arrives on stdin.
_PY_INNER = ". /usr/local/etc/environment 2>/dev/null; cd /utils 2>/dev/null || true; exec python3 -"


def _ssh_opts():
    """Build the shared list of ssh -o options from SSH_CONFIG."""
    opts = []
    if SSH_CONFIG.get("strict_hostkey"):
        opts += ["-o", "StrictHostKeyChecking=accept-new"]
    else:
        opts += ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
    opts += ["-o", "Compression=" + ("yes" if SSH_CONFIG.get("compression") else "no")]
    if SSH_CONFIG.get("cipher"):
        opts += ["-c", SSH_CONFIG["cipher"]]
    if SSH_CONFIG.get("multiplex"):
        opts += [
            "-o",
            "ControlMaster=auto",
            "-o",
            "ControlPath=/tmp/tt-cm-%C",
            "-o",
            "ControlPersist=120s",
        ]
    return opts


def _rsh():
    """The ssh command string for rsync's -e option."""
    return "ssh " + " ".join(_ssh_opts())


def _ssh_prefix(remote_host):
    return ["ssh"] + _ssh_opts() + [remote_host]


def _ssh_run(remote_host, command_str, **kw):
    """Run a shell command on the remote HOST (not in a container)."""
    cmd = _ssh_prefix(remote_host) + [command_str]
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def _storage_py(program, remote_host=None, timeout=600):
    """Run a python ``program`` inside isard-storage (local or via SSH), program on stdin."""
    if remote_host:
        remote_cmd = "{} exec -i {} sh -c {}".format(
            " ".join(REMOTE_DOCKER), shlex.quote(CONTAINER), shlex.quote(_PY_INNER)
        )
        cmd = _ssh_prefix(remote_host) + [remote_cmd]
    else:
        cmd = LOCAL_DOCKER + ["exec", "-i", CONTAINER, "sh", "-c", _PY_INNER]
    return subprocess.run(
        cmd, input=program, capture_output=True, text=True, timeout=timeout
    )


def _storage_cmd(args, remote_host=None, timeout=None, capture=True):
    """Run a plain command (e.g. qemu-img) inside isard-storage (local or via SSH)."""
    if remote_host:
        remote_cmd = "{} exec -i {} {}".format(
            " ".join(REMOTE_DOCKER),
            shlex.quote(CONTAINER),
            " ".join(shlex.quote(a) for a in args),
        )
        cmd = _ssh_prefix(remote_host) + [remote_cmd]
    else:
        cmd = LOCAL_DOCKER + ["exec", "-i", CONTAINER] + args
    if capture:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return subprocess.run(cmd, timeout=timeout)


# ----------------------------------------------------------------------------
# Privilege detection + SSH/docker self-verification (G0)
# ----------------------------------------------------------------------------


def _docker_prefixes():
    """Candidate docker invocations, in order: plain, then passwordless sudo."""
    prefixes = [["docker"]]
    if ALLOW_SUDO:
        prefixes.append(["sudo", "-n", "docker"])
    return prefixes


def _resolve_docker(remote_host=None):
    """Find a docker prefix that can `exec <container> true` (local or remote).

    Returns (prefix_list, mode) where mode is 'direct'|'sudo', or (None, reason)."""
    for pref in _docker_prefixes():
        if remote_host:
            rc = subprocess.run(
                _ssh_prefix(remote_host)
                + ["{} exec {} true".format(" ".join(pref), shlex.quote(CONTAINER))],
                capture_output=True,
                text=True,
                timeout=40,
            )
        else:
            rc = subprocess.run(
                pref + ["exec", CONTAINER, "true"],
                capture_output=True,
                text=True,
                timeout=40,
            )
        if rc.returncode == 0:
            return pref, ("sudo" if pref[0] == "sudo" else "direct")
    return None, (rc.stderr or rc.stdout or "").strip()[:160]


def _probe_ssh(remote_host):
    """Classify the SSH path: 'ok' | 'no_key' | 'unreachable' | 'error' (+detail)."""
    rc = subprocess.run(
        _ssh_prefix(remote_host) + ["true"], capture_output=True, text=True, timeout=25
    )
    if rc.returncode == 0:
        return "ok", ""
    err = (rc.stderr or "").strip()
    low = err.lower()
    if "permission denied" in low:
        return "no_key", err
    if any(
        s in low
        for s in ("connection refused", "timed out", "no route", "could not resolve")
    ):
        return "unreachable", err
    return "error", err


# Single-line capability report from inside the container.
_CAP_SNIPPET = (
    ". /usr/local/etc/environment 2>/dev/null; echo CAP"
    " qemu_img=$(command -v qemu-img >/dev/null 2>&1 && echo yes || echo MISSING)"
    " rethinkdb=$(python3 -c 'import rethinkdb' >/dev/null 2>&1 && echo yes || echo MISSING)"
    " virt_sparsify=$(command -v virt-sparsify >/dev/null 2>&1 && echo yes || echo MISSING)"
    " utils=$(test -d /utils && echo yes || echo no)"
)


def _probe_capabilities(remote_host=None):
    """Return a dict of in-container capabilities (qemu_img/rethinkdb/virt_sparsify/utils)."""
    cp = _storage_cmd(["sh", "-c", _CAP_SNIPPET], remote_host=remote_host)
    caps = {}
    for line in ((cp.stdout or "") + "\n" + (cp.stderr or "")).splitlines():
        if line.startswith("CAP "):
            for tok in line[4:].split():
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    caps[k] = v
            break
    return caps


def _report_caps(side, caps, need_sparsify, lines):
    """Append a capability report for a side; return False if a required tool is missing."""
    if not caps:
        lines.append(
            f"G0 {side} tools : FAIL - could not read {CONTAINER} capabilities"
        )
        return False
    missing = [t for t in ("qemu_img", "rethinkdb") if caps.get(t) != "yes"]
    if missing:
        lines.append(
            f"G0 {side} tools : FAIL - missing {', '.join(missing)} in {CONTAINER}"
        )
        return False
    extra = "" if caps.get("utils") == "yes" else " (no /utils; inline DB fallback)"
    lines.append(f"G0 {side} tools : OK (qemu-img + rethinkdb){extra}")
    if need_sparsify and caps.get("virt_sparsify") != "yes":
        lines.append(
            f"G0 {side} tools : WARN virt-sparsify missing; --sparsify will be skipped"
        )
    return True


def preflight_connectivity(remote_host, need_sparsify=False):
    """G0: self-verify SSH + local/remote docker + container tools, resolving auto-sudo.

    Sets LOCAL_DOCKER / REMOTE_DOCKER / REMOTE_SUDO. Returns (ok, report_lines)."""
    global LOCAL_DOCKER, REMOTE_DOCKER, REMOTE_SUDO
    lines = []
    ok = True

    pref, mode = _resolve_docker()
    if pref:
        LOCAL_DOCKER = pref
        lines.append(f"G0 local docker  : OK ({mode}) [{CONTAINER}]")
        if not _report_caps("local", _probe_capabilities(), need_sparsify, lines):
            ok = False
    else:
        ok = False
        hint = "is it running? docker perms?" + (
            "" if ALLOW_SUDO else " (sudo disabled by --no-sudo)"
        )
        lines.append(
            f"G0 local docker  : FAIL - cannot exec {CONTAINER} - {hint} {mode}"
        )

    st, err = _probe_ssh(remote_host)
    if st == "ok":
        lines.append(f"G0 ssh           : OK -> {remote_host}")
    elif st == "no_key":
        ok = False
        lines.append(
            f"G0 ssh           : FAIL -> {remote_host} - key NOT authorized. "
            f"Add the source public key to the destination ~/.ssh/authorized_keys."
        )
    elif st == "unreachable":
        ok = False
        lines.append(
            f"G0 ssh           : FAIL -> {remote_host} - unreachable. "
            f"Open port 22 / check the host. ({err})"
        )
    else:
        ok = False
        lines.append(f"G0 ssh           : FAIL -> {remote_host} - {err}")

    if st == "ok":
        rpref, rmode = _resolve_docker(remote_host)
        if rpref:
            REMOTE_DOCKER = rpref
            lines.append(f"G0 remote docker : OK ({rmode})")
            if not _report_caps(
                "remote", _probe_capabilities(remote_host), need_sparsify, lines
            ):
                ok = False
        else:
            ok = False
            lines.append(
                f"G0 remote docker : FAIL - cannot exec {CONTAINER} on destination "
                f"(docker perms / sudo). {rmode}"
            )
        wr = _ssh_run(remote_host, "test -w /opt/isard/templates && echo Y || echo N")
        REMOTE_SUDO = (wr.stdout or "").strip() != "Y"
        lines.append(
            "G0 remote write  : "
            + (
                "/opt/isard/templates writable (rsync direct)"
                if not REMOTE_SUDO
                else "/opt/isard/templates NOT writable -> rsync/mkdir via sudo"
            )
        )
    return ok, lines


# Prelude prepended to every DB program. Provides get_conn() (honouring env), the
# rethinkdb query object ``r``, and base64 helpers so inputs/outputs never need shell
# quoting (data travels as a base64 JSON literal inside the program, program on stdin).
_DB_PRELUDE = """\
import sys, os, json, base64
sys.path.insert(0, "/utils")
from rethinkdb import r
try:
    from storage_lib.db import get_conn
except Exception:
    from contextlib import contextmanager
    @contextmanager
    def get_conn():
        c = r.connect(host=os.environ.get("RETHINKDB_HOST", "isard-db"),
                      port=int(os.environ.get("RETHINKDB_PORT", "28015")),
                      db=os.environ.get("RETHINKDB_DB", "isard"), timeout=20)
        try:
            yield c
        finally:
            c.close(noreply_wait=False)
def _b64load(s):
    return json.loads(base64.b64decode(s).decode())
def _emit(obj):
    print("RESULT:" + base64.b64encode(json.dumps(obj).encode()).decode())
"""


def _db_call(body, inputs=None, remote_host=None, timeout=600):
    """Run a DB ``body`` program inside isard-storage with ``inputs`` (a JSON-able dict)
    embedded as base64, and return the object the program passes to _emit()."""
    blob = base64.b64encode(json.dumps(inputs or {}).encode()).decode()
    program = _DB_PRELUDE + "\nINPUT = _b64load('" + blob + "')\n" + body
    cp = _storage_py(program, remote_host=remote_host, timeout=timeout)
    if cp.returncode != 0:
        raise RuntimeError(
            "isard-storage DB op failed (rc={}): {}".format(
                cp.returncode, (cp.stderr or cp.stdout).strip()[:500]
            )
        )
    for line in cp.stdout.splitlines():
        if line.startswith("RESULT:"):
            return json.loads(base64.b64decode(line[len("RESULT:") :]).decode())
    raise RuntimeError(
        "isard-storage DB op returned no result (out={!r} err={!r})".format(
            cp.stdout[:300], cp.stderr[:300]
        )
    )


def _qemu_check(container_path, remote_host=None):
    """qemu-img check -U on a container path. Returns (ok, message)."""
    cp = _storage_cmd(
        ["qemu-img", "check", "-U", container_path], remote_host=remote_host
    )
    return cp.returncode == 0, (cp.stdout + cp.stderr).strip()


def _qemu_flat_estimate(container_path, remote_host=None):
    """Estimate the flattened copy's on-disk size in bytes: the sum of *actual*
    (allocated) sizes across the backing chain -- a safe upper bound for what
    `qemu-img convert` writes. Uses actual-size, NOT virtual-size, so sparse
    templates (small data, huge virtual size) are not falsely rejected. None if
    unknown."""
    cp = _storage_cmd(
        ["qemu-img", "info", "--output=json", "-U", "--backing-chain", container_path],
        remote_host=remote_host,
    )
    if cp.returncode != 0:
        return None
    try:
        chain = json.loads(cp.stdout)
        if isinstance(chain, dict):
            chain = [chain]
        total = sum(int(e.get("actual-size") or 0) for e in chain)
        # small margin for qcow2 metadata / cluster rounding
        return int(total * 1.05) + (64 << 20)
    except Exception:
        return None


def _is_file_in_use(container_path):
    """Detect a hypervisor lock by running qemu-img info WITHOUT -U. Returns (in_use, msg)."""
    cp = _storage_cmd(["qemu-img", "info", "--output=json", container_path])
    if cp.returncode == 0:
        return False, ""
    msg = cp.stderr + cp.stdout
    low = msg.lower()
    if "lock" in low or "in use" in low or "failed to get" in low:
        return True, msg.strip()
    return False, msg.strip()


def _sha256_local(path):
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ============================================================================
# DB programs (run inside isard-storage)
# ============================================================================

_FETCH_META = """
with get_conn() as conn:
    domain_id = INPUT["domain_id"]
    domain = r.table("domains").get(domain_id).run(conn)
    storage = None
    err = None
    if domain is None:
        err = "domain_not_found"
    elif domain.get("kind") != "template":
        err = "not_template:" + str(domain.get("kind"))
    else:
        disks = (domain.get("create_dict") or {}).get("hardware", {}).get("disks", [])
        if len(disks) != 1:
            err = "unsupported_disk_count:" + str(len(disks))
        else:
            sid = disks[0].get("storage_id")
            storage = r.table("storage").get(sid).run(conn) if sid else None
            if storage is None:
                err = "storage_not_found:" + str(sid)
    iface_names = {}
    if domain:
        for _if in (domain.get("create_dict") or {}).get("hardware", {}).get("interfaces", []) or []:
            iid = _if.get("id") if isinstance(_if, dict) else None
            if iid and iid not in iface_names:
                bi = r.table("interfaces").get(iid).run(conn)
                iface_names[iid] = (bi or {}).get("name")
    _emit({"error": err, "domain": domain, "storage": storage, "iface_names": iface_names})
"""

_CHECK = """
TABLE_FOR = {"interfaces": "interfaces", "graphics": "graphics", "videos": "videos",
             "media": "media", "vgpus": "reservables_vgpus",
             "hypervisors_pools": "hypervisors_pools"}
with get_conn() as conn:
    conflicts = []
    for did in INPUT.get("domain_ids", []):
        if r.table("domains").get(did).run(conn) is not None:
            conflicts.append(["domain", did])
    for sid in INPUT.get("storage_ids", []):
        if r.table("storage").get(sid).run(conn) is not None:
            conflicts.append(["storage", sid])
    ru = INPUT.get("remote_user")
    user = r.table("users").get(ru).run(conn) if ru else None
    missing = {}
    unverifiable = []
    for kind, ids in (INPUT.get("refs") or {}).items():
        ids = [i for i in set(ids) if i]
        tbl = TABLE_FOR.get(kind)
        if not ids or not tbl:
            missing[kind] = []
            continue
        try:
            existing = set(r.table(tbl).get_all(r.args(ids)).pluck("id")["id"].run(conn))
            missing[kind] = [i for i in ids if i not in existing]
        except Exception:
            missing[kind] = []
            unverifiable.append(kind)
    _emit({
        "conflicts": conflicts,
        "user_exists": user is not None,
        "user": {"username": user.get("username"), "category": user.get("category"),
                 "group": user.get("group")} if user else None,
        "missing": missing,
        "unverifiable": unverifiable,
    })
"""

_RESTORE = """
import subprocess as sp
with get_conn() as conn:
    domain = INPUT["domain"]
    storage = INPUT["storage"]
    ru = INPUT["remote_user"]
    opt = INPUT.get("opts", {})

    user = r.table("users").get(ru).run(conn)
    if user is None:
        _emit({"ok": False, "error": "remote_user_not_found:" + str(ru)}); sys.exit(0)
    if r.table("domains").get(domain["id"]).run(conn) is not None:
        _emit({"ok": False, "error": "domain_exists"}); sys.exit(0)
    if r.table("storage").get(storage["id"]).run(conn) is not None:
        _emit({"ok": False, "error": "storage_exists"}); sys.exit(0)

    # D7: the landed disk must be intact before it is registered.
    cpath = storage["directory_path"] + "/" + storage["id"] + "." + storage["type"]
    chk = sp.run(["qemu-img", "check", "-U", cpath], capture_output=True, text=True)
    if chk.returncode != 0:
        _emit({"ok": False, "error": "integrity_check_failed:" + ((chk.stderr or chk.stdout) or "")[:200]}); sys.exit(0)

    # Storage: flattened, standalone, ready, read-only, owned by the target user.
    storage["parent"] = None
    storage["status"] = "ready"
    storage["perms"] = ["r"]
    storage.pop("qemu-img-info", None)
    storage["user_id"] = ru
    storage.setdefault("status_logs", [])

    # Domain: ownership remap + safe portability resets.
    domain["status"] = "Stopped"
    domain["user"] = ru
    domain["username"] = user.get("username", domain.get("username"))
    domain["category"] = user["category"]
    domain["group"] = user["group"]
    if not opt.get("keep_hyp_pools"):
        domain["hypervisors_pools"] = ["default"]
        domain["forced_hyp"] = False
        domain["favourite_hyp"] = False
    domain["tag"] = False
    domain["tag_name"] = False
    domain["tag_visible"] = False
    domain["booking_id"] = False
    domain["parents"] = []
    domain.pop("duplicate_parent_template", None)

    cd = domain.setdefault("create_dict", {})
    hw = cd.setdefault("hardware", {})
    try:
        disk0 = hw["disks"][0]
        disk0["storage_id"] = storage["id"]
        for k in ("parent", "backing", "backing_file", "path", "file"):
            disk0.pop(k, None)
    except Exception:
        pass

    # Explicit, force-everything normalisations (operator opt-in).
    if opt.get("clear_vgpu"):
        cd["reservables"] = {"vgpus": None}
    if opt.get("clear_media"):
        hw["isos"] = []
        hw["floppies"] = []
    if opt.get("reset_network"):
        anyi = list(r.table("interfaces").limit(1)["id"].run(conn))
        defid = "default" if r.table("interfaces").get("default").run(conn) is not None else (anyi[0] if anyi else None)
        if defid:
            old = hw.get("interfaces") or [{}]
            mac = old[0].get("mac") if old and isinstance(old[0], dict) else None
            hw["interfaces"] = [{"id": defid, "mac": mac} if mac else {"id": defid}]

    # Referential auto-prune: any referenced id the destination does not have is
    # dropped (or replaced by the IsardVDI default), so a verbatim import never fails
    # on a missing resource. Warn-only -- the pruned ids are returned to the caller.
    pruned = {}

    def _existing(table, ids):
        ids = [i for i in set(ids) if i]
        if not ids:
            return set()
        try:
            return set(r.table(table).get_all(r.args(ids)).pluck("id")["id"].run(conn))
        except Exception:
            return set(ids)  # table absent / cannot verify -> keep as-is

    if not opt.get("reset_network"):
        # Interfaces are matched BY NAME: an interface named X on the source is
        # remapped to the destination interface that has the same name (ids differ
        # across installs for ovs/personal nets). Only names with no destination
        # match are dropped.
        ifaces = [i for i in (hw.get("interfaces") or []) if isinstance(i, dict)]
        if ifaces:
            try:
                tk_by_name = {ti["name"]: ti["id"]
                              for ti in r.table("interfaces").pluck("id", "name").run(conn)
                              if ti.get("name") is not None}
            except Exception:
                tk_by_name = None
            src_names = INPUT.get("iface_names") or {}
            kept, dropped, remapped = [], [], []
            for i in ifaces:
                bid = i.get("id")
                nm = src_names.get(bid)
                if tk_by_name is None:
                    tkid = bid  # cannot verify -> keep as-is
                elif nm is not None and nm in tk_by_name:
                    tkid = tk_by_name[nm]
                elif bid in set(tk_by_name.values()):
                    tkid = bid  # same id already exists on destination
                else:
                    tkid = None
                if tkid:
                    if tkid != bid:
                        remapped.append([nm, bid, tkid])
                    kept.append({**i, "id": tkid})
                else:
                    dropped.append(nm or bid)
            hw["interfaces"] = kept
            if dropped:
                pruned["interfaces"] = dropped
            if remapped:
                pruned["interfaces_remapped"] = remapped

    for key, table in (("graphics", "graphics"), ("videos", "videos")):
        vals = [x for x in (hw.get(key) or []) if isinstance(x, str)]
        ex = _existing(table, vals)
        keep = [x for x in vals if x in ex]
        if len(keep) != len(vals):
            pruned[key] = [x for x in vals if x not in ex]
            # display needs a device: fall back to the stock "default" if we emptied it
            if not keep and r.table(table).get("default").run(conn) is not None:
                keep = ["default"]
            hw[key] = keep

    if not opt.get("clear_media"):
        for key in ("isos", "floppies"):
            items = [it for it in (hw.get(key) or []) if isinstance(it, dict)]
            ex = _existing("media", [it.get("id") for it in items])
            drop = [it.get("id") for it in items if it.get("id") not in ex]
            if drop:
                pruned.setdefault("media", []).extend(drop)
                hw[key] = [it for it in items if it.get("id") in ex]

    if not opt.get("clear_vgpu"):
        vg = [x for x in ((cd.get("reservables") or {}).get("vgpus") or []) if isinstance(x, str)]
        ex = _existing("reservables_vgpus", vg)
        keep = [x for x in vg if x in ex]
        if len(keep) != len(vg):
            pruned["vgpus"] = [x for x in vg if x not in ex]
            cd.setdefault("reservables", {})["vgpus"] = keep or None

    if opt.get("keep_hyp_pools"):
        pools = [p for p in (domain.get("hypervisors_pools") or []) if isinstance(p, str)]
        ex = _existing("hypervisors_pools", pools)
        keep = [p for p in pools if p in ex]
        if len(keep) != len(pools):
            pruned["hypervisors_pools"] = [p for p in pools if p not in ex]
            domain["hypervisors_pools"] = keep or ["default"]

    # Atomic-ish insert with rollback of the storage row on domain failure.
    r.table("storage").insert(storage).run(conn)
    try:
        r.table("domains").insert(domain).run(conn)
    except Exception as e:
        try:
            r.table("storage").get(storage["id"]).delete().run(conn)
        except Exception:
            pass
        _emit({"ok": False, "error": "domain_insert_failed:" + str(e)}); sys.exit(0)

    _emit({"ok": True, "domain_id": domain["id"], "storage_id": storage["id"], "pruned": pruned})
"""


# ============================================================================
# Metadata + reference extraction
# ============================================================================


def fetch_template_metadata(domain_id):
    """Fetch domain+storage from the LOCAL install (via isard-storage) and derive paths."""
    res = _db_call(_FETCH_META, {"domain_id": domain_id})
    if res.get("error"):
        raise ValueError(f"{domain_id}: {res['error']}")
    domain, storage = res["domain"], res["storage"]

    disk_container = "{}/{}.{}".format(
        storage["directory_path"], storage["id"], storage["type"]
    )
    disk_host = Path(container_to_host_path(disk_container))

    card = domain.get("image") or {}
    card_url = card.get("url") if card.get("type") == "user" else None
    card_host = Path("/opt/isard") / card_url.lstrip("/") if card_url else None

    meta = {
        "domain": domain,
        "storage": storage,
        "domain_id": domain_id,
        "storage_id": storage["id"],
        "type": storage["type"],
        "directory_path": storage["directory_path"],
        "disk_container": disk_container,
        "disk_host": disk_host,
        "card_url": card_url,
        "card_host": card_host,
        "name": domain.get("name", domain_id),
        "iface_names": res.get("iface_names", {}),
    }
    meta["refs"] = _extract_refs(domain)
    return meta


def _extract_refs(domain):
    """Collect the destination-resolved hardware ids the template references."""
    cd = domain.get("create_dict") or {}
    hw = cd.get("hardware") or {}
    media = [
        m.get("id")
        for m in (hw.get("isos") or []) + (hw.get("floppies") or [])
        if isinstance(m, dict) and m.get("id")
    ]
    return {
        "interfaces": [
            i.get("id")
            for i in (hw.get("interfaces") or [])
            if isinstance(i, dict) and i.get("id")
        ],
        "graphics": [g for g in (hw.get("graphics") or []) if isinstance(g, str)],
        "videos": [v for v in (hw.get("videos") or []) if isinstance(v, str)],
        "media": media,
        "vgpus": [
            p
            for p in ((cd.get("reservables") or {}).get("vgpus") or [])
            if isinstance(p, str)
        ],
        "hypervisors_pools": [
            p for p in (domain.get("hypervisors_pools") or []) if isinstance(p, str)
        ],
    }


# ============================================================================
# Pre-flight gates (fail-closed)
# ============================================================================


def _remote_avail_bytes(remote_host, host_dir):
    cp = _ssh_run(
        remote_host,
        "df --output=avail -B1 {} 2>/dev/null | tail -n1".format(shlex.quote(host_dir)),
    )
    try:
        return int((cp.stdout or "").strip())
    except Exception:
        return None


def _remote_exists(remote_host, host_path):
    cp = _ssh_run(
        remote_host, "test -e {} && echo 1 || echo 0".format(shlex.quote(host_path))
    )
    return (cp.stdout or "").strip() == "1"


def gate_check(metas, remote_host, remote_user, opts):
    """Run all O*/D* gates. Returns {domain_id: {"block": [...], "warn": [...]}}."""
    domain_ids = [m["domain_id"] for m in metas]
    storage_ids = [m["storage_id"] for m in metas]
    refs_union = {}
    for kind in (
        "interfaces",
        "graphics",
        "videos",
        "media",
        "vgpus",
        "hypervisors_pools",
    ):
        refs_union[kind] = sorted({i for m in metas for i in m["refs"].get(kind, [])})

    conf = _db_call(
        _CHECK,
        {
            "domain_ids": domain_ids,
            "storage_ids": storage_ids,
            "remote_user": remote_user,
            "refs": refs_union,
        },
        remote_host=remote_host,
    )

    conflict_set = {(t, i) for t, i in conf.get("conflicts", [])}
    missing = conf.get("missing", {})
    if conf.get("unverifiable"):
        logger.warning(
            "Could not verify on destination (table absent?): %s",
            ", ".join(conf["unverifiable"]),
        )

    avail_remote = _remote_avail_bytes(remote_host, "/opt/isard/templates")
    try:
        avail_local = shutil.disk_usage(str(CONVERTING_FOLDER)).free
    except Exception:
        avail_local = None

    verdicts = {}
    need_local_total = 0
    for m in metas:
        did, sid = m["domain_id"], m["storage_id"]
        block, warn = [], []

        # O4: source disk present and not mid-write.
        if not m["disk_host"].exists():
            block.append(f"O1/O4: source disk missing: {m['disk_host']}")
        else:
            st = m["storage"].get("status") or ""
            if st not in ("ready",):
                block.append(f"O4: source storage status={st!r} (not 'ready')")
            in_use, _ = _is_file_in_use(m["disk_container"])
            if in_use:
                warn.append(
                    "O4: source disk reports a lock (template base read with -U)"
                )

        # D1/D2: id collisions on the destination.
        if ("domain", did) in conflict_set:
            block.append("D1: domain id already exists on destination")
        if ("storage", sid) in conflict_set:
            block.append("D2: storage id already exists on destination")

        # D6: target user.
        if not conf.get("user_exists"):
            block.append(f"D6: --remote-user not found on destination: {remote_user}")

        # D5 / O5: free space (estimate = flattened actual size, not virtual).
        est = _qemu_flat_estimate(m["disk_container"]) or 0
        m["est_size"] = est
        need_local_total += est
        if avail_remote is not None and est > avail_remote:
            block.append(
                f"D5: insufficient destination space (need~{est}, avail {avail_remote})"
            )

        # D3: do not clobber an existing user-card file on the destination.
        if m["card_host"] and _remote_exists(remote_host, str(m["card_host"])):
            block.append(
                f"D3: card file already exists on destination: {m['card_host']}"
            )

        # D9: referential integrity. Missing refs are NOT fatal -- on import the
        # restore step prunes them from the domain (or substitutes the IsardVDI
        # default), so a verbatim import never fails on a missing resource. Warn-only.
        for kind in REF_KINDS:
            miss = [
                i for i in m["refs"].get(kind, []) if i in set(missing.get(kind, []))
            ]
            if miss:
                warn.append(
                    f"D9: {kind} not on destination {miss} -> will be pruned/defaulted on import"
                )

        verdicts[did] = {"block": block, "warn": warn}

    if avail_local is not None and need_local_total > avail_local:
        for did in verdicts:
            verdicts[did]["block"].append(
                f"O5: insufficient local space for conversion (need~{need_local_total}, avail {avail_local})"
            )
    return verdicts


# ============================================================================
# Convert / transfer
# ============================================================================


def convert_disk(meta, cfg):
    """Flatten the template disk into a standalone copy (resumable, integrity-checked)."""
    out_host = CONVERTING_FOLDER / "{}.qcow2".format(meta["storage_id"])
    out_container = host_to_container_path(out_host)
    src_container = meta["disk_container"]
    single = cfg.get("workers", 2) == 1

    # Ensure the staging dir exists inside the container (the host dir may be
    # root-owned, e.g. where /opt/isard/templates is not user-writable).
    _storage_cmd(["mkdir", "-p", host_to_container_path(str(CONVERTING_FOLDER))])

    # Resume: reuse an existing valid converted copy instead of regenerating it.
    if out_host.exists():
        ok, _ = _qemu_check(out_container)
        if ok:
            logger.info("[%s] reusing existing converted disk (resume)", meta["name"])
            return out_host
        logger.info("[%s] discarding invalid leftover converted disk", meta["name"])
        _storage_cmd(["rm", "-f", out_container])

    in_use, msg = _is_file_in_use(src_container)
    if in_use:
        logger.warning(
            "[%s] source disk reports in-use; reading read-only with -U: %s",
            meta["name"],
            msg[:120],
        )

    qemu = [
        "qemu-img",
        "convert",
        "-U",
        "-f",
        meta["type"],
        "-O",
        "qcow2",
        "-W",
        "-m",
        "16",
    ]
    if cfg.get("compress"):
        qemu.append("-c")
    if single:
        qemu.append("-p")
    qemu += [src_container, out_container]

    logger.info("[%s] flattening disk -> %s", meta["name"], out_host.name)
    cp = _storage_cmd(qemu, capture=not single)
    if cp.returncode != 0:
        _storage_cmd(["rm", "-f", out_container])
        detail = ""
        if cp is not None and getattr(cp, "stderr", None):
            detail = ": " + cp.stderr.strip()[:200]
        raise RuntimeError(f"qemu-img convert failed (rc={cp.returncode}){detail}")
    if not out_host.exists():
        raise FileNotFoundError(f"converted file not found: {out_host}")

    ok, info = _qemu_check(out_container)
    if not ok:
        _storage_cmd(["rm", "-f", out_container])
        raise RuntimeError(f"integrity check failed after convert: {info[:200]}")

    if cfg.get("sparsify"):
        logger.info("[%s] sparsifying (virt-sparsify --in-place)", meta["name"])
        sp = _storage_cmd(["virt-sparsify", "--in-place", out_container])
        if sp.returncode != 0:
            logger.warning(
                "[%s] sparsify failed (continuing with unsparsified copy): %s",
                meta["name"],
                (sp.stderr or sp.stdout).strip()[:200],
            )
        else:
            ok2, info2 = _qemu_check(out_container)
            if not ok2:
                _storage_cmd(["rm", "-f", out_container])
                raise RuntimeError(
                    f"integrity check failed after sparsify: {info2[:200]}"
                )
    return out_host


def rsync_file(source, destination, cfg, progress=False):
    """Resumable rsync of a single file (no compression, partial + append-verify).

    --append-verify provides resume (continue a partial dest, verifying the overlap);
    it is rsync's own transfer mode and is incompatible with -W/--whole-file, so -W is
    not passed. A first transfer to an absent destination already sends the whole file;
    an interrupted one resumes by appending the missing tail."""
    cmd = ["rsync", "-a", "--partial", "--append-verify", "-e", _rsh()]
    if REMOTE_SUDO:
        cmd += ["--rsync-path", "sudo -n rsync"]
    cmd += ["--info=progress2"] if progress else ["--info=flist0,name0,stats0"]
    if cfg.get("bwlimit"):
        cmd += ["--bwlimit", str(cfg["bwlimit"])]
    cmd += [str(source), destination]
    cp = (
        subprocess.run(cmd)
        if progress
        else subprocess.run(cmd, capture_output=True, text=True)
    )
    if cp.returncode != 0:
        detail = ""
        if not progress and getattr(cp, "stderr", None):
            detail = ": " + cp.stderr.strip()[:300]
        raise RuntimeError(f"rsync failed (rc={cp.returncode}){detail}")


def insecure_net_transfer(source, remote_host, dest_host_path, cfg):
    """Opt-in plaintext disk transport over nc for trusted high-throughput links.

    Offset-resumable and sha256-verified. SSH is still used for control. Requires
    ``nc`` on both ends and an open ``--insecure-net-port`` between them.
    """
    port = cfg.get("insecure_net_port", 9920)
    host_only = remote_host.split("@")[-1]
    src_size = source.stat().st_size

    sz = _ssh_run(
        remote_host,
        "stat -c %s {} 2>/dev/null || echo 0".format(shlex.quote(dest_host_path)),
    )
    try:
        off = int((sz.stdout or "0").strip() or "0")
    except Exception:
        off = 0
    if off > src_size:
        off = 0
    if off == src_size:
        logger.info("[insecure-net] destination already complete, verifying checksum")
    else:
        if off:
            logger.info("[insecure-net] resuming from offset %d / %d", off, src_size)
        listener = "truncate -s {off} {p} 2>/dev/null; nc -l -p {port} >> {p}".format(
            off=off, p=shlex.quote(dest_host_path), port=port
        )
        lp = subprocess.Popen(_ssh_prefix(remote_host) + [listener])
        time.sleep(1.5)
        send = "dd if={src} bs=1M iflag=skip_bytes skip={off} 2>/dev/null | nc -N {host} {port}".format(
            src=shlex.quote(str(source)),
            off=off,
            host=shlex.quote(host_only),
            port=port,
        )
        rc = subprocess.run(["sh", "-c", send])
        try:
            lp.wait(timeout=60)
        except Exception:
            lp.kill()
        if rc.returncode != 0:
            raise RuntimeError(
                "insecure-net transfer failed (nc rc={}); check the port/firewall or use --fast".format(
                    rc.returncode
                )
            )

    local_sha = _sha256_local(source)
    rs = _ssh_run(
        remote_host, "sha256sum {} | cut -d' ' -f1".format(shlex.quote(dest_host_path))
    )
    if (rs.stdout or "").strip() != local_sha:
        raise RuntimeError(
            "insecure-net checksum mismatch after transfer (use --fast for a verified resumable transfer)"
        )
    logger.info("[insecure-net] checksum verified")


def transfer_one(meta, remote_host, remote_user, cfg):
    """Full per-template pipeline: convert -> transfer -> remote restore. Returns (id, ok, msg)."""
    did = meta["domain_id"]
    try:
        converted = convert_disk(meta, cfg)

        dest_dir_host = container_to_host_path(
            meta["directory_path"]
        )  # /opt/isard/templates
        _sudo = "sudo -n " if REMOTE_SUDO else ""
        _ssh_run(remote_host, _sudo + "mkdir -p {}".format(shlex.quote(dest_dir_host)))
        dest_file_host = "{}/{}.{}".format(
            dest_dir_host, meta["storage_id"], meta["type"]
        )

        if cfg.get("insecure_net"):
            insecure_net_transfer(converted, remote_host, dest_file_host, cfg)
        else:
            rsync_file(
                converted,
                "{}:{}".format(remote_host, dest_file_host),
                cfg,
                progress=(cfg.get("workers", 2) == 1),
            )

        # User card (only present for image.type == "user"; stock cards exist on both installs).
        if meta["card_host"] and meta["card_host"].exists():
            _ssh_run(
                remote_host,
                _sudo
                + "mkdir -p {}".format(shlex.quote(str(meta["card_host"].parent))),
            )
            rsync_file(
                meta["card_host"],
                "{}:{}/".format(remote_host, str(meta["card_host"].parent)),
                cfg,
            )

        res = _db_call(
            _RESTORE,
            {
                "domain": meta["domain"],
                "storage": meta["storage"],
                "remote_user": remote_user,
                "opts": cfg.get("restore_opts", {}),
                "iface_names": meta.get("iface_names", {}),
            },
            remote_host=remote_host,
        )
        if not res.get("ok"):
            return (did, False, "restore: " + str(res.get("error")))
        meta["_pruned"] = res.get("pruned") or {}
        if meta["_pruned"]:
            logger.warning(
                "[%s] pruned/defaulted refs missing on destination: %s",
                meta["name"],
                meta["_pruned"],
            )

        if not cfg.get("keep_converted") and converted.exists():
            _storage_cmd(["rm", "-f", host_to_container_path(str(converted))])
            logger.info("[%s] removed local converted disk", meta["name"])

        return (did, True, "")
    except Exception as e:
        return (did, False, str(e))


# ============================================================================
# Orchestration
# ============================================================================


def _snapshot_source(meta, want_hash=False):
    try:
        st = meta["disk_host"].stat()
        meta["_src_snap"] = (
            st.st_size,
            int(st.st_mtime),
            _sha256_local(meta["disk_host"]) if want_hash else None,
        )
    except Exception:
        meta["_src_snap"] = None


def _verify_source_untouched(metas, want_hash=False):
    changed = []
    for m in metas:
        before = m.get("_src_snap")
        if not before:
            continue
        try:
            st = m["disk_host"].stat()
            now = (
                st.st_size,
                int(st.st_mtime),
                _sha256_local(m["disk_host"]) if want_hash else None,
            )
        except Exception:
            changed.append((m["name"], "stat failed"))
            continue
        if (now[0], now[1]) != (before[0], before[1]) or (
            want_hash and now[2] != before[2]
        ):
            changed.append((m["name"], "size/mtime/hash changed"))
    for name, why in changed:
        logger.error("O1 VIOLATION: source disk modified for %s (%s)", name, why)
    return not changed


_REVIEW_LABELS = {
    "interfaces": "interfaces/networks NOT mapped (no destination network with that name) -> REMOVED from template",
    "interfaces_remapped": "interfaces remapped by name to destination ids [name, src_id, dst_id]",
    "media": "media (ISO/floppy) not on destination -> DETACHED",
    "vgpus": "vGPU profiles not on destination -> DROPPED",
    "graphics": "graphics not on destination -> DROPPED",
    "videos": "videos not on destination -> DROPPED",
    "hypervisors_pools": "hypervisor pools not on destination -> RESET to default",
}


def _confirm_or_abort(passed, blocked, bad, verdicts, assume_yes):
    """Safety gate before the destructive phase. Returns True to proceed.

    With --yes this is non-interactive (logs a one-line note). Without it, prints a
    warning that summarises what WILL be auto-resolved on import (networks that will
    not map, refs that will be pruned/defaulted) and prompts for explicit confirmation.
    """
    if assume_yes:
        logger.info("--yes set: skipping interactive confirmation.")
        return True

    logger.warning("=" * 78)
    logger.warning("WARNING: about to MODIFY the destination install (no --yes given).")
    logger.warning(
        "  %d template(s) will be copied and inserted into the destination DB"
        "  |  %d blocked  |  %d metadata-failed.",
        len(passed),
        len(blocked),
        len(bad),
    )
    flagged = [
        (m["name"], verdicts[m["domain_id"]]["warn"])
        for m in passed
        if verdicts[m["domain_id"]]["warn"]
    ]
    if flagged:
        logger.warning(
            "  The following will be auto-pruned/defaulted on import"
            " (a manual-review report is printed at the end):"
        )
        for name, warns in flagged:
            for w in warns:
                logger.warning("    %-40s %s", name, w)
    logger.warning("=" * 78)

    if not sys.stdin.isatty():
        logger.error(
            "Refusing to proceed: not an interactive terminal and --yes was not given. "
            "Re-run with --yes to confirm non-interactively."
        )
        return False
    try:
        ans = (
            input("Proceed with the transfer? Type 'yes' to continue: ").strip().lower()
        )
    except EOFError:
        ans = ""
    if ans not in ("y", "yes"):
        logger.error("Aborted by operator (no confirmation).")
        return False
    return True


def _print_manual_review(passed, blocked, bad, results, verdicts):
    """End-of-run report of everything auto-resolved that a human should verify."""
    reviewed = [(m["name"], m["_pruned"]) for m in passed if m.get("_pruned")]
    failed = [(d, msg) for d, good, msg in results if not good]

    if not (reviewed or blocked or bad or failed):
        logger.info(
            "MANUAL REVIEW: none — every template imported with all references mapped."
        )
        return

    logger.info("=" * 78)
    logger.info("MANUAL REVIEW REQUIRED — verify the following on the destination:")
    for name, pr in reviewed:
        logger.info("  %s:", name)
        for key in (
            "interfaces",
            "interfaces_remapped",
            "media",
            "vgpus",
            "graphics",
            "videos",
            "hypervisors_pools",
        ):
            if pr.get(key):
                logger.info("    - %s: %s", _REVIEW_LABELS.get(key, key), pr[key])
    if blocked:
        logger.info("  BLOCKED (not transferred):")
        for m in blocked:
            logger.info(
                "    - %-40s %s",
                m["name"],
                "; ".join(verdicts[m["domain_id"]]["block"]),
            )
    if failed:
        logger.info("  TRANSFER FAILED (left no destination record):")
        for did, msg in failed:
            logger.info("    - %s  %s", did, msg)
    if bad:
        logger.info("  METADATA-FAILED (could not be read on source):")
        for did, msg in bad:
            logger.info("    - %s  %s", did, msg)
    logger.info("=" * 78)


def run_transfer(domain_ids, remote_host, remote_user, cfg, dry_run=False):
    logger.info("=" * 78)
    logger.info("ISARDVDI TEMPLATE TRANSFER%s", "  [DRY RUN]" if dry_run else "")
    logger.info(
        "templates=%d  remote=%s  remote-user=%s  workers=%d",
        len(domain_ids),
        remote_host,
        remote_user,
        cfg.get("workers", 2),
    )
    if cfg.get("insecure_net"):
        logger.info("transport=insecure-net (PLAINTEXT nc, LAN only)")
    elif cfg.get("fast"):
        logger.info(
            "transport=fast (cipher=%s, no-compression, whole-file, multiplexed)",
            SSH_CONFIG.get("cipher"),
        )
    logger.info("=" * 78)

    # G0: self-verify the SSH path + local/remote docker, resolving auto-sudo. This
    # is the core of --dry-run and aborts before any work if the path isn't usable.
    g0_ok, g0_lines = preflight_connectivity(
        remote_host, need_sparsify=cfg.get("sparsify")
    )
    for ln in g0_lines:
        logger.info(ln)
    if not g0_ok:
        logger.error("Pre-flight connectivity FAILED — resolve the above and retry.")
        return False

    metas, bad = [], []
    for did in domain_ids:
        try:
            metas.append(fetch_template_metadata(did))
        except Exception as e:
            bad.append((did, str(e)))
            logger.error("metadata: %s", e)
    if not metas:
        logger.error("No valid templates to process")
        return False

    verdicts = gate_check(metas, remote_host, remote_user, cfg.get("restore_opts", {}))

    logger.info("PRE-FLIGHT GATES:")
    passed = []
    for m in metas:
        v = verdicts[m["domain_id"]]
        if v["block"]:
            logger.info("  ABORT  %-40s %s", m["name"], "; ".join(v["block"]))
        else:
            passed.append(m)
            extra = ("  [warn: " + "; ".join(v["warn"]) + "]") if v["warn"] else ""
            logger.info("  PASS   %-40s%s", m["name"], extra)

    blocked = [m for m in metas if verdicts[m["domain_id"]]["block"]]

    if dry_run:
        logger.info(
            "DRY RUN: no changes made. would-transfer=%d blocked=%d metadata-failed=%d",
            len(passed),
            len(blocked),
            len(bad),
        )
        return not blocked and not bad

    if not passed:
        logger.error("Nothing to transfer after gates")
        return False
    if blocked:
        logger.warning(
            "%d template(s) blocked by gates and will be skipped", len(blocked)
        )

    if not _confirm_or_abort(passed, blocked, bad, verdicts, cfg.get("assume_yes")):
        return False

    for m in passed:
        _snapshot_source(m, want_hash=cfg.get("verify_source_hash"))

    results = []
    with ThreadPoolExecutor(max_workers=cfg.get("workers", 2)) as executor:
        futures = {
            executor.submit(transfer_one, m, remote_host, remote_user, cfg): m
            for m in passed
        }
        for fut in as_completed(futures):
            results.append(fut.result())

    _verify_source_untouched(passed, want_hash=cfg.get("verify_source_hash"))

    ok = [d for d, good, _ in results if good]
    logger.info("=" * 78)
    for did, good, msg in sorted(results, key=lambda x: (x[1], x[0])):
        logger.info(
            "  %-4s %s%s", "OK" if good else "FAIL", did, "" if good else "  - " + msg
        )
    logger.info(
        "Transferred %d/%d (blocked=%d, metadata-failed=%d)",
        len(ok),
        len(passed),
        len(blocked),
        len(bad),
    )
    logger.info("=" * 78)

    _print_manual_review(passed, blocked, bad, results, verdicts)
    return len(ok) == len(passed) and not blocked and not bad


# ============================================================================
# Legacy local dump / restore (backward compatibility)
# ============================================================================


def _require_rethinkdb():
    if r is None:
        raise RuntimeError(
            "The legacy dump/restore commands need the python 'rethinkdb' module on this host "
            "(pip install rethinkdb), or use 'transfer-templates' which runs through isard-storage."
        )


def _legacy_conn():
    _require_rethinkdb()
    try:
        ip = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                "isard-db",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:
        ip = ""
    return r.connect(host=ip or "isard-db", port=28015, db="isard")


def origin_dump(domain_id):
    """Legacy: dump a single domain to /opt/isard/dump/<...> locally."""
    conn = _legacy_conn()
    try:
        domain = r.table("domains").get(domain_id).run(conn)
        if domain is None:
            print(f"Domain {domain_id} not found")
            return
        domain["status"] = "Stopped"
        print(f"Domain {domain['kind']} - {domain['name']} - {domain['id']} found")
        domain_name = domain["name"].replace(" ", "_").replace("/", "_")
        folder = Path(f"/opt/isard/dump/{domain['kind']}_{domain_name}_{domain['id']}")
        folder.mkdir(parents=True, exist_ok=True)
        if domain.get("image", {}).get("type") == "user" and domain.get(
            "image", {}
        ).get("url"):
            image_path = Path("/opt/isard") / domain["image"]["url"].lstrip("/")
            if image_path.exists():
                (folder / domain["image"]["id"]).write_bytes(image_path.read_bytes())
        storage = (
            r.table("storage")
            .get(domain["create_dict"]["hardware"]["disks"][0]["storage_id"])
            .run(conn)
        )
        (folder / "domain.json").write_text(
            json.dumps({"storage": storage, "domain": domain})
        )
        storage_path = Path(
            container_to_host_path(
                f"{storage['directory_path']}/{storage['id']}.{storage['type']}"
            )
        )
        if storage_path.exists():
            subprocess.run(
                ["rsync", "-av", "--progress", str(storage_path), str(folder)],
                check=False,
            )
    finally:
        conn.close()


def destination_restore(user_id):
    """Legacy: restore domains found under /opt/isard/dump into the local DB."""
    conn = _legacy_conn()
    try:
        user = r.table("users").get(user_id).run(conn)
        if user is None:
            print(f"User {user_id} not found")
            return
        for folder in Path("/opt/isard/dump").iterdir():
            if not folder.is_dir():
                continue
            print(f"Restoring {folder.parts[-1]}")
            data = json.loads((folder / "domain.json").read_text())
            storage, domain = data["storage"], data["domain"]
            if r.table("storage").get(storage["id"]).run(conn) is not None:
                print(
                    f"Storage {storage['id']} already exists. Skipping {domain['id']}"
                )
                continue
            if r.table("domains").get(domain["id"]).run(conn) is not None:
                print(f"Domain {domain['id']} already exists. Skipping")
                continue
            domain["user"] = user_id
            domain["category"] = user["category"]
            domain["group"] = user["group"]
            storage["user_id"] = user_id
            storage["parent"] = None
            storage["status"] = "ready"
            r.table("storage").insert(storage).run(conn)
            domain["create_dict"]["hardware"]["disks"][0]["storage_id"] = storage["id"]
            r.table("domains").insert(domain).run(conn)
            if domain.get("image", {}).get("type") == "user" and domain.get(
                "image", {}
            ).get("url"):
                image_path = folder / domain["image"]["id"]
                dest = Path("/opt/isard") / domain["image"]["url"].lstrip("/")
                if image_path.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(image_path), str(dest))
            dest_dir = Path(container_to_host_path(storage["directory_path"]))
            src = folder / f"{storage['id']}.{storage['type']}"
            if src.exists():
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(
                    str(src), str(dest_dir / f"{storage['id']}.{storage['type']}")
                )
            print(
                f"Domain {domain['kind']} - {domain['name']} - {domain['id']} restored"
            )
    finally:
        conn.close()


# ============================================================================
# CLI
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="IsardVDI Template Transfer Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Transfer templates to another install, re-owned to a destination user
  %(prog)s transfer-templates --domains UUID1,UUID2 \\
      --remote-host root@dest-host --remote-user <dest-user-id> --fast

  # Dry run: show every pre-flight gate, change nothing
  %(prog)s transfer-templates --domains-file tpls.txt \\
      --remote-host root@dest-host --remote-user <dest-user-id> --dry-run

  # Slow WAN: shrink before sending
  %(prog)s transfer-templates --domains UUID1 \\
      --remote-host root@host --remote-user U --sparsify --compress

  # Trusted LAN, maximum throughput (plaintext disk transport)
  %(prog)s transfer-templates --domains UUID1 \\
      --remote-host root@host --remote-user U --insecure-net
        """,
    )
    sub = parser.add_subparsers(dest="command", help="Command to execute")

    t = sub.add_parser(
        "transfer-templates", help="Transfer templates to a remote install"
    )
    t.add_argument("--domains", help="Comma-separated domain UUIDs")
    t.add_argument("--domains-file", help="File with one domain UUID per line")
    t.add_argument(
        "--remote-host", required=True, help="Remote SSH host (user@hostname)"
    )
    t.add_argument(
        "--remote-user",
        help="Destination user id to own the imported templates (required)",
    )
    t.add_argument(
        "--workers", type=int, default=2, help="Parallel workers (default: 2)"
    )
    t.add_argument(
        "--keep-converted", action="store_true", help="Keep local converted disks"
    )
    t.add_argument(
        "--dry-run", action="store_true", help="Run all gates, change nothing"
    )
    t.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip the interactive pre-transfer confirmation (non-interactive use). "
        "Without it, the tool warns and prompts before modifying the destination.",
    )
    t.add_argument(
        "--remote-db-container",
        default="isard-storage",
        help="Container used for DB/qemu ops on both sides (default: isard-storage)",
    )
    # speed / transport
    t.add_argument(
        "--fast",
        action="store_true",
        help="No compression + whole-file + multiplexing + aes-gcm cipher (resumable)",
    )
    t.add_argument(
        "--ssh-cipher",
        help="SSH cipher (e.g. aes128-gcm@openssh.com, chacha20-poly1305@openssh.com)",
    )
    t.add_argument(
        "--insecure-net",
        action="store_true",
        help="PLAINTEXT disk transport over nc (trusted LAN only; SSH still used for control)",
    )
    t.add_argument(
        "--insecure-net-port",
        type=int,
        default=9920,
        help="Port for --insecure-net (default 9920)",
    )
    t.add_argument(
        "--bwlimit", help="rsync bandwidth limit (e.g. 200000 = ~200MB/s); unset = max"
    )
    t.add_argument(
        "--secure-ssh",
        action="store_true",
        help="Verify host keys (accept-new) instead of disabling",
    )
    t.add_argument(
        "--compress",
        action="store_true",
        help="Compress the disk during convert (qemu-img -c)",
    )
    t.add_argument(
        "--sparsify",
        action="store_true",
        help="virt-sparsify the converted copy (reclaim free space)",
    )
    t.add_argument(
        "--verify-source-hash",
        action="store_true",
        help="sha256 the source disk before/after to prove it was untouched (slower)",
    )
    # destination normalisation (unblock missing references)
    t.add_argument(
        "--reset-network",
        action="store_true",
        help="Point interfaces at the destination 'default' interface",
    )
    t.add_argument(
        "--clear-vgpu", action="store_true", help="Drop vGPU reservation on import"
    )
    t.add_argument(
        "--clear-media", action="store_true", help="Detach ISOs/floppies on import"
    )
    t.add_argument(
        "--keep-hyp-pools",
        action="store_true",
        help="Keep hypervisors_pools/forced_hyp instead of resetting to defaults",
    )
    t.add_argument(
        "--no-sudo",
        action="store_true",
        help="Never escalate with sudo; fail if docker/rsync/mkdir need it",
    )

    dump_p = sub.add_parser("dump", help="Legacy: dump a domain locally")
    dump_p.add_argument("domain_id")
    restore_p = sub.add_parser("restore", help="Legacy: restore local dumps")
    restore_p.add_argument("user_id")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    if args.command == "transfer-templates":
        global CONTAINER, ALLOW_SUDO
        CONTAINER = args.remote_db_container
        ALLOW_SUDO = not args.no_sudo
        if args.compress and args.fast:
            logger.error("--compress and --fast are mutually exclusive")
            return 1
        if not args.remote_user:
            logger.error(
                "--remote-user is required (the destination owner of the imported templates)"
            )
            return 1

        SSH_CONFIG["strict_hostkey"] = args.secure_ssh
        SSH_CONFIG["compression"] = False
        SSH_CONFIG["multiplex"] = True
        SSH_CONFIG["cipher"] = args.ssh_cipher or (
            "aes128-gcm@openssh.com" if args.fast else None
        )

        if args.insecure_net and args.workers > 1:
            logger.warning(
                "--insecure-net uses a fixed port; forcing --workers 1 to avoid collisions"
            )
            args.workers = 1

        if args.domains:
            domain_ids = [d.strip() for d in args.domains.split(",") if d.strip()]
        elif args.domains_file:
            with open(args.domains_file) as f:
                domain_ids = [line.strip() for line in f if line.strip()]
        else:
            logger.error("Specify --domains or --domains-file")
            return 1

        cfg = {
            "workers": args.workers,
            "assume_yes": args.yes,
            "keep_converted": args.keep_converted,
            "fast": args.fast,
            "compress": args.compress,
            "sparsify": args.sparsify,
            "insecure_net": args.insecure_net,
            "insecure_net_port": args.insecure_net_port,
            "bwlimit": args.bwlimit,
            "verify_source_hash": args.verify_source_hash,
            "restore_opts": {
                "reset_network": args.reset_network,
                "clear_vgpu": args.clear_vgpu,
                "clear_media": args.clear_media,
                "keep_hyp_pools": args.keep_hyp_pools,
            },
        }
        ok = run_transfer(
            domain_ids, args.remote_host, args.remote_user, cfg, dry_run=args.dry_run
        )
        return 0 if ok else 1

    elif args.command == "dump":
        origin_dump(args.domain_id)
        return 0
    elif args.command == "restore":
        destination_restore(args.user_id)
        return 0


if __name__ == "__main__":
    sys.exit(main())
