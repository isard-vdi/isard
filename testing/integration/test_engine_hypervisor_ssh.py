# SPDX-License-Identifier: AGPL-3.0-or-later

"""The engine reaches the hypervisor over SSH with its own key, the way it registers it."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time

import pytest

rethinkdb = pytest.importorskip("rethinkdb")
from rethinkdb import r  # noqa: E402

pytestmark = pytest.mark.real

ENGINE = os.environ.get("E2E_ENGINE_CONTAINER", "isard-engine")
HYPERVISOR = os.environ.get("E2E_HYPER_CONTAINER", "isard-hypervisor")
HYPER_ID = os.environ.get("E2E_HYPER_ID", "isard-hypervisor")
OPENSSH_SERVER_FLOOR = "10.3_p1-r2"
ONLINE_TIMEOUT = 300

# the engine's own helper, so the test follows its paramiko options
ENGINE_PARAMIKO = """
import json, sys
from engine.services.lib.functions import exec_remote_cmd
host, port, user = sys.argv[1], int(sys.argv[2]), sys.argv[3]
out = exec_remote_cmd("id -un", host, username=user, port=port, timeout=20)
print("RESULT " + json.dumps({k: v.decode() for k, v in out.items()}))
"""

# what must be refused: no key at all, a key the hypervisor does not know, a guessed password
PARAMIKO_REFUSED = """
import json, os, subprocess, sys, tempfile
import paramiko
host, port, user = sys.argv[1], int(sys.argv[2]), sys.argv[3]
results = {}
with tempfile.TemporaryDirectory() as tmp:
    key = os.path.join(tmp, "stranger")
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key], check=True)
    transport = paramiko.Transport((host, port))
    try:
        transport.start_client(timeout=20)
        transport.auth_none(user)
        results["no_key"] = "connected"
    except paramiko.AuthenticationException:
        results["no_key"] = "refused"
    finally:
        transport.close()
    cases = {
        "unknown_key": {"key_filename": key},
        "wrong_password": {"password": "not-the-hypervisor-secret"},
    }
    for name, extra in cases.items():
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(host, port=port, username=user, timeout=20, banner_timeout=20,
                           look_for_keys=False, allow_agent=False, **extra)
            results[name] = "connected"
        except paramiko.AuthenticationException:
            results[name] = "refused"
        except Exception as exc:
            results[name] = f"error: {type(exc).__name__}: {exc}"
        finally:
            client.close()
print("RESULT " + json.dumps(results))
"""

STRANGER_SSH = """
set -e
d=$(mktemp -d)
trap 'rm -rf "$d"' EXIT
ssh-keygen -q -t ed25519 -N "" -f "$d/k"
ssh -i "$d/k" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=10 \
    -o PreferredAuthentications=publickey -p "$2" "$3@$1" true
"""


def _exec(container, *argv, stdin=None, timeout=90):
    try:
        p = subprocess.run(
            ["docker", "exec", *(["-i"] if stdin else []), container, *argv],
            input=stdin,
            stdin=None if stdin else subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"{argv[0]} in {container} hung for {timeout}s: {exc}")
    return p.returncode, p.stdout, p.stderr


def _result(stdout):
    for line in stdout.splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[len("RESULT ") :])
    return None


@pytest.fixture(scope="module")
def hyper():
    if shutil.which("docker") is None:
        pytest.skip("needs the docker CLI to exec into the engine and the hypervisor")
    host = os.environ.get("RETHINKDB_HOST", "isard-db")
    port = int(os.environ.get("RETHINKDB_PORT", "28015"))
    try:
        conn = r.connect(
            host=host, port=port, db=os.environ.get("RETHINKDB_DB", "isard")
        )
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"RethinkDB not reachable at {host}:{port}: {exc}")
    deadline = time.monotonic() + ONLINE_TIMEOUT
    with conn:
        while True:
            row = r.table("hypervisors").get(HYPER_ID).run(conn)
            if row and row.get("status") == "Online":
                break
            if time.monotonic() > deadline:
                pytest.fail(
                    f"hypervisor {HYPER_ID} is not Online after {ONLINE_TIMEOUT}s "
                    f"(status={row and row.get('status')!r}): the engine cannot reach it"
                )
            time.sleep(3)
    return row["hostname"], str(row["port"]), row.get("user") or "root"


def test_engine_libvirt_over_ssh(hyper):
    host, port, user = hyper
    uri = f"qemu+ssh://{user}@{host}:{port}/system"
    rc, out, err = _exec(ENGINE, "virsh", "-c", uri, "hostname")
    assert rc == 0, f"virsh -c {uri} failed from {ENGINE} (rc={rc}): {err.strip()}"
    assert out.strip(), f"virsh -c {uri} hostname printed nothing"


def test_engine_openssh_client_uses_key_and_known_hosts(hyper):
    host, port, user = hyper
    rc, out, err = _exec(
        ENGINE,
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "PreferredAuthentications=publickey",
        "-o", "ConnectTimeout=10",
        "-p", port,
        f"{user}@{host}",
        "id -un",
    )  # fmt: skip
    assert rc == 0, (
        f"{ENGINE} cannot ssh to {user}@{host}:{port} with its key and known_hosts "
        f"(rc={rc}): {err.strip()}"
    )
    assert out.strip() == user


def test_engine_paramiko_command(hyper):
    host, port, user = hyper
    rc, out, err = _exec(
        ENGINE, "python3", "-", host, port, user, stdin=ENGINE_PARAMIKO
    )
    result = _result(out)
    assert rc == 0 and result is not None, (
        f"exec_remote_cmd to {user}@{host}:{port} failed in {ENGINE} (rc={rc}): "
        f"{err.strip()[-2000:]}"
    )
    assert result["out"].strip() == user, f"unexpected answer: {result!r}"


def test_hypervisor_refuses_anything_but_the_engine_key(hyper):
    host, port, user = hyper
    rc, out, err = _exec(
        ENGINE, "python3", "-", host, port, user, stdin=PARAMIKO_REFUSED
    )
    result = _result(out)
    assert rc == 0 and result is not None, f"control script failed: {err.strip()}"
    assert result == {
        "no_key": "refused",
        "unknown_key": "refused",
        "wrong_password": "refused",
    }, f"the hypervisor sshd let in a client without the engine key: {result!r}"

    rc, _, err = _exec(ENGINE, "sh", "-s", host, port, user, stdin=STRANGER_SSH)
    assert rc != 0, "ssh with a key missing from authorized_keys was accepted"
    assert "Permission denied" in err, f"unexpected ssh failure: {err.strip()}"


def test_hypervisor_openssh_server_meets_the_floor():
    rc, out, err = _exec(HYPERVISOR, "apk", "list", "--installed", "openssh-server")
    match = re.search(r"^openssh-server-(\S+)\s", out, re.MULTILINE)
    assert rc == 0 and match, f"openssh-server is not installed: {out}{err}"
    installed = match.group(1)
    rc, out, err = _exec(
        HYPERVISOR, "apk", "version", "-t", installed, OPENSSH_SERVER_FLOOR
    )
    assert out.strip() in {">", "="}, (
        f"openssh-server {installed} is older than {OPENSSH_SERVER_FLOOR} "
        f"(apk version -t: {out.strip()!r} {err.strip()})"
    )
