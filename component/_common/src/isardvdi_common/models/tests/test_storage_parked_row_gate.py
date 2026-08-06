# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Storage.create_task``'s blocking gate on a row parked by another row.

Template creation parks the NEW template storage row while the producing
task is stamped on the DESKTOP's row. The parked row therefore has no
``task`` of its own and names its parker through ``parked_by`` instead —
stamping the task id on it would put two rows on the ``task`` secondary
index for one task.

So the gate that refuses a second operation while a chain is in flight has
to resolve that back-reference: without it the parked row is the one row in
the system that accepts a concurrent operation on a disk a running chain is
about to overwrite, while the origin row it was copied from correctly
answers 428.
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models.storage import Storage


def _bare_storage(*, id="parked-row", task=None, parked_by=None):
    """A Storage that reads its own fields without touching RethinkDB."""
    s = Storage.__new__(Storage)
    object.__setattr__(s, "id", id)
    object.__setattr__(s, "user_id", "u1")
    object.__setattr__(s, "task", task)
    if parked_by is not None:
        object.__setattr__(s, "parked_by", parked_by)
    return s


def _parker(*, id="desktop-row", task="chain-task"):
    """The row that parked ours. A ``MagicMock`` rather than a real Storage:
    returning a Storage instance from ``__new__`` would still run ``__init__``,
    which reads the row from RethinkDB."""
    row = MagicMock()
    row.id = id
    row.task = task
    return row


def _run_create_task(storage, parker=None, parker_task_pending=True):
    """Call ``create_task`` with the queue/tiering machinery stubbed out.

    ``Storage(parked_by)`` is routed to ``parker`` so the gate resolves the
    back-reference without a DB hit. Returns the ``Task`` class mock.
    """
    real_new = Storage.__new__

    def fake_new(cls, *args, **kwargs):
        if parker is not None and args and args[0] == parker.id:
            return parker
        return real_new(cls)

    task_cls = MagicMock()
    task_cls.exists.return_value = True
    task_cls.return_value = MagicMock(id="new-task", pending=parker_task_pending)
    with (
        patch("isardvdi_common.models.storage.Task", task_cls),
        patch("isardvdi_common.models.storage.queue_coverage.enforce_shed"),
        patch("isardvdi_common.models.storage.Storage.__new__", side_effect=fake_new),
        patch.object(Storage, "category", new_callable=PropertyMock, return_value="c1"),
        patch.object(Storage, "__setattr__", lambda self, name, value: None),
    ):
        storage.create_task(user_id="u1", queue="storage.p.standard", task="resize")
    return task_cls


@pytest.fixture(autouse=True)
def _repair_storage_new_slot():
    """See ``test_storage_chain_definitions``: patching ``Storage.__new__``
    leaves the class unable to construct instances once mock restores it."""
    yield
    if "__new__" not in Storage.__dict__:
        Storage.__new__ = staticmethod(lambda cls, *args, **kwargs: object.__new__(cls))


def test_parked_row_refuses_a_second_operation_while_its_parker_runs():
    """The 428 the origin row already answers must also come from the row
    its chain parked — the chain is about to write that very disk."""
    parker = _parker()
    parked = _bare_storage(id="template-row", parked_by="desktop-row")

    with pytest.raises(Error) as raised:
        _run_create_task(parked, parker=parker, parker_task_pending=True)

    assert raised.value.error["description_code"] == "storage_pending_task"
    assert "chain-task" in raised.value.error["description"]


def test_parked_row_accepts_work_once_its_parker_settles():
    """Once the parking chain settles the row is operable again — the gate
    resolves the parker's task, it does not refuse on the marker alone."""
    parker = _parker()
    parked = _bare_storage(id="template-row", parked_by="desktop-row")

    task_cls = _run_create_task(parked, parker=parker, parker_task_pending=False)

    assert task_cls.call_args.kwargs["task"] == "resize"


def test_unparked_row_is_unaffected():
    """A row with neither a task nor a parker enqueues as before."""
    plain = _bare_storage(id="plain-row")

    task_cls = _run_create_task(plain)

    assert task_cls.call_args.kwargs["task"] == "resize"
