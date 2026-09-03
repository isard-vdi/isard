#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""What the cfg says about disk work decides the storage composition.

``CAPABILITIES_DISK`` is what a node declares it does; without it isard-storage
starts and goes straight to sleeping, so the container does not belong in the
composition at all. ``REDIS_WORKERS`` is how many threads that container runs.
Either at zero means the node serves no storage, and then it must not get the
pool-space sidecar either: ``isard-storage-vdo-stats`` runs the very same
publisher and its compose part is never handed ``REDIS_WORKERS``, so the guard
in ``init.sh`` cannot reach it -- a worker-less node would go back to publishing
its root disk under the pool's key, and the first writer owns that key for its
whole TTL. Both variables come from the cfg, and the cfg is only read at build
time, so the composition is where this is decided.

The decision lives in shell, so this runs the shell.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

BUILD = Path(__file__).resolve().parents[4] / "build.sh"
MARKER = "# Normalised the way init.sh normalises it"
END = "# Add openapi container"


def _block():
    """The storage composition decision, from its banner to the next section."""
    lines = BUILD.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().startswith(MARKER))
    end = next(i for i, line in enumerate(lines[start:], start) if line.strip() == END)
    return "\n".join(lines[start:end])


def _run(flavour="hypervisor", parts="network storage stats backupninja", **env):
    """Run the block over a flavour's parts; return the completed process."""
    source = BUILD.read_text(encoding="utf-8")
    storage_key = re.search(r'^STORAGE_KEY="(.+)"$', source, re.M).group(1)
    # the real helper, so the part-name matching under test is the shipped one
    remove_part = re.search(
        r"^remove_part\(\) \{\n.*?^\}\n", source, re.M | re.S
    ).group(0)
    script = (
        f'set -e\n{remove_part}STORAGE_KEY="{storage_key}"\nFLAVOUR="{flavour}"\n'
        f'parts="{parts}"\n{_block()}\necho "$parts"\n'
    )
    return subprocess.run(
        ["sh", "-c", script],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], **env},
    )


def _parts(flavour="hypervisor", parts="network storage stats backupninja", **env):
    """The parts the block leaves behind, when it is allowed to leave any."""
    done = _run(flavour, parts, **env)
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout.strip().split("\n")[-1].split()


@pytest.fixture(autouse=True)
def _needs_sh():
    if shutil.which("sh") is None:
        pytest.skip("the guard is shell")


def test_a_node_without_storage_workers_gets_no_sidecar():
    assert "storage-vdo-stats" not in _parts(
        STORAGE_POOL_VDO_STATS="true", REDIS_WORKERS="0"
    )


def test_a_node_without_the_disk_capability_gets_no_storage_container():
    assert "storage" not in _parts(CAPABILITIES_DISK="false")


def test_the_capability_is_read_the_way_the_hypervisor_writes_it():
    """strtobool accepts False/no/off on the hypervisor side; so must this."""
    assert "storage" not in _parts(CAPABILITIES_DISK="False")


def test_the_default_keeps_the_storage_container():
    assert "storage" in _parts()


def test_a_worker_count_of_zero_keeps_the_container_it_only_empties_it():
    """The capability owns whether the container exists; the count, its threads."""
    assert "storage" in _parts(REDIS_WORKERS="0")


def test_the_storage_flavour_refuses_to_build_without_the_capability():
    """A flavour that exists to serve storage cannot be told to serve none."""
    done = _run(flavour="storage", CAPABILITIES_DISK="false")
    assert done.returncode != 0
    assert "CAPABILITIES_DISK" in done.stdout + done.stderr


def test_dropping_the_storage_part_leaves_its_namesakes_alone():
    """``remove_part`` matches whole words: no part whose name merely starts the
    same way may disappear with it."""
    left = _parts(
        parts="network storage storage-vdo-stats stats", CAPABILITIES_DISK="false"
    )
    assert "storage" not in left
    assert "storage-vdo-stats" in left


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
