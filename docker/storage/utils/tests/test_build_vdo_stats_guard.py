#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A node that serves no storage must not get the pool-space sidecar either.

``isard-storage-vdo-stats`` runs the very same publisher as isard-storage and
its compose part is not given ``REDIS_WORKERS``, so the guard in ``init.sh``
cannot reach it: with the sidecar enabled, a worker-less node goes back to
publishing its root disk under the pool's key, and the first writer owns that
key for its whole TTL. The variable is read from the cfg, and the cfg is only
read at build time, so the composition is where this is decided.

The guard lives in shell, so this runs the shell.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

BUILD = Path(__file__).resolve().parents[4] / "build.sh"
MARKER = "# The VDO fill needs a privileged container"
END = "# Add openapi container"


def _block():
    """The vdo-stats part selection, from its banner to the next section."""
    lines = BUILD.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().startswith(MARKER))
    end = next(i for i, line in enumerate(lines[start:], start) if line.strip() == END)
    return "\n".join(lines[start:end])


def _parts(flavour="hypervisor", parts="network storage stats backupninja", **env):
    """Run the block over a flavour's parts; return the parts it leaves behind."""
    script = (
        f'set -e\nFLAVOUR="{flavour}"\nparts="{parts}"\n{_block()}\necho "$parts"\n'
    )
    done = subprocess.run(
        ["sh", "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], **env},
    )
    return done.stdout.strip().split("\n")[-1].split()


@pytest.fixture(autouse=True)
def _needs_sh():
    if shutil.which("sh") is None:
        pytest.skip("the guard is shell")


def test_a_node_without_storage_workers_gets_no_sidecar():
    assert "storage-vdo-stats" not in _parts(
        STORAGE_POOL_VDO_STATS="true", REDIS_WORKERS="0"
    )


def test_a_node_without_the_disk_capability_gets_no_sidecar():
    assert "storage-vdo-stats" not in _parts(
        STORAGE_POOL_VDO_STATS="true", REDIS_WORKERS="10", CAPABILITIES_DISK="False"
    )


def test_a_storage_node_still_gets_the_sidecar():
    assert "storage-vdo-stats" in _parts(
        STORAGE_POOL_VDO_STATS="true", REDIS_WORKERS="10"
    )


def test_the_default_still_gets_the_sidecar():
    """No REDIS_WORKERS at all keeps the pre-existing behaviour."""
    assert "storage-vdo-stats" in _parts(STORAGE_POOL_VDO_STATS="true")


def test_the_sidecar_stays_out_when_it_was_never_asked_for():
    assert "storage-vdo-stats" not in _parts(REDIS_WORKERS="10")


def test_a_flavour_without_storage_still_gets_the_warning_and_no_part():
    assert "storage-vdo-stats" not in _parts(
        flavour="web", parts="network db portal", STORAGE_POOL_VDO_STATS="true"
    )


def test_an_unreadable_worker_count_does_not_abort_the_build():
    """build.sh runs under `set -e`: a numeric test on a typo would end it here."""
    assert "storage-vdo-stats" in _parts(
        STORAGE_POOL_VDO_STATS="true", REDIS_WORKERS="two"
    )


def test_the_guard_reads_the_same_variables_the_workers_do():
    """Both gates must move together, or one of them stops meaning anything."""
    init = (BUILD.parent / "docker" / "storage" / "init.sh").read_text(encoding="utf-8")
    for variable in (r"\$\{REDIS_WORKERS:-1\}", r"\$\{CAPABILITIES_DISK:-true\}"):
        assert re.search(variable, _block())
        assert re.search(variable, init)
