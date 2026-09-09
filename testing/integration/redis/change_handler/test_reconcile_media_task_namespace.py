# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pass 4 must read a media's task from the MEDIA namespace.

The per-owner task index is keyed ``<kind>:<owner_id>:tasks``, and the two
kinds are disjoint by construction. ``Media.create_task`` writes under
``media``; ``Storage.create_task`` under ``storage``.

Pass 4 reuses ``_task_alive``, which was written for storage rows and defaulted
to the storage namespace. Handed a media it therefore asked
``storage:<media_id>:tasks`` — a key nothing ever writes. The lookup came back
empty, which at that point in ``_task_alive`` is indistinguishable from "the
task is dead", so the pass concluded the media was abandoned and re-issued its
delete over a download or a delete that was still running.

That is silent and destructive in the same breath: the running task keeps
writing the file while a second delete is enqueued behind it, and the row is
settled from under both. It also cannot be caught by asserting on
``media.task``, because the row pointer is exactly what the index replaced —
so these tests assert through the index, on a real Redis db.
"""

import pytest
from isardvdi_change_handler.streams import reconcile
from isardvdi_common.lib.task_index import MEDIA, STORAGE, index_key


class _Row:
    """A media/storage row as the pass reads it.

    ``delete_file`` is what Pass 4 calls to settle a row, and it records the
    call: without it ``_finalize_stuck_media`` raises, the pass swallows the
    error and returns 0, and an end-to-end assertion of "the pass did nothing"
    would hold whether or not the guard works.
    """

    def __init__(self, row_id, status="maintenance"):
        self.id = row_id
        self.status = status
        self.converted_from = None
        self.deletes = []

    def delete_file(self):
        self.deletes.append(self.id)
        return "reissued-task"


def _index(connection, kind, owner_id, task_id, score=1.0):
    """Index ``task_id`` under ``owner_id``, with the job it names.

    ``current_task_id`` answers the newest member whose job still EXISTS, so
    the rq job hash has to be there too — a bare ZSET member reads as dead and
    every assertion below would pass for the wrong reason.
    """
    connection.hset(f"rq:job:{task_id}", "status", "started")
    connection.zadd(index_key(kind, owner_id), {task_id: score})


@pytest.fixture
def alive_task(monkeypatch):
    """Every task id this module indexes reads as live, pending work.

    The point under test is *which key gets read*, not how a task settles, so
    the task itself is pinned live: a false negative can then only come from
    looking in the wrong namespace.
    """
    monkeypatch.setattr(reconcile.Task, "exists", staticmethod(lambda task_id: True))
    monkeypatch.setattr(reconcile.Task, "__init__", lambda self, task_id: None)
    monkeypatch.setattr(
        reconcile.Task, "chain_pending", property(lambda self: True), raising=False
    )
    monkeypatch.setattr(reconcile, "_metadata_finalize_orphaned", lambda *a, **k: False)


def test_a_media_task_is_found_in_the_media_namespace(
    task_on_scratch_redis, alive_task
):
    _index(task_on_scratch_redis, MEDIA, "m-1", "task-1")

    assert reconcile._task_alive(_Row("m-1"), kind=MEDIA) is True


def test_the_storage_namespace_does_not_answer_for_a_media(
    task_on_scratch_redis, alive_task
):
    """The regression, stated directly: same id, wrong namespace, no answer.

    Reading the storage namespace for a media that has a live task in the
    media namespace returns "dead" — which is what made Pass 4 act.
    """
    _index(task_on_scratch_redis, MEDIA, "m-1", "task-1")

    assert reconcile._task_alive(_Row("m-1"), kind=STORAGE) is False


def test_a_storage_row_still_defaults_to_the_storage_namespace(
    task_on_scratch_redis, alive_task
):
    """Adding the parameter must not move where storage rows are looked up:
    passes 2 and 3 pass no kind at all."""
    _index(task_on_scratch_redis, STORAGE, "s-1", "task-2")

    assert reconcile._task_alive(_Row("s-1")) is True


def test_the_namespaces_do_not_leak_into_each_other(task_on_scratch_redis, alive_task):
    """Both kinds indexed for the same id: each must read only its own."""
    _index(task_on_scratch_redis, MEDIA, "same-id", "task-media")
    _index(task_on_scratch_redis, STORAGE, "same-id", "task-storage")

    assert index_key(MEDIA, "same-id") != index_key(STORAGE, "same-id")
    assert reconcile._task_alive(_Row("same-id"), kind=MEDIA) is True
    assert reconcile._task_alive(_Row("same-id")) is True


def _pass4_over(monkeypatch, media):
    monkeypatch.setattr(
        reconcile.Media,
        "get_index",
        classmethod(
            lambda cls, values, index: [media] if media.status in values else []
        ),
    )


@pytest.mark.asyncio
async def test_pass4_leaves_a_media_whose_media_indexed_task_is_alive(
    monkeypatch, task_on_scratch_redis, alive_task
):
    """End to end through the pass, which is where the damage happened.

    ``_reconcile_stuck_media`` is what re-issues the delete, so the guard has
    to hold at that level and not only in the helper.
    """
    media = _Row("m-2")
    _pass4_over(monkeypatch, media)
    _index(task_on_scratch_redis, MEDIA, "m-2", "task-3")

    assert await reconcile._reconcile_stuck_media(None) == 0
    assert media.deletes == [], "the pass deleted over a task that is still running"


@pytest.mark.asyncio
async def test_a_pathless_media_with_a_live_task_is_not_settled_deleted(
    monkeypatch, task_on_scratch_redis, alive_task
):
    """Where the namespace bug actually costs state, not just log noise.

    ``Media.delete_file`` carries its own pending-task precondition, and it
    reads the MEDIA namespace correctly — so for a media that HAS a path, a
    wrongly-selected row is refused there and the damage is a recurring
    exception rather than a lost row.

    A media with no ``path_downloaded`` never reaches that precondition:
    delete_file settles it ``deleted`` and returns first, because a row with no
    path is taken to have never had a file. A download whose path is not
    written yet is exactly that shape, so a wrongly-selected one is settled
    ``deleted`` underneath its running task with nothing to stop it. The guard
    in this pass is the only thing standing there.
    """
    media = _Row("m-4")
    media.path_downloaded = ""

    def settle_like_delete_file():
        media.status = "deleted"
        return None

    media.delete_file = settle_like_delete_file
    _pass4_over(monkeypatch, media)
    _index(task_on_scratch_redis, MEDIA, "m-4", "task-4")

    assert await reconcile._reconcile_stuck_media(None) == 0
    assert media.status == "maintenance", (
        "a path-less media with a live task was settled deleted; delete_file "
        "settles before it checks, so this pass is the only guard"
    )


@pytest.mark.asyncio
async def test_pass4_still_settles_a_media_with_no_live_task(
    monkeypatch, task_on_scratch_redis
):
    """The guard on the guard.

    Without this, the test above passes for any reason the pass declines to
    act — including a harness that cannot act at all — and the protection it
    claims to prove would be unfalsifiable. Same row, same pass, nothing in
    the index: the delete must be re-issued.
    """
    media = _Row("m-3")
    _pass4_over(monkeypatch, media)

    assert await reconcile._reconcile_stuck_media(None) == 1
    assert media.deletes == ["m-3"]
