#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Every producer that hands work to a ``storage.`` lane consults the coverage gate.

A lane with no live worker accepts a job exactly as a healthy one does. Nothing
raises, nothing times out, no timer fires: the row says CreatingDisk or
``deleting`` or ``moved``, the job sits in redis, and the operator finds out
weeks later. ``queue_coverage`` is the only thing in the tree that can tell a
served lane from an abandoned one, so a producer that never asks it cannot know
it has just thrown the work away while reporting it placed. This walks the
modules that build a task on a queue that can name a ``storage.`` lane and
asserts each one really asks.

Why a source scan, and not one gate inside ``Task.__init__``
------------------------------------------------------------
``test_task_index_producers`` makes the opposite argument for the task index,
and there it is the right one: one write site means a new producer cannot
silently bypass the index, it only has to name its owners. The argument does
not transfer here, because an index write has no failure mode and a gate has
nothing but. Recording the owners of a task either happens or the enqueue fails
anyway; the gate exists in order to answer NO, and a constructor has no way to
say "declined" -- only to raise.

A raise at that seam is exactly what turns a silent stall into a crash loop for
the two producers that are not answering a user. The change-handler's stream
consumer wraps the construction of a dependent in ``except Exception``: an
exception there is logged as a traceback and the entry is treated as handled,
so a routine shed becomes a dropped dependent plus a page of noise on every
redelivery. The migration runner reads an exception mid-tree as a failure of
the move and would terminalize a migration over a worker restart. Both are
right to DECLINE -- to leave the work where something already re-drives it --
and neither can express that from inside a constructor. So the gate is
mandatory on every producer while the VERB is the caller's: refuse where
somebody is listening, decline where nobody is. The only cheap check that
"every producer" still means every producer is this one.

The scan is AST-based, so a comment does not survive parsing and a docstring is
a constant: a module that merely mentions the gate in prose fails here exactly
as one that never heard of it.
"""

import ast
import importlib.util
import os

import isardvdi_common

MODULE = "isardvdi_common.lib.queue_coverage"

# Producers inside isardvdi_common, keyed by their path under the package, with
# the one line that says why each is allowed to enqueue at all.
COMMON_PRODUCERS = {
    "models/storage.py": "enforce_shed on create_task",
    "models/media.py": "enforce_shed on create_task",
    "models/task.py": "check_no_consumer in retry",
    "helpers/recycle_bin.py": "asks per delete, defers the entry on a no",
    "lib/storage/migration_run.py": "asks per phase whether the lane drains",
}

# Producers in the change-handler component, keyed by their path under its
# package. It never goes through create_task, so it carries its own gate.
CHANGE_HANDLER_PRODUCERS = {
    "streams/task_results_consumer.py": "asks before building the knot child",
}

MIGRATION_RUN = "lib/storage/migration_run.py"
MIGRATION_GATE = "lane_is_drainable"
MIGRATION_ENQUEUE = "_enqueue"


def _first_existing(roots, relative):
    for root in roots:
        candidate = os.path.join(root, *relative.split("/"))
        if os.path.isfile(candidate):
            return candidate
    return None


def _common_roots():
    return list(isardvdi_common.__path__)


def _change_handler_roots():
    """The installed package if the workspace is synced, else the checkout.

    Both routes are tried because the common suite is run from
    ``component/_common/src`` with the whole monorepo on disk AND with the
    change-handler package installed in the venv; either one alone is enough.
    """
    roots = []
    try:
        spec = importlib.util.find_spec("isardvdi_change_handler")
    except Exception:
        spec = None
    if spec is not None and spec.submodule_search_locations:
        roots.extend(spec.submodule_search_locations)
    walked = os.path.abspath(__file__)
    for _ in range(8):
        walked = os.path.dirname(walked)
        roots.append(
            os.path.join(
                walked, "component", "change-handler", "src", "isardvdi_change_handler"
            )
        )
    return roots


def _parse(path):
    with open(path, encoding="utf-8") as source:
        return ast.parse(source.read(), filename=path)


def _gate_bindings(tree):
    """What this file binds the gate to: module aliases, and imported names."""
    aliases = set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if f"{node.module}.{alias.name}" == MODULE:
                    aliases.add(alias.asname or alias.name)
                elif node.module == MODULE:
                    names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == MODULE and alias.asname:
                    aliases.add(alias.asname)
    return aliases, names


def _consults_the_gate(path):
    """True only if the file actually reads something off the gate module."""
    tree = _parse(path)
    aliases, names = _gate_bindings(tree)
    if not aliases and not names:
        return False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        ):
            return True
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in names
        ):
            return True
    return False


def _methods(tree):
    """Every module-level and class-level function, as (name, node).

    Nested helpers are deliberately left out: a gate held by the enclosing
    function covers them, and counting them would report a false miss.
    """
    found = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append((node.name, node))
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found.append((f"{node.name}.{child.name}", child))
    return found


def _first_line(node, predicate):
    lines = [inner.lineno for inner in ast.walk(node) if predicate(inner)]
    return min(lines) if lines else None


def _calls_attribute(name):
    return lambda node: (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == name
    )


def _reads_attribute(name):
    return lambda node: isinstance(node, ast.Attribute) and node.attr == name


def test_every_storage_lane_producer_consults_the_coverage_gate():
    """A producer that never asks lands work on a lane nobody drains and leaves
    it looking placed: no exception, no timeout, and a row stuck mid-operation
    until a human goes looking for it."""
    unresolved = []
    silent = []
    for roots, producers in (
        (_common_roots(), COMMON_PRODUCERS),
        (_change_handler_roots(), CHANGE_HANDLER_PRODUCERS),
    ):
        for relative, why in sorted(producers.items()):
            path = _first_existing(roots, relative)
            if path is None:
                unresolved.append(relative)
            elif not _consults_the_gate(path):
                silent.append(f"{relative} ({why})")
    missing = (
        "could not find these producers on disk, so nothing was checked "
        "(incomplete checkout?):\n" + "\n".join(sorted(unresolved))
    )
    assert not unresolved, missing
    report = (
        f"enqueues onto a storage. lane without consulting {MODULE}:\n"
        + "\n".join(sorted(silent))
    )
    assert not silent, report


def test_every_migration_phase_that_enqueues_asks_the_lane_first():
    """A migration phase that enqueues without asking wedges the whole
    migration: the tree waits on a job nobody will ever run, so it never
    completes, reactivate never fires, and every desktop in the migration stays
    down with its autostart still suppressed."""
    path = _first_existing(_common_roots(), MIGRATION_RUN)
    assert path is not None, f"{MIGRATION_RUN} not found, nothing was checked"
    ungated = []
    for name, node in _methods(_parse(path)):
        enqueued = _first_line(node, _calls_attribute(MIGRATION_ENQUEUE))
        if enqueued is None:
            continue
        asked = _first_line(node, _reads_attribute(MIGRATION_GATE))
        if asked is None:
            ungated.append(f"{name} (line {enqueued}): never asks")
        elif asked > enqueued:
            ungated.append(f"{name} (line {enqueued}): asks only after enqueuing")
    report = (
        f"enqueues a migration phase without asking {MIGRATION_GATE} first:\n"
        + "\n".join(sorted(ungated))
    )
    assert not ungated, report
