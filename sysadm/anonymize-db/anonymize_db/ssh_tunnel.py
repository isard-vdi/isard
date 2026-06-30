"""SSH `-L` tunnel context manager."""

from __future__ import annotations

import contextlib
import logging
import socket
import subprocess
import time

log = logging.getLogger(__name__)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_open(host: str, port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with contextlib.suppress(OSError):
            with socket.create_connection((host, port), timeout=1.0):
                return
        time.sleep(0.2)
    raise TimeoutError(f"tunnel port {host}:{port} never accepted connections")


@contextlib.contextmanager
def ssh_tunnel(
    ssh_user_host: str,
    ssh_port: int,
    remote_host: str,
    remote_port: int,
    local_port: int | None = None,
):
    """Open `ssh -L local:remote_host:remote_port -p ssh_port user@jump`.

    Yields the local port. Tunnel is torn down on exit (success or exception).
    Relies on the user's SSH agent / key config; never prompts.
    """
    local = local_port or _free_port()
    cmd = [
        "ssh",
        "-N",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "BatchMode=yes",
        "-L",
        f"{local}:{remote_host}:{remote_port}",
        "-p",
        str(ssh_port),
        ssh_user_host,
    ]
    log.info(
        "opening tunnel: 127.0.0.1:%d -> %s:%d via %s",
        local,
        remote_host,
        remote_port,
        ssh_user_host,
    )
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        _wait_open("127.0.0.1", local)
        yield local
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
        log.info("tunnel closed (port %d)", local)


def parse_ssh_target(spec: str) -> tuple[str, int]:
    """Parse `user@host[:port]` -> (`user@host`, port)."""
    if ":" in spec.rsplit("@", 1)[-1]:
        head, port = spec.rsplit(":", 1)
        return head, int(port)
    return spec, 22


def parse_host_port(spec: str, default_port: int) -> tuple[str, int]:
    if ":" in spec:
        h, p = spec.rsplit(":", 1)
        return h, int(p)
    return spec, default_port
