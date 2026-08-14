# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pass 4 leaves a media alone while its task is still running.

Liveness is declared the way the producer declares it — an entry in the MEDIA
namespace of the per-owner index — not by setting the row's retired ``task``
field. The two namespaces are disjoint, so a media indexed here and read as a
storage reads as dead; that is the whole point of the check, and exercising it
through the real key is why this lives here instead of beside the rest of the
pass-4 tests.

The row is a REAL ``Media``, not a stand-in with a stub ``delete_file``: an
earlier revision of this pass selected exactly the statuses ``delete_file``
refused, so every row it found raised ``precondition_required``, got swallowed
by the pass's own ``except Exception`` and healed nothing — while tests built
on a hand-written ``delete_file`` stayed green through all of it. Only
persistence and the queue are stubbed; every precondition runs for real.
"""

import pytest
from isardvdi_change_handler.streams import reconcile
from isardvdi_common.lib.task_index import MEDIA, index_key
from isardvdi_common.models.media import Media
from isardvdi_common.models.storage_pool import StoragePool
from isardvdi_common.models.task import Task

pytestmark = pytest.mark.contract


class _StuckMedia(Media):
    """A real ``Media`` whose row lives in memory.

    ``RethinkCustomBase`` writes through to RethinkDB on every assignment, so
    the persisted attributes are held in a dict instead. ``delete_file`` itself
    is inherited untouched.
    """

    def __init__(self, status, path_downloaded="/isard/media/m.iso", task=None):
        object.__setattr__(self, "_values", {})
        self._values.update(
            {
                "id": "m-1",
                "status": status,
                "path_downloaded": path_downloaded,
                "task": task,
            }
        )
        self.created_tasks = []

    def __getattr__(self, name):
        try:
            return object.__getattribute__(self, "_values")[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        if name in ("created_tasks", "create_task"):
            object.__setattr__(self, name, value)
        else:
            self._values[name] = value

    def create_task(self, **kwargs):
        self.created_tasks.append(kwargs)
        self._values["task"] = "task-1"


@pytest.fixture
def _media_queue(monkeypatch):
    """Stub only what reaches outside the process: the pool and the task."""
    pool = StoragePool.__new__(StoragePool)
    object.__setattr__(pool, "id", "pool-a")
    monkeypatch.setattr(
        StoragePool, "get_best_for_action", classmethod(lambda cls, *a, **k: pool)
    )
    monkeypatch.setattr(Task, "exists", staticmethod(lambda task_id: False))


def _index_returns(monkeypatch, rows):
    """Serve ``Media.get_index`` from ``rows`` keyed by status."""
    monkeypatch.setattr(
        reconcile.Media,
        "get_index",
        classmethod(lambda cls, values, index: [r for r in rows if r.status in values]),
    )


@pytest.mark.asyncio
async def test_pass4_leaves_media_whose_task_is_alive(
    monkeypatch, _media_queue, task_on_scratch_redis
):
    """Pass 1 and the consumer own it while the task is still running."""
    media = _StuckMedia("maintenance")
    _index_returns(monkeypatch, [media])
    task_on_scratch_redis.hset("rq:job:task-9", "status", "started")
    task_on_scratch_redis.zadd(index_key(MEDIA, media.id), {"task-9": 1.0})
    # ``_media_queue`` pins ``exists`` False for the passes that want a dead
    # task; this one wants a live one, so say so after it.
    monkeypatch.setattr(Task, "exists", staticmethod(lambda task_id: True))
    monkeypatch.setattr(Task, "__init__", lambda self, task_id: None)
    monkeypatch.setattr(Task, "chain_pending", property(lambda self: True))
    monkeypatch.setattr(reconcile, "_metadata_finalize_orphaned", lambda *a, **k: False)

    assert await reconcile._reconcile_stuck_media(None) == 0
    assert media.created_tasks == []
    assert media.status == "maintenance"
