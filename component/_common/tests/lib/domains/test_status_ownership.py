"""The five hand-maintained status collections must agree with the declaration.

Each lives inside one component and several name statuses a *different*
component owns. They are read here from their real source files by ``ast``, so
this fails when one of them drifts rather than when a desktop comes out in the
wrong state.

The existing guard, ``test_desktop_status_enum_coverage.py``, reads three of
these same files and checks the enum covers their **union**. It never looks at
the intersection, which is where two owners for one status hide.
"""

import ast
from pathlib import Path

import pytest
from isardvdi_common.lib.domains.status_ownership import (
    CONTESTED,
    ENGINE,
    PROMOTABLE_TERMINAL,
    STATUS_EXECUTOR,
    STORAGE_CHAIN,
    TERMINAL,
)

_REPO_ROOT = Path(__file__).resolve().parents[5]

_COLLECTIONS = {
    "TRANSITIONAL_STATUS": "engine/src/engine/config.py",
    "status_to_failed": "engine/src/engine/services/db/domains.py",
    "status_to_stopped": "engine/src/engine/services/db/domains.py",
    "status_to_delete": "engine/src/engine/services/db/domains.py",
    "STATUSES_ALREADY_ACCOUNTED_FOR": "engine/src/engine/controllers/broom.py",
    "STATUSES_IN_CREATION": "engine/src/engine/controllers/broom.py",
    "STATUSES_SKIPPED_WITHOUT_HYPERVISOR": "engine/src/engine/controllers/broom.py",
    "_DOMAIN_PRE_READY_STATUSES": (
        "component/change-handler/src/isardvdi_change_handler/task_results/storage.py"
    ),
    "_DOMAIN_LOCK_STATUSES": (
        "component/change-handler/src/isardvdi_change_handler/streams/reconcile.py"
    ),
}

# Written by the engine's own paths and never by a sweep, so no collection
# declares them; the broom's whitelist is the only place they are named.
_ENGINE_RUNTIME_ONLY = {"Started", "Paused", "ForceDeleting"}


def _literals(node):
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "frozenset":
        return _literals(node.args[0]) if node.args else []
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [
            element.value
            for element in node.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        ]
    return []


def _collection(symbol):
    path = _REPO_ROOT / _COLLECTIONS[symbol]
    assert (
        path.exists()
    ), f"{path} not found: the collection moved and the test must follow it"
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == symbol
            for target in node.targets
        ):
            return set(_literals(node.value))
    raise AssertionError(f"{symbol} not found in {_COLLECTIONS[symbol]}")


@pytest.mark.parametrize("symbol", sorted(_COLLECTIONS))
def test_every_status_in_a_collection_is_declared(symbol):
    """A status added to any of them has to be classified before it ships."""
    undeclared = sorted(
        _collection(symbol) - set(STATUS_EXECUTOR) - _ENGINE_RUNTIME_ONLY
    )

    assert not undeclared, (
        f"{symbol} names {undeclared}, absent from STATUS_EXECUTOR. Declare which "
        "component executes them before adding them to a collection."
    )


def test_only_the_known_statuses_have_two_owners():
    """The regression this exists for.

    ``status_to_failed`` is what the engine converges on its own; every status
    in ``_DOMAIN_PRE_READY_STATUSES`` is one the change-handler will promote to
    ``Stopped`` on any storage update. A status in both is a status whose end
    state depends on which tick arrives first.
    """
    contested = _collection("status_to_failed") & _collection(
        "_DOMAIN_PRE_READY_STATUSES"
    )

    assert contested == set(CONTESTED), (
        f"contested statuses are {sorted(contested)}, declared {sorted(CONTESTED)}. "
        "Add the status to CONTESTED with why it is contested, "
        "or take it out of one of the two collections."
    )


def test_the_change_handler_only_promotes_what_it_or_nobody_executes():
    """It settles storage-chain work; engine-executed statuses are not its to end."""
    engine_owned = {
        status
        for status in _collection("_DOMAIN_PRE_READY_STATUSES")
        if STATUS_EXECUTOR.get(status) == ENGINE
    }

    assert engine_owned == set(CONTESTED), (
        f"the promote set claims engine-executed {sorted(engine_owned)}; "
        f"declared contested: {sorted(CONTESTED)}"
    )


def test_the_reconciler_only_locks_what_the_storage_chain_executes():
    """Pass 3 re-observes disks, so every status it selects must be chain work."""
    not_chain = {
        status
        for status in _collection("_DOMAIN_LOCK_STATUSES")
        if STATUS_EXECUTOR.get(status) != STORAGE_CHAIN
    }

    assert not not_chain, f"_DOMAIN_LOCK_STATUSES selects non-chain {sorted(not_chain)}"


def test_every_contested_status_says_why():
    for status, reason in CONTESTED.items():
        assert status in STATUS_EXECUTOR, f"{status} is contested but undeclared"
        assert reason.strip(), f"{status} must say why its owner is contested"


def test_the_promote_set_does_not_undo_a_terminal_verdict():
    """A terminal status is another component's decision: the promotion must not undo it."""
    undone = {
        status
        for status in _collection("_DOMAIN_PRE_READY_STATUSES")
        if STATUS_EXECUTOR.get(status) == TERMINAL
    } - PROMOTABLE_TERMINAL

    assert not undone, (
        f"the promote set turns {sorted(undone)} into Stopped, erasing a terminal "
        "verdict and leaving the row carrying the reason it is not ready."
    )
