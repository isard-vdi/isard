#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A node that serves no storage must not publish pool space.

``REDIS_WORKERS=0`` and ``CAPABILITIES_DISK=false`` each say this node runs no
storage worker, so it holds no pool: every pool path resolves to whatever
filesystem contains it, which is the root disk. Published under the pool's key
that figure is not merely useless -- the first writer owns the key for its whole
TTL, so the node that does hold the pool cannot correct it, and every free-space
decision reads the root disk of a machine that was never storing anything.

The guard lives in shell, so this runs the shell.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

INIT = Path(__file__).resolve().parents[3] / "storage" / "init.sh"
PUBLISHER = "/utils/storage-pool-physical"
CAPABILITY = "_cap_disk=$(printf"
MARKER = "# --- Storage pool space"


def _block():
    """The publishing decision, from the capability it reads to the end of its if."""
    lines = INIT.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(CAPABILITY))
    marker = next(i for i, line in enumerate(lines) if line.startswith(MARKER))
    end = next(i for i, line in enumerate(lines[marker:], marker) if line == "fi")
    return "\n".join(lines[start : end + 1])


def _run(tmp_path, **env):
    """Run the block with a stubbed publisher; return True when it launched."""
    stub_dir = tmp_path / "utils"
    stub_dir.mkdir()
    stub = stub_dir / "storage-pool-physical"
    launched = tmp_path / "launched"
    stub.write_text(f"#!/bin/sh\ntouch {launched}\n", encoding="utf-8")
    stub.chmod(0o755)

    script = _block().replace(PUBLISHER, str(stub))
    subprocess.run(
        ["sh", "-c", script + "\nwait\n"],
        check=True,
        capture_output=True,
        env={"PATH": os.environ["PATH"], **env},
    )
    return launched.exists()


@pytest.fixture(autouse=True)
def _needs_sh():
    if shutil.which("sh") is None:
        pytest.skip("the guard is shell")


def test_a_node_without_storage_workers_publishes_nothing(tmp_path):
    assert _run(tmp_path, REDIS_WORKERS="0") is False


def test_a_node_without_the_disk_capability_publishes_nothing(tmp_path):
    """The other switch that stops the fleet must stop the publisher too."""
    assert _run(tmp_path, REDIS_WORKERS="10", CAPABILITIES_DISK="false") is False


def test_the_capability_is_read_the_way_the_hypervisor_writes_it(tmp_path):
    """strtobool accepts False/no/off on the hypervisor side; so must this."""
    assert _run(tmp_path, REDIS_WORKERS="10", CAPABILITIES_DISK="False") is False


def test_a_storage_node_still_publishes(tmp_path):
    assert _run(tmp_path, REDIS_WORKERS="10") is True


def test_the_default_still_publishes(tmp_path):
    """No REDIS_WORKERS at all keeps the pre-existing behaviour."""
    assert _run(tmp_path) is True


def test_the_sidecar_still_wins_over_the_in_process_publisher(tmp_path):
    assert _run(tmp_path, REDIS_WORKERS="10", STORAGE_POOL_VDO_STATS="true") is False


def test_the_sidecar_does_not_resurrect_a_workerless_node(tmp_path):
    assert _run(tmp_path, REDIS_WORKERS="0", STORAGE_POOL_VDO_STATS="true") is False


def test_the_guard_reads_the_same_variables_the_workers_do():
    """Both gates must move together, or one of them stops meaning anything."""
    block = _block()
    for variable in (r"\$\{REDIS_WORKERS:-1\}", r"\$\{_cap_disk_enabled\}"):
        assert re.search(variable, block)
        assert re.search(variable, INIT.read_text(encoding="utf-8"))
