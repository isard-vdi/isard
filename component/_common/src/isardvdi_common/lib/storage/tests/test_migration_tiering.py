# SPDX-License-Identifier: AGPL-3.0-or-later

"""The migration's move must land on the tier the tier rules mandate.

queue_tiers hard-floors a whole-disk ``move`` to ``maintenance`` precisely
because it is a hours-long copy that has to be PSI-paced and counted against the
max-heavy concurrency cap. The migration runner builds its queue name itself
(it bypasses create_task), so nothing enforces that for it: a hardcoded
``.default`` tier would run every migration rsync ungoverned.
"""

import ast
import inspect

from isardvdi_common.lib import queue_tiers as qt
from isardvdi_common.lib.storage import migration_run as mr


def test_a_move_is_floored_to_a_heavy_tier():
    assert qt.normalize_tier("default", "move") == "maintenance"
    assert (
        qt.retier_queue("storage.src:dst.default", "move")
        == "storage.src:dst.maintenance"
    )


def test_the_runner_tiers_its_move_queue_through_the_tier_rules():
    """Source-level: _move_queue must not hand-build a tier. It runs on the
    worker with no create_task around it, so the only thing that can put the
    move on the governed tier is an explicit retier_queue call."""
    src = inspect.getsource(mr.MigrationRunner._move_queue)
    tree = ast.parse(src.lstrip())
    calls = [
        n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
    ]
    assert "retier_queue" in calls, f"_move_queue does not retier: {calls}"


def test_the_guard_checks_the_tier_the_runner_actually_uses():
    """If the guard checks one tier and the runner enqueues on another, the
    guard silently protects nothing."""
    from isardvdi_common.lib.storage.migration_run import DEFAULT_PRIORITY

    assert qt.normalize_tier(DEFAULT_PRIORITY, "move") == "maintenance"
