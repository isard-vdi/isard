#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A hypervisor that runs no storage worker must not declare disk operations.

``cap_disk`` is what the node registers as ``capabilities.disk_operations``, and
every reader of that field takes it as a promise to serve the node's storage
pools. ``REDIS_WORKERS=0`` stops the worker fleet as surely as the capability
does, so the promise has to account for both.

``setup`` imports the whole registration stack and loads modules from container
paths, so it is not importable here. The two functions are lifted out of the
shipped source and executed as they are written.
"""

import ast
import os
from pathlib import Path

import pytest

SETUP = Path(__file__).resolve().parent / "setup.py"
WANTED = ("strtobool", "_cap_disk")


def _cap_disk_from_source():
    tree = ast.parse(SETUP.read_text(encoding="utf-8"))
    wanted = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in WANTED
    ]
    assert sorted(node.name for node in wanted) == sorted(WANTED)
    namespace = {"os": os}
    exec(
        compile(ast.Module(body=wanted, type_ignores=[]), str(SETUP), "exec"), namespace
    )
    return namespace["_cap_disk"]


@pytest.fixture
def cap_disk(monkeypatch):
    for name in ("CAPABILITIES_DISK", "REDIS_WORKERS"):
        monkeypatch.delenv(name, raising=False)
    function = _cap_disk_from_source()

    def run(**env):
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return function()

    return run


def test_a_node_with_workers_and_the_capability_declares_disk_operations(cap_disk):
    assert cap_disk(CAPABILITIES_DISK="true", REDIS_WORKERS="10") is True


def test_the_defaults_are_preserved(cap_disk):
    """Neither variable set is what most installs have, and it must not change."""
    assert cap_disk() is True


def test_a_node_without_workers_declares_none(cap_disk):
    assert cap_disk(REDIS_WORKERS="0") is False


def test_the_capability_alone_still_decides(cap_disk):
    assert cap_disk(CAPABILITIES_DISK="false", REDIS_WORKERS="10") is False


def test_the_capability_is_read_the_way_the_cfg_may_spell_it(cap_disk):
    """strtobool is what reads it, so False/no/off must all count."""
    assert cap_disk(CAPABILITIES_DISK="False") is False
    assert cap_disk(CAPABILITIES_DISK="no") is False
    assert cap_disk(CAPABILITIES_DISK="off") is False


def test_a_worker_count_that_is_not_a_number_keeps_the_previous_answer(cap_disk):
    """A typo must not silently retire a node from disk operations."""
    assert cap_disk(REDIS_WORKERS="two") is True
