#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A build.sh that fails to render the compose must leave the previous one in place."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

BUILD = Path(__file__).resolve().parents[3] / "build.sh"

OLD = "services:\n  isard-old:\n    image: old\n"
NEW = "services:\n  isard-new:\n    image: new\n    volumes:\n      - type: bind\n        bind: {}\n"

FAKE_COMPOSE = """#!/bin/sh
if [ "$FAKE_COMPOSE_FAIL" = "true" ]; then
    echo 'service "isard-x" depends on undefined service "isard-redis": invalid compose project' >&2
    exit 15
fi
printf '%s' "$FAKE_COMPOSE_OUT"
"""


def _function(name):
    source = BUILD.read_text(encoding="utf-8")
    return re.search(rf"^{name}\(\)\s*\{{\n.*?^\}}\n", source, re.M | re.S).group(0)


@pytest.fixture(autouse=True)
def _needs_sh():
    if shutil.which("sh") is None:
        pytest.skip("build.sh is shell")


@pytest.fixture
def workdir(tmp_path):
    parts = tmp_path / "docker-compose-parts"
    parts.mkdir()
    (parts / "network.yml").write_text("services: {}\n", encoding="utf-8")
    fake = tmp_path / "fake-compose"
    fake.write_text(FAKE_COMPOSE, encoding="utf-8")
    fake.chmod(0o755)
    return tmp_path


def _merge(workdir, config_name="", fail=False):
    script = (
        "set -e\n"
        f"{_function('parts_files')}{_function('merge')}"
        f'merge "" "{config_name}" network\n'
    )
    return subprocess.run(
        ["sh", "-c", script],
        cwd=workdir,
        capture_output=True,
        text=True,
        env={
            "PATH": os.environ["PATH"],
            "DOCKER_COMPOSE": str(workdir / "fake-compose"),
            "PARTS_PATH": "docker-compose-parts",
            "FAKE_COMPOSE_FAIL": "true" if fail else "false",
            "FAKE_COMPOSE_OUT": NEW,
        },
    )


@pytest.mark.parametrize("config_name", ["", "web"])
def test_a_failed_render_keeps_the_previous_compose(workdir, config_name):
    target = workdir / (
        f"docker-compose.{config_name}.yml" if config_name else "docker-compose.yml"
    )
    target.write_text(OLD, encoding="utf-8")

    done = _merge(workdir, config_name, fail=True)

    assert done.returncode != 0, "a failed render must fail the build"
    assert target.read_text(encoding="utf-8") == OLD
    assert "undefined service" in done.stderr


def test_a_failed_render_leaves_no_stray_compose_file(workdir):
    """Later steps edit ``docker-compose*.yml`` by glob."""
    (workdir / "docker-compose.yml").write_text(OLD, encoding="utf-8")

    _merge(workdir, fail=True)

    assert sorted(p.name for p in workdir.iterdir() if "compose" in p.name) == [
        "docker-compose-parts",
        "docker-compose.yml",
        "fake-compose",
    ]


def test_a_failed_first_render_creates_no_empty_compose(workdir):
    done = _merge(workdir, fail=True)

    assert done.returncode != 0
    assert not (workdir / "docker-compose.yml").exists()


def test_a_good_render_replaces_the_compose_with_the_bind_fix_applied(workdir):
    (workdir / "docker-compose.yml").write_text(OLD, encoding="utf-8")

    done = _merge(workdir)

    assert done.returncode == 0, done.stdout + done.stderr
    rendered = (workdir / "docker-compose.yml").read_text(encoding="utf-8")
    assert "isard-new" in rendered
    assert "bind: {create_host_path: true}" in rendered
    assert not [p for p in workdir.iterdir() if p.name.startswith(".docker-compose")]
