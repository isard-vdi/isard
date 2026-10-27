# SPDX-License-Identifier: AGPL-3.0-or-later

"""Removing a domain deletes its certificate file, also when acme.sh never issued it."""

from __future__ import annotations

import shutil
import subprocess

import pytest

pytestmark = pytest.mark.real

PORTAL = "isard-portal"
DOMAIN = "e2e-real-custom-cert.example.com"
PEM = f"/certs/{DOMAIN}.pem"


def _portal(*cmd: str) -> str:
    return subprocess.run(
        ["docker", "exec", PORTAL, *cmd],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout


@pytest.fixture
def custom_cert():
    if shutil.which("docker") is None:
        pytest.skip("needs the docker CLI to reach the portal")
    try:
        _portal("sh", "-c", f"echo custom > {PEM}")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"cannot reach the portal: {exc}")

    yield

    _portal("rm", "-f", PEM)


@pytest.mark.usefixtures("custom_cert")
def test_removing_a_custom_certificate_deletes_its_file():
    _portal("acme-remove-cert.sh", DOMAIN, f"{DOMAIN}.pem")

    assert (
        _portal("sh", "-c", f"test -e {PEM} && echo present || echo gone") == "gone\n"
    )
