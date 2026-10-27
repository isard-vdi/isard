# SPDX-License-Identifier: AGPL-3.0-or-later

"""A node is asked only for the secrets that something it runs reads."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
BUILD = ROOT / "build.sh"
FUNCTIONS = ("default_secret", "has_part", "secret_unused_by_part", "require_secrets")

HYPERVISOR = "network video hypervisor websockify squid squid-hypervisor stats storage"
SECRETS = {
    "API_ISARDVDI_SECRET": "own-isardvdi",
    "API_HYPERVISORS_SECRET": "own-hypervisors",
}


def _functions():
    source = BUILD.read_text(encoding="utf-8")
    secret_names = re.search(r'^SECRET_NAMES="(.+)"$', source, re.M).group(1)
    bodies = []
    for name in FUNCTIONS:
        match = re.search(rf"^{name}\(\)\s*\{{\n.*?^\}}\n", source, re.M | re.S)
        assert match, f"build.sh no longer defines {name}()"
        bodies.append(match.group(0))
    return (
        f'SECRET_NAMES="{secret_names}"\nPARTS_PATH=docker-compose-parts\n'
        + "".join(bodies)
    )


def _require(flavour, parts, **env):
    script = (
        f'{_functions()}FLAVOUR="{flavour}"\nrequire_secrets isardvdi.cfg {parts}\n'
    )
    return subprocess.run(
        ["sh", "-c", script],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={"PATH": os.environ["PATH"], **env},
    )


@pytest.fixture(autouse=True)
def _needs_sh():
    if shutil.which("sh") is None:
        pytest.skip("the check is shell")


def test_a_hypervisor_without_storage_workers_builds_without_the_isardvdi_secret():
    done = _require(
        "hypervisor",
        HYPERVISOR,
        REDIS_WORKERS="0",
        API_HYPERVISORS_SECRET="own-hypervisors",
    )
    assert done.returncode == 0, done.stderr


def test_a_video_node_builds_without_the_isardvdi_secret():
    done = _require(
        "video-standalone",
        "network video websockify squid stats",
        API_HYPERVISORS_SECRET="own-hypervisors",
    )
    assert done.returncode == 0, done.stderr


def test_a_hypervisor_with_storage_workers_still_needs_the_isardvdi_secret():
    done = _require(
        "hypervisor",
        HYPERVISOR,
        REDIS_WORKERS="1",
        API_HYPERVISORS_SECRET="own-hypervisors",
    )
    assert done.returncode == 1
    assert "API_ISARDVDI_SECRET" in done.stderr


def test_a_hypervisor_with_backups_still_needs_the_isardvdi_secret():
    done = _require(
        "hypervisor",
        f"{HYPERVISOR} backupninja",
        REDIS_WORKERS="0",
        API_HYPERVISORS_SECRET="own-hypervisors",
    )
    assert done.returncode == 1
    assert "API_ISARDVDI_SECRET" in done.stderr


def test_stats_on_a_web_node_still_needs_the_isardvdi_secret():
    done = _require("web", "network stats")
    assert done.returncode == 1
    assert "API_ISARDVDI_SECRET" in done.stderr


def test_stats_told_to_run_as_web_on_a_hypervisor_still_needs_the_isardvdi_secret():
    done = _require(
        "hypervisor",
        HYPERVISOR,
        REDIS_WORKERS="0",
        STATS_FLAVOUR="web",
        API_HYPERVISORS_SECRET="own-hypervisors",
    )
    assert done.returncode == 1
    assert "API_ISARDVDI_SECRET" in done.stderr


def test_a_hypervisor_without_storage_workers_still_needs_the_hypervisors_secret():
    done = _require("hypervisor", HYPERVISOR, REDIS_WORKERS="0")
    assert done.returncode == 1
    assert "API_HYPERVISORS_SECRET" in done.stderr
    assert "API_ISARDVDI_SECRET" not in done.stderr


def test_a_hypervisor_with_both_secrets_builds():
    done = _require(
        "hypervisor",
        f"{HYPERVISOR} backupninja",
        REDIS_WORKERS="1",
        REDIS_PASSWORD="0123abcd",
        **SECRETS,
    )
    assert done.returncode == 0, done.stderr
