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
