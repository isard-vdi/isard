# SPDX-License-Identifier: AGPL-3.0-or-later

"""Drive a real FreeRDP login against the guest over the VPN, headless via Xvfb.

The container joins isard-vpn's netns because the guest overlay IP is reachable
only there; the verdict is read from the guest's sesman log, not FreeRDP.
"""

from __future__ import annotations

import os
import subprocess

IMAGE = os.environ.get("E2E_FREERDP_IMAGE", "isard-it-freerdp:local")
ALPINE = os.environ.get(
    "E2E_FREERDP_BASE",
    "alpine:3.21@sha256:bc21487101ae47172509130ee1092cc273a831968d64b617776d1f69c81e42ab",
)
VPN_CONTAINER = os.environ.get("E2E_VPN_CONTAINER", "isard-vpn")


def ensure_image() -> None:
    if (
        subprocess.run(
            ["docker", "image", "inspect", IMAGE], capture_output=True
        ).returncode
        == 0
    ):
        return
    dockerfile = f"FROM {ALPINE}\nRUN apk add --no-cache freerdp xvfb xvfb-run\n"
    subprocess.run(
        ["docker", "build", "-t", IMAGE, "-"],
        input=dockerfile.encode(),
        check=True,
        capture_output=True,
        timeout=900,
    )


def attempt_login(
    guest_ip: str,
    username: str,
    password: str,
    *,
    hold: int = 12,
    vpn: str = VPN_CONTAINER,
) -> subprocess.CompletedProcess:
    """Connect and log in, holding the session open for ``hold`` seconds."""
    # Own Xvfb rather than xvfb-run (which hangs under busybox sh, leaking the
    # container); timeout -k wraps only xfreerdp so PID 1 always exits.
    rdp = (
        f"timeout -k 5 {hold} xfreerdp /v:{guest_ip}:3389 "
        f"/u:{username} /p:{password} /cert:ignore /sec:tls "
        "-clipboard -sound -microphone /log-level:ERROR"
    )
    cmd = (
        "Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp >/dev/null 2>&1 & xvfb=$!; "
        f"sleep 2; DISPLAY=:99 {rdp}; kill $xvfb 2>/dev/null; exit 0"
    )
    return subprocess.run(
        ["docker", "run", "--rm", f"--network=container:{vpn}", IMAGE, "sh", "-c", cmd],
        capture_output=True,
        text=True,
        timeout=hold + 60,
    )
