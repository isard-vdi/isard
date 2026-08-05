#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression: ``Task.to_dict`` must not crash on instance-only attributes.

``__init__`` sets instance-only attributes (``_enqueued`` / ``_queue_name``)
that appear in ``dir(self)`` but are NOT class attributes. The property-filter
comprehension used a bare ``getattr(self.__class__, name)`` which raised
``AttributeError`` for those, breaking every ``to_dict`` caller — ``get_task``,
the admin task listing, and ``emit_task_feedback`` (whose try/except swallowed
the crash, so NO ``task`` SocketIO events were ever delivered). The fix passes a
default: ``getattr(self.__class__, name, None)``.
"""

from unittest.mock import MagicMock, patch

from isardvdi_common.models.task import Task


def _new_task(**extra):
    """Real ``Task.__init__`` (new-task path) with Job/Queue mocked so no redis
    is touched; the mock job satisfies the attributes ``to_dict`` reads."""
    with patch("isardvdi_common.models.task.Job") as Job, patch(
        "isardvdi_common.models.task.Queue"
    ) as Queue:
        job = MagicMock(name="root_job")
        job.id = "root-1"
        job.meta = {}
        job.args = []
        job.get_position.return_value = None
        Job.create.return_value = job
        queue_obj = MagicMock(name="queue")
        queue_obj.enqueue_job.return_value = job
        Queue.return_value = queue_obj
        return Task(task="find", queue="storage.pool.default", **extra)


def test_to_dict_does_not_crash_on_instance_only_attrs():
    task = _new_task()
    # the instance-only attribute is present on the instance...
    assert hasattr(task, "_enqueued")
    # ...but to_dict must not raise, and must not leak instance-only attrs.
    data = task.to_dict()
    assert isinstance(data, dict)
    assert "_enqueued" not in data
    assert "_queue_name" not in data
    # a genuine property is still serialised
    assert "id" in data


def test_to_dict_does_not_walk_the_chain():
    """``chain_pending`` is a full closure walk with a cache-bypassing status
    read per member, and ``to_dict`` recurses into dependents — so serialising
    it costs a walk per node, on every listing, every task GET and every
    progress tick through ``emit_task_feedback``. ``storage_id`` is off the
    output for exactly this reason.

    Asserting on the emitted keys rather than on the exclusion list: a test
    that restates the list passes whatever the list says.
    """
    task = _new_task()

    assert "chain_pending" not in task.to_dict()


def test_every_task_property_has_a_recorded_decision():
    """Safe by default, and no property may sit undecided.

    A denylist lets a new property join every listing, every task GET and every
    SocketIO emit by simply existing — which has now happened twice
    (``storage_id``, then ``chain_pending``). The output is a safelist instead,
    so this test does not ask "is the denylist right?" but "does the author of
    every property on this class have an opinion recorded about it?".

    It reads the real class, so adding a property and running the suite is what
    surfaces the question — you cannot satisfy it by editing a copy of a list
    inside the test.
    """
    from isardvdi_common.models.task import (
        _TO_DICT_OMITTED_PROPERTIES,
        _TO_DICT_PROPERTIES,
    )

    actual = {
        name for name in dir(Task) if isinstance(getattr(Task, name, None), property)
    }
    decided = set(_TO_DICT_PROPERTIES) | set(_TO_DICT_OMITTED_PROPERTIES)

    undecided = actual - decided
    assert not undecided, (
        f"new Task propert{'y' if len(undecided) == 1 else 'ies'} "
        f"{sorted(undecided)} with no recorded decision. Add the name to "
        "_TO_DICT_PROPERTIES to serialise it (and check what it costs: to_dict "
        "recurses into dependents, so anything walking the chain is O(N^2) and "
        "anything returning a datetime breaks the SocketIO emitter), or to "
        "_TO_DICT_OMITTED_PROPERTIES to keep it off the wire."
    )

    stale = decided - actual
    assert not stale, (
        f"{sorted(stale)} listed but no longer a property on Task; "
        "the lists have drifted from the class"
    )


def test_to_dict_emits_exactly_the_safelist():
    """The safelist is the output contract, not a filter applied to whatever
    ``dir()`` happens to return."""
    from isardvdi_common.models.task import _TO_DICT_PROPERTIES

    data = _new_task().to_dict()

    # args / dependencies / dependents are built explicitly by to_dict itself.
    assert set(data) == set(_TO_DICT_PROPERTIES) | {
        "args",
        "dependencies",
        "dependents",
    }
