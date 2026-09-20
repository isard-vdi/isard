#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Every ``queue_tiers.<name>`` referenced across isardvdi_common must exist.

``queue_tiers`` is imported as a *module* by producers all over the package, so
a reference to a name it does not define is invisible to the import machinery
and to flake8 — it only blows up as an ``AttributeError`` the first time that
line runs. That is exactly how ``queue_tiers.multitenancy_enabled()`` (a helper
from an earlier design that never landed) shipped inside
``RecycleBin.delete_storage``: every permanent delete raised, the entry was left
stranded in ``deleting`` and no disk space was ever reclaimed.

The scan is AST-based, so it costs nothing and needs no database.
"""

import ast
import os

import isardvdi_common
from isardvdi_common.lib import queue_tiers

MODULE = "isardvdi_common.lib.queue_tiers"


def _package_sources():
    for root in isardvdi_common.__path__:
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if filename.endswith(".py"):
                    yield os.path.join(dirpath, filename)


def _module_aliases(tree):
    """Names bound to the queue_tiers module in this file."""
    aliases = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if f"{node.module}.{alias.name}" == MODULE:
                    aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == MODULE and alias.asname:
                    aliases.add(alias.asname)
    return aliases


def test_no_reference_to_a_missing_queue_tiers_name():
    missing = []
    for path in _package_sources():
        with open(path, encoding="utf-8") as source:
            tree = ast.parse(source.read(), filename=path)
        aliases = _module_aliases(tree)
        if not aliases:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in aliases
                and not hasattr(queue_tiers, node.attr)
            ):
                missing.append(f"{path}:{node.lineno}: queue_tiers.{node.attr}")
    assert not missing, "queue_tiers has no such name:\n" + "\n".join(sorted(missing))


# ── #4251: the check/repair tasks are tiered by measured cost, not left to fall
#    on the default lane. ──────────────────────────────────────────────────────
def test_check_tier_routes_by_allocated_clusters():
    from isardvdi_common.lib.queue_tiers import (
        CHECK_INTERACTIVE_MAX_CLUSTERS,
        check_tier,
    )

    assert CHECK_INTERACTIVE_MAX_CLUSTERS == 1_100_000
    assert check_tier(0) == "interactive"
    assert check_tier(CHECK_INTERACTIVE_MAX_CLUSTERS - 1) == "interactive"
    assert check_tier(CHECK_INTERACTIVE_MAX_CLUSTERS) == "standard"
    # a producer may pass an env-tuned threshold
    assert check_tier(50, threshold=10) == "standard"


def test_repair_tier_routes_by_what():
    from isardvdi_common.lib.queue_tiers import repair_tier

    assert repair_tier("leaks") == "standard"
    assert repair_tier("all") == "maintenance"
