# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Storage.create_task`` really threads the disk id into the job it builds.

Both halves of the reverse mapping were tested in isolation and the producer
joining them was not: the model tests drive ``Task(...)`` with an explicit
``storage_id=`` kwarg, and every other test of ``create_task`` patches the
method out at class level, so its body never ran. Deleting the one line that
sets the default left the whole suite green while every storage task in
production got ``meta["storage_id"] = None``.

This executes the real body and asserts on what reaches ``Task``.
"""

from unittest.mock import MagicMock, patch

from isardvdi_common.models.storage import Storage


def _disk():
    """A bare ``Storage`` carrying only what ``create_task`` reads, so the real
    method body runs without a database. Fields go straight into ``__dict__``:
    ``Storage`` resolves unknown attributes through ``__getattr__`` (a query)
    and writes them through ``__setattr__`` (an update); ``category`` is a real
    property, so it is replaced on the class in :func:`_run` instead."""
    disk = Storage.__new__(Storage)
    disk.__dict__.update({"id": "disk-1", "task": None})
    return disk


def _run(storage, **extra):
    """Run the real ``create_task`` and return the kwargs handed to ``Task``."""
    seen = {}

    def _task(*args, **kwargs):
        seen.update(kwargs)
        built = MagicMock()
        built.id = "job-1"
        return built

    with patch("isardvdi_common.models.storage.Task", side_effect=_task) as Task, patch(
        "isardvdi_common.models.storage.queue_coverage.enforce_shed"
    ), patch.object(Storage, "category", "cat-1"), patch.object(
        Storage, "__setattr__", lambda self, name, value: None
    ):
        Task.exists.return_value = False
        Task._redis = MagicMock()
        storage.create_task(
            user_id="u-1",
            queue="storage.pool.default",
            task="convert",
            **extra,
        )
    return seen


class TestTheDiskIdReachesTheJob:
    def test_create_task_names_its_own_disk(self):
        assert _run(_disk())["storage_id"] == "disk-1"

    def test_an_explicit_owner_is_not_overwritten(self):
        """``setdefault``, so a caller that knows better still wins."""
        assert (
            _run(_disk(), storage_id="disk-override")["storage_id"] == "disk-override"
        )

    def test_the_category_is_threaded_too(self):
        """Guards the neighbouring setdefault, which has the same shape and the
        same failure mode."""
        assert _run(_disk())["category_id"] == "cat-1"
