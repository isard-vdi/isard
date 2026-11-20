# SPDX-License-Identifier: AGPL-3.0-or-later

"""Run a command inside a started guest through its qemu-guest-agent.

Shells out to ``virsh qemu-agent-command`` in the hypervisor container, the
only place the agent is reachable; used to read the guest's xrdp session log.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time

HYPER_CONTAINER = os.environ.get("E2E_HYPER_CONTAINER", "isard-hypervisor")


def _agent(domain_id: str, command: dict, hyper: str, timeout: float) -> dict:
    proc = subprocess.run(
        [
            "docker",
            "exec",
            hyper,
            "virsh",
            "qemu-agent-command",
            domain_id,
            json.dumps(command),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"qemu-agent-command failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)["return"]


def run(
    domain_id: str,
    command: str,
    *,
    hyper: str = HYPER_CONTAINER,
    timeout: float = 30.0,
    wait: float = 25.0,
) -> tuple[int, str, str]:
    """Run ``sh -c command`` in the guest; return (exit code, stdout, stderr)."""
    pid = _agent(
        domain_id,
        {
            "execute": "guest-exec",
            "arguments": {
                "path": "/bin/sh",
                "arg": ["-c", command],
                "capture-output": True,
            },
        },
        hyper,
        timeout,
    )["pid"]
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        status = _agent(
            domain_id,
            {"execute": "guest-exec-status", "arguments": {"pid": pid}},
            hyper,
            timeout,
        )
        if status.get("exited"):
            decode = lambda b: base64.b64decode(b or "").decode(errors="replace")
            return (
                status.get("exitcode", -1),
                decode(status.get("out-data")),
                decode(status.get("err-data")),
            )
        time.sleep(0.5)
    raise TimeoutError(f"guest command did not finish in {wait}s: {command!r}")
