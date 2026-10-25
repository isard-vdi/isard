# SPDX-License-Identifier: AGPL-3.0-or-later

"""The portal's runtime maps are pushed again into the worker every reload starts."""

from __future__ import annotations

import shutil
import subprocess
import time

import pytest

pytestmark = pytest.mark.real

PORTAL = "isard-portal"
SOCKET = "/var/run/haproxy.sock"
MAP = "virt@subdomains"


def _portal(*cmd: str) -> str:
    return subprocess.run(
        ["docker", "exec", PORTAL, *cmd],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout


def _admin(command: str) -> str:
    return _portal("sh", "-c", f'echo "{command}" | socat stdio unix-connect:{SOCKET}')


def _worker() -> int:
    for line in _admin("show info").splitlines():
        if line.startswith("Pid: "):
            return int(line.split()[1])
    raise AssertionError("show info has no Pid line")


def _entries() -> set[str]:
    return {
        line.split()[1]
        for line in _admin(f"show map {MAP}").splitlines()
        if len(line.split()) >= 2
    }


def _wait_new_worker(old: int, timeout: float = 30) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pid = _worker()
        if pid != old:
            return pid
        time.sleep(0.2)
    raise AssertionError(f"HAProxy worker {old} was never replaced")


def _wait_entries(expected: set[str], timeout: float = 60) -> tuple[int, set[str]]:
    deadline = time.monotonic() + timeout
    while True:
        pid, got = _worker(), _entries()
        if got == expected or time.monotonic() > deadline:
            return pid, got
        time.sleep(0.5)


@pytest.fixture(scope="module")
def synced_entries() -> set[str]:
    if shutil.which("docker") is None:
        pytest.skip("needs the docker CLI to reach the portal's admin socket")
    try:
        _admin("show info")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"cannot reach the portal's admin socket: {exc}")

    deadline = time.monotonic() + 60
    while not (entries := _entries()):
        if time.monotonic() > deadline:
            pytest.fail(f"{MAP} is still empty: the startup sync never reached HAProxy")
        time.sleep(1)
    return entries


def test_a_reload_keeps_the_maps(synced_entries):
    old = _worker()
    _portal("haproxy-reload")
    new = _wait_new_worker(old)

    pid, got = _wait_entries(synced_entries)
    assert pid == new
    assert got == synced_entries


def test_a_reload_after_an_unsignalled_one_keeps_the_maps(synced_entries):
    # a reload haproxy-sync is not told about, as an operator's kill -USR2 1 does
    first = _worker()
    _portal("kill", "-USR2", "1")
    second = _wait_new_worker(first)

    _portal("haproxy-reload")
    third = _wait_new_worker(second)

    pid, got = _wait_entries(synced_entries)
    assert pid == third
    assert got == synced_entries
