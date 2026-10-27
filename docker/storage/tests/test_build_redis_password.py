# SPDX-License-Identifier: AGPL-3.0-or-later

"""build.sh gives isard-redis a password and asks every other node for it."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
BUILD = ROOT / "build.sh"
FUNCTIONS = (
    "default_secret",
    "has_part",
    "generate_secrets",
    "secret_unused_by_part",
    "require_secrets",
)

WEB = "network db redis apiv4 storage backupninja"
HYPERVISOR = "network video hypervisor websockify squid squid-hypervisor stats storage"
API_SECRETS = {
    "API_ISARDVDI_SECRET": "own-isardvdi",
    "API_HYPERVISORS_SECRET": "own-hypervisors",
}
LINE = re.compile(r"^REDIS_PASSWORD=(.*)$", re.M)


def _functions():
    source = BUILD.read_text(encoding="utf-8")
    secret_names = re.search(r'^SECRET_NAMES="(.+)"$', source, re.M).group(1)
    bodies = []
    for name in FUNCTIONS:
        match = re.search(rf"^{name}\(\)\s*\{{\n.*?^\}}\n", source, re.M | re.S)
        assert match, f"build.sh no longer defines {name}()"
        bodies.append(match.group(0))
    return (
        f'SECRET_NAMES="{secret_names}"\nPARTS_PATH={ROOT}/docker-compose-parts\n'
        + "".join(bodies)
    )


def _run(tmp_path, script, **env):
    shutil.copy(ROOT / "isardvdi.cfg.example", tmp_path / "isardvdi.cfg.example")
    return subprocess.run(
        ["sh", "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], **env},
    )


def _generate(tmp_path, cfg, parts=WEB):
    (tmp_path / "isardvdi.cfg").write_text(cfg, encoding="utf-8")
    script = (
        f'{_functions()}flavour_parts(){{ echo "{parts}"; }}\n'
        "generate_secrets isardvdi.cfg\n"
    )
    done = _run(tmp_path, script)
    assert done.returncode == 0, done.stderr
    return LINE.findall((tmp_path / "isardvdi.cfg").read_text(encoding="utf-8"))


def _require(tmp_path, flavour, parts, **env):
    script = (
        f'{_functions()}FLAVOUR="{flavour}"\nrequire_secrets isardvdi.cfg {parts}\n'
    )
    return _run(tmp_path, script, **env)


@pytest.fixture(autouse=True)
def _needs_sh():
    if shutil.which("sh") is None:
        pytest.skip("build.sh is shell")


@pytest.mark.parametrize(
    "cfg",
    ["FLAVOUR=web\nREDIS_PASSWORD=\n", "FLAVOUR=web\n#REDIS_PASSWORD=\n"],
    ids=["empty", "commented"],
)
def test_the_node_with_redis_generates_a_hex_password_once(tmp_path, cfg):
    first = _generate(tmp_path, cfg)

    assert len(first) == 1
    assert re.fullmatch(r"[0-9a-f]{64}", first[0])
    assert _generate(tmp_path, (tmp_path / "isardvdi.cfg").read_text()) == first


def test_the_node_with_redis_keeps_a_password_it_already_has(tmp_path):
    assert _generate(tmp_path, "FLAVOUR=web\nREDIS_PASSWORD=kept/+=\n") == ["kept/+="]


def test_a_node_without_redis_never_generates_one(tmp_path):
    assert _generate(tmp_path, "FLAVOUR=hypervisor\n", parts=HYPERVISOR) == []


def test_a_hypervisor_with_storage_workers_needs_the_password(tmp_path):
    done = _require(
        tmp_path, "hypervisor", HYPERVISOR, REDIS_WORKERS="1", **API_SECRETS
    )

    assert done.returncode == 1
    assert "REDIS_PASSWORD" in done.stderr


def test_a_hypervisor_without_storage_workers_builds_without_it(tmp_path):
    done = _require(
        tmp_path, "hypervisor", HYPERVISOR, REDIS_WORKERS="0", **API_SECRETS
    )

    assert done.returncode == 0, done.stderr


def test_backupninja_without_storage_workers_still_needs_it(tmp_path):
    done = _require(
        tmp_path,
        "hypervisor",
        f"{HYPERVISOR} backupninja",
        REDIS_WORKERS="0",
        **API_SECRETS,
    )

    assert done.returncode == 1
    assert "REDIS_PASSWORD" in done.stderr


def test_a_remote_node_with_the_password_builds(tmp_path):
    done = _require(
        tmp_path,
        "hypervisor",
        f"{HYPERVISOR} backupninja",
        REDIS_WORKERS="1",
        REDIS_PASSWORD="0123abcd",
        **API_SECRETS,
    )

    assert done.returncode == 0, done.stderr


FAKE_DOCKER = """#!/bin/sh
if [ "$1 $2 $3" = "exec isard-redis printenv" ]; then echo stack-secret; exit 0; fi
if [ "$1" = run ]; then printf '%s\\n' "REDIS_PASSWORD=${REDIS_PASSWORD-unset} $*" >> "$RUNS"; fi
"""


@pytest.mark.parametrize("target", ["test-integration", "ci-test-integration"])
def test_the_integration_runner_gets_the_stack_redis_password(tmp_path, target):
    if shutil.which("make") is None:
        pytest.skip("needs make")
    (tmp_path / "docker").write_text(FAKE_DOCKER, encoding="utf-8")
    (tmp_path / "docker").chmod(0o755)
    runs = tmp_path / "runs"
    done = subprocess.run(
        ["make", "-C", str(BUILD.parent), target],
        capture_output=True,
        text=True,
        env={"PATH": f"{tmp_path}:{os.environ['PATH']}", "RUNS": str(runs), "CI": "1"},
    )
    assert done.returncode == 0, done.stdout + done.stderr
    [runner] = [r for r in runs.read_text().splitlines() if "testing/integration/" in r]
    assert runner.startswith("REDIS_PASSWORD=stack-secret ")
    assert " -e REDIS_PASSWORD " in runner
    assert "stack-secret" not in done.stdout + done.stderr
