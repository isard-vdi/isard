# SPDX-License-Identifier: AGPL-3.0-or-later

"""Template-from-desktop asks BOTH pools before it labels anything.

The chain roots on the destination pool (the ``move`` that writes the new
template file) and hands a later step to the source pool (the backing-chain
re-read of the desktop's rewritten overlay). So "can this work be placed?" has
two answers, and the producer needs both of them BEFORE it touches state.

The state it touches first is ``template_storage.set_maintenance("create")``.
That label is what makes the row unavailable to every other caller, and nothing
clears it but the chain that set it. Enqueue a chain onto a lane no worker
serves and the label stays forever: the template row is locked, the template
domain sits in ``CreatingTemplate``, and the only way out is an operator
editing the database by hand. Refusing one lane and not the other is the same
outcome with a smaller window -- the destination answers "fine", the label goes
on, and the source step is the one nothing will ever run.

These tests drive the real method body with the two pools answering
independently, and assert on the two things a user and an operator can see: the
typed 429 the API renders, and the maintenance label that was never applied.

Harness notes
-------------
``Storage`` is patched *in the module's own namespace* rather than through
``Storage.__new__``: the method reads the global twice (``Storage.exists`` and
``Storage(template_storage_id)``) and nowhere else, so rebinding the name routes
the template row to a stand-in while ``self`` stays a real ``Storage`` running
the real body. That also avoids the process-wide ``tp_new`` damage a
``__new__`` patch leaves behind for every later test in the interpreter.

The stand-in rows are plain objects, not ``MagicMock``s: a mock auto-creates any
attribute on first read, so a field the code never writes would read back as
written and every assertion here would pass vacuously.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from isardvdi_common.models.storage import Error, Storage

DESKTOP_ID = "desktop-1"
TEMPLATE_ID = "template-1"
TEMPLATE_STORAGE_ID = "new-template-storage-99"
SRC_POOL = "src-pool"
DST_POOL = "dst-pool"
ROOT_TASK_ID = "root-task-1"


class _ParkedRow:
    """The new template storage row the chain parks and labels."""

    def __init__(self, storage_id, pool_id):
        self.id = storage_id
        self.pool = MagicMock(id=pool_id)
        self.path = f"/isard/templates/{storage_id}.qcow2"
        self.type = "qcow2"
        self.set_maintenance = MagicMock()


class _DomainRow:
    """A domain row that only carries what somebody actually wrote to it."""

    def __init__(self, domain_id):
        self.id = domain_id


def _bare_desktop_storage():
    """The desktop's existing ``Storage``, without a database.

    ``RethinkCustomBase.__setattr__`` writes through to RethinkDB on every
    assignment, so the fields the body reads go in via ``object.__setattr__``.
    ``path`` is a property over ``directory_path``/``id``/``type``; ``pool`` and
    ``category`` are properties patched on the class by :func:`_chain`.
    """
    storage = Storage.__new__(Storage)
    object.__setattr__(storage, "id", "src-desktop-storage")
    object.__setattr__(storage, "directory_path", "/isard/groups")
    object.__setattr__(storage, "type", "qcow2")
    object.__setattr__(storage, "user_id", "u1")
    object.__setattr__(storage, "parent", None)
    object.__setattr__(storage, "task", None)
    return storage


def _lane_refuser(unserved_pool):
    """A lane check that refuses exactly one pool, with the real typed 429.

    The pool is read out of the queue name's infra segment
    (``storage.<pool>....``) rather than matched whole, so the tier and any
    per-category segment the producer resolves are free to change without
    turning this into a test of queue-name spelling.
    """

    def _check(conn, queue):
        parts = str(queue).split(".")
        if len(parts) < 2 or parts[1] != unserved_pool:
            return None
        raise Error(
            "too_many_requests",
            f"Storage lane {parts[1]} is temporarily unable to accept work; "
            "please retry shortly",
            description_code="storage_no_consumer_retry_later",
        )

    return _check


@contextmanager
def _chain(unserved_pool=None):
    """Run the real template chain with the two pools answering separately.

    ``unserved_pool`` is the pool id whose lane has nobody to drain it; ``None``
    means both are healthy. Yields the spies plus ``go()``, so a caller can
    still interrogate them after a refusal has escaped.
    """
    desktop = _bare_desktop_storage()
    parked = _ParkedRow(TEMPLATE_STORAGE_ID, DST_POOL)
    domains = {}

    domain_cls = MagicMock()
    domain_cls.exists.return_value = True
    domain_cls.side_effect = lambda domain_id: domains.setdefault(
        domain_id, _DomainRow(domain_id)
    )

    check_shed = MagicMock(
        side_effect=_lane_refuser(unserved_pool) if unserved_pool else None
    )

    with (
        patch("isardvdi_common.models.storage.Storage") as storage_global,
        patch("isardvdi_common.models.storage.Task") as task_cls,
        patch("isardvdi_common.models.storage.queue_coverage.check_shed", check_shed),
        patch("isardvdi_common.models.domain.Domain", domain_cls),
        patch.object(Storage, "create_task", return_value=ROOT_TASK_ID) as create_task,
        patch.object(Storage, "category", "cat-1"),
        patch.object(
            Storage,
            "pool",
            new_callable=PropertyMock,
            return_value=MagicMock(id=SRC_POOL),
        ),
    ):
        storage_global.exists.return_value = True
        storage_global.return_value = parked
        task_cls._redis = MagicMock()

        def go():
            return desktop.enqueue_template_creation_chain_from_desktop(
                desktop_id=DESKTOP_ID,
                template_id=TEMPLATE_ID,
                template_storage_id=TEMPLATE_STORAGE_ID,
            )

        yield SimpleNamespace(
            go=go,
            desktop=desktop,
            parked=parked,
            domains=domains,
            create_task=create_task,
            check_shed=check_shed,
        )


def test_source_pool_without_a_worker_refuses_before_the_maintenance_label():
    """A template whose SOURCE pool has no worker is labelled and abandoned.

    The chain roots on the destination, so a producer that only asks the
    destination admits this one: ``set_maintenance("create")`` goes on the new
    template row, the chain enqueues, the destination-side ``move`` may even
    succeed, and the source-side step waits on a lane nothing serves. The row
    stays in maintenance and the template domain stays in ``CreatingTemplate``
    until somebody edits the database.
    """
    with _chain(unserved_pool=SRC_POOL) as run:
        with pytest.raises(Exception) as excinfo:
            run.go()

        assert getattr(excinfo.value, "status_code", None) == 429
        assert (
            getattr(excinfo.value, "error", {}).get("description_code")
            == "storage_no_consumer_retry_later"
        )
        run.parked.set_maintenance.assert_not_called()
        run.create_task.assert_not_called()


def test_the_refused_template_domain_says_why_in_words():
    """Refusing without a reason leaves an operator a stuck row and a traceback.

    The 429 is only ever seen by the caller that got refused. What survives is
    the template domain: it must come out ``Failed`` carrying a sentence that
    names the pool and says the pool has no online storage worker, or the only
    account of the outage is a stack trace in a log nobody is reading.
    """
    with _chain(unserved_pool=SRC_POOL) as run:
        with pytest.raises(Exception):
            run.go()

        row = run.domains.get(TEMPLATE_ID)
        assert row is not None, "the template domain was never marked"
        assert getattr(row, "status", None) == "Failed"
        detail = getattr(row, "detail", None)
        assert detail is not None, "the template domain carries no reason"
        assert "has no online storage worker" in detail
        assert SRC_POOL in detail


def test_two_healthy_pools_still_label_the_row_and_build_the_chain():
    """The gate must refuse an unservable lane and nothing else.

    A pre-flight that answers "no" too often is worse than none: template
    creation is a normal, frequent operation, and a gate that trips on a
    healthy fleet takes the feature away entirely. This is the half that says
    the ordinary path is untouched -- the label goes on, the root ``move`` is
    built on the destination pool, and no domain is marked Failed.
    """
    with _chain() as run:
        task_id = run.go()

    assert task_id == ROOT_TASK_ID
    run.parked.set_maintenance.assert_called_once_with("create")
    run.create_task.assert_called_once()
    assert run.create_task.call_args.kwargs["queue"] == f"storage.{DST_POOL}.template"
    assert run.create_task.call_args.kwargs["task"] == "move"
    assert run.domains == {}, "a healthy create must not fail any domain"


def test_destination_pool_without_a_worker_refuses_too():
    """The pool the chain roots on is not exempt from being asked.

    The destination is where the whole-disk copy lands. With no worker there
    the ``move`` never starts, so the template row would sit in maintenance
    with a 0-byte future and the desktop's disk untouched -- the same stranding
    as the source case, reached through the other pool.
    """
    with _chain(unserved_pool=DST_POOL) as run:
        with pytest.raises(Exception) as excinfo:
            run.go()

        assert getattr(excinfo.value, "status_code", None) == 429
        run.parked.set_maintenance.assert_not_called()
        run.create_task.assert_not_called()

        row = run.domains.get(TEMPLATE_ID)
        assert row is not None, "the template domain was never marked"
        detail = getattr(row, "detail", None)
        assert detail is not None, "the template domain carries no reason"
        assert DST_POOL in detail
