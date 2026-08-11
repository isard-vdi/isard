# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the storage/task-chain self-heal reconcile passes.

The reconcile recovers chains the consumer could not finish: a core handler
that raised leaves a storage-queue/core dependent stuck DEFERRED forever, the
storage row stuck ``maintenance`` and the domain stuck ``Downloading`` — and
``Task.pending`` then blocks every later op on that storage with a 428. These
tests pin the two idempotent passes and the safety gates (grace window,
never finalize a storage whose task is still alive).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from rq.exceptions import InvalidJobOperation, NoSuchJobError
from rq.job import JobStatus


def _dep(status=JobStatus.FINISHED, ended_secs_ago=600):
    """A dependency Task double: a job_status + a job.ended_at."""
    ended = None
    if ended_secs_ago is not None:
        ended = datetime.now(timezone.utc) - timedelta(seconds=ended_secs_ago)
    return SimpleNamespace(job_status=status, job=SimpleNamespace(ended_at=ended))


def _task(
    task_id="t1",
    *,
    task_name="storage_update",
    queue="core",
    dependencies=None,
    dependents=None,
    user_id="u1",
):
    job = MagicMock(name=f"job-{task_id}")
    return SimpleNamespace(
        id=task_id,
        task=task_name,
        queue=queue,
        user_id=user_id,
        dependencies=dependencies if dependencies is not None else [_dep()],
        dependents=dependents or [],
        job=job,
        cancel=MagicMock(name=f"cancel-{task_id}"),
    )


# ---------------------------------------------------------------------------
# _deps_terminal_and_aged — the orphan gate
# ---------------------------------------------------------------------------


def _gone_dep(exc=None):
    """A dependency whose RQ job data has been evicted: reading ``job_status``
    raises, exactly as observed in production ("reconcile: orphan heal failed
    ... rq.exceptions.InvalidJobOperation: Failed to retrieve status for job").
    RQ evicts a finished/failed job's hash after its result TTL, so a
    dependency we can no longer read is necessarily terminal and long settled.
    """
    if exc is None:
        exc = InvalidJobOperation("Failed to retrieve status for job: gone")
    dep = MagicMock(name="gone-dep")
    type(dep).job_status = PropertyMock(side_effect=exc)
    return dep


def test_orphan_gate_true_when_all_deps_terminal_and_aged():
    from isardvdi_change_handler.streams import reconcile

    now = datetime.now(timezone.utc)
    task = _task(dependencies=[_dep(JobStatus.FINISHED, 600)])
    assert reconcile._deps_terminal_and_aged(task, now, grace_s=120) is True


def test_orphan_gate_false_when_a_dep_not_terminal():
    from isardvdi_change_handler.streams import reconcile

    now = datetime.now(timezone.utc)
    task = _task(dependencies=[_dep(JobStatus.STARTED, 600)])
    assert reconcile._deps_terminal_and_aged(task, now, grace_s=120) is False


def test_orphan_gate_false_within_grace_window():
    from isardvdi_change_handler.streams import reconcile

    now = datetime.now(timezone.utc)
    task = _task(dependencies=[_dep(JobStatus.FINISHED, 5)])  # finished 5s ago
    assert reconcile._deps_terminal_and_aged(task, now, grace_s=120) is False


def test_orphan_gate_false_when_no_dependencies():
    from isardvdi_change_handler.streams import reconcile

    now = datetime.now(timezone.utc)
    task = _task(dependencies=[])
    assert reconcile._deps_terminal_and_aged(task, now, grace_s=120) is False


def test_orphan_gate_false_when_ended_at_missing():
    from isardvdi_change_handler.streams import reconcile

    now = datetime.now(timezone.utc)
    task = _task(dependencies=[_dep(JobStatus.FINISHED, None)])
    assert reconcile._deps_terminal_and_aged(task, now, grace_s=120) is False


def test_orphan_gate_handles_naive_ended_at():
    from isardvdi_change_handler.streams import reconcile

    now = datetime.now(timezone.utc)
    naive_old = (datetime.now(timezone.utc) - timedelta(seconds=600)).replace(
        tzinfo=None
    )
    dep = SimpleNamespace(
        job_status=JobStatus.FINISHED,
        job=SimpleNamespace(ended_at=naive_old),
    )
    task = _task(dependencies=[dep])
    assert reconcile._deps_terminal_and_aged(task, now, grace_s=120) is True


# ---------------------------------------------------------------------------
# Pass 1 — orphaned DEFERRED jobs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pass1_core_orphan_replays_dispatch_and_deletes():
    """A core-queue orphan re-runs the handler, marks FINISHED, releases its
    storage dependents and deletes the dead core job."""
    from isardvdi_change_handler.streams import reconcile

    orphan = _task("core1", queue="core", task_name="storage_update")
    with (
        patch.object(reconcile.Task, "get_by_status", return_value=[orphan]),
        patch.object(reconcile, "_walk_core_dependents", return_value=[]),
        patch.object(
            reconcile, "_run_handler", new=AsyncMock(return_value=True)
        ) as run_h,
        patch.object(reconcile, "_set_job_status", new=AsyncMock()) as set_st,
        patch.object(reconcile, "_release_storage_dependents", new=AsyncMock()) as rel,
    ):
        healed = await reconcile._reconcile_orphan_deferred(AsyncMock())

    assert healed == 1
    run_h.assert_awaited()
    set_st.assert_awaited_with(orphan, JobStatus.FINISHED)
    rel.assert_awaited_with(orphan)
    orphan.job.delete.assert_called_once()


@pytest.mark.asyncio
async def test_pass1_failed_handler_marks_failed_and_does_not_release():
    from isardvdi_change_handler.streams import reconcile

    orphan = _task("core1", queue="core")
    with (
        patch.object(reconcile.Task, "get_by_status", return_value=[orphan]),
        patch.object(reconcile, "_walk_core_dependents", return_value=[]),
        patch.object(reconcile, "_run_handler", new=AsyncMock(return_value=False)),
        patch.object(reconcile, "_set_job_status", new=AsyncMock()) as set_st,
        patch.object(reconcile, "_release_storage_dependents", new=AsyncMock()) as rel,
    ):
        await reconcile._reconcile_orphan_deferred(AsyncMock())

    set_st.assert_awaited_with(orphan, JobStatus.FAILED)
    rel.assert_not_awaited()


@pytest.mark.asyncio
async def test_pass1_skips_orphan_within_grace():
    from isardvdi_change_handler.streams import reconcile

    fresh = _task("core1", queue="core", dependencies=[_dep(JobStatus.FINISHED, 5)])
    with (
        patch.object(reconcile.Task, "get_by_status", return_value=[fresh]),
        patch.object(reconcile, "_run_handler", new=AsyncMock()) as run_h,
    ):
        healed = await reconcile._reconcile_orphan_deferred(AsyncMock())

    assert healed == 0
    run_h.assert_not_awaited()


@pytest.mark.asyncio
async def test_pass1_storage_orphan_with_finished_parent_is_released():
    from isardvdi_change_handler.streams import reconcile

    parent = _dep(JobStatus.FINISHED, 600)
    orphan = _task("stg1", queue="storage.default.low", dependencies=[parent])
    with (
        patch.object(reconcile.Task, "get_by_status", return_value=[orphan]),
        patch.object(reconcile, "_release_via_parents", new=AsyncMock()) as rel,
    ):
        healed = await reconcile._reconcile_orphan_deferred(AsyncMock())

    assert healed == 1
    rel.assert_awaited_with(orphan)
    orphan.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_pass1_storage_orphan_with_failed_parent_is_cancelled():
    from isardvdi_change_handler.streams import reconcile

    parent = _dep(JobStatus.FAILED, 600)
    orphan = _task("stg1", queue="storage.default.low", dependencies=[parent])
    with (
        patch.object(reconcile.Task, "get_by_status", return_value=[orphan]),
        patch.object(reconcile, "_release_via_parents", new=AsyncMock()) as rel,
    ):
        healed = await reconcile._reconcile_orphan_deferred(AsyncMock())

    assert healed == 1
    # Through ``Task.cancel`` — which settles the whole chain — and never
    # through rq's raw ``job.cancel(enqueue_dependents=True)``, which promoted
    # the chain's finalize dependents onto the consumerless ``core`` queue.
    orphan.cancel.assert_called_once_with()
    orphan.job.cancel.assert_not_called()
    rel.assert_not_awaited()


# ---------------------------------------------------------------------------
# Pass 2 — storages stuck in maintenance whose task is dead
# ---------------------------------------------------------------------------


def _storage(
    sid="s1",
    *,
    status="maintenance",
    task="oldtask",
    virtual_size=171798691840,
    user_id="u1",
):
    s = MagicMock(name=f"storage-{sid}")
    s.id = sid
    s.status = status
    s.task = task
    s.user_id = user_id
    qi = {"virtual-size": virtual_size} if virtual_size is not None else None
    # ``qemu-img-info`` is not a valid attr name; the model exposes it via getattr
    setattr(s, "qemu-img-info", qi)
    return s


def _domain(did="d1", *, status="Maintenance", storages=None, disks=None):
    """A Domain double: a status + its existing ``storages`` + the disks its
    ``create_dict`` declares (used to tell 'storage gone' from 'no disks')."""
    d = MagicMock(name=f"domain-{did}")
    d.id = did
    d.status = status
    d.current_action = "resize"
    d.storages = storages if storages is not None else []
    d.create_dict = {"hardware": {"disks": disks if disks is not None else []}}
    return d


@pytest.mark.asyncio
async def test_pass2_valid_disk_promoted_to_ready():
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(virtual_size=171798691840)
    with (
        patch.object(reconcile.Storage, "get_index", return_value=[storage]),
        patch.object(reconcile, "_task_alive", return_value=False),
        patch.object(reconcile, "_apply_storage_update") as apply_u,
        patch.object(reconcile, "send_status_socket", new=AsyncMock()) as sock,
    ):
        healed = await reconcile._reconcile_stuck_storage(AsyncMock())

    assert healed == 1
    apply_u.assert_called_once_with({"id": "s1", "status": "ready"})
    sock.assert_awaited_once()


@pytest.mark.asyncio
async def test_pass2_skips_storage_with_live_task():
    from isardvdi_change_handler.streams import reconcile

    storage = _storage()
    with (
        patch.object(reconcile.Storage, "get_index", return_value=[storage]),
        patch.object(reconcile, "_task_alive", return_value=True),
        patch.object(reconcile, "_apply_storage_update") as apply_u,
        patch.object(reconcile, "send_status_socket", new=AsyncMock()),
    ):
        healed = await reconcile._reconcile_stuck_storage(AsyncMock())

    assert healed == 0
    apply_u.assert_not_called()


@pytest.mark.asyncio
async def test_pass2_invalid_disk_rechecks_chain_not_finalized():
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(virtual_size=0)
    storage.check_backing_chain = MagicMock()
    with (
        patch.object(reconcile.Storage, "get_index", return_value=[storage]),
        patch.object(reconcile, "_task_alive", return_value=False),
        patch.object(reconcile, "_apply_storage_update") as apply_u,
        patch.object(reconcile, "send_status_socket", new=AsyncMock()),
    ):
        healed = await reconcile._reconcile_stuck_storage(AsyncMock())

    assert healed == 0
    apply_u.assert_not_called()
    storage.check_backing_chain.assert_called_once()


def test_task_alive_false_when_task_missing():
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(task=None)
    assert reconcile._task_alive(storage) is False


def test_task_alive_false_when_task_not_pending():
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(task="t9")
    with (
        patch.object(reconcile.Task, "exists", return_value=True),
        patch.object(reconcile, "Task", wraps=reconcile.Task) as TaskCls,
    ):
        TaskCls.exists.return_value = True
        inst = MagicMock()
        inst.pending = False
        TaskCls.return_value = inst
        assert reconcile._task_alive(storage) is False


# ---------------------------------------------------------------------------
# Pass 3 — domains stuck in a storage-lock status their storage already left
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pass3_promotes_stuck_domain_when_storage_ready():
    """A domain parked in a storage-lock status whose backing storage is
    already ``ready`` and settled (no live task) was missed by the promote and
    must be returned to Stopped."""
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(status="ready")
    dom = _domain(
        status="CreatingTemplate", storages=[storage], disks=[{"storage_id": "s1"}]
    )
    with (
        patch.object(reconcile.Domain, "get_index", return_value=[dom]),
        patch.object(reconcile, "_task_alive", return_value=False),
    ):
        healed = await reconcile._reconcile_stuck_domains(AsyncMock())

    assert healed == 1
    assert dom.status == "Stopped"
    assert dom.current_action is None


@pytest.mark.asyncio
async def test_pass3_fails_domain_whose_storage_row_is_gone():
    """A domain locked in Maintenance whose declared disk's storage row no
    longer exists is orphaned -> Failed."""
    from isardvdi_change_handler.streams import reconcile

    dom = _domain(status="Maintenance", storages=[], disks=[{"storage_id": "gone"}])
    with patch.object(reconcile.Domain, "get_index", return_value=[dom]):
        healed = await reconcile._reconcile_stuck_domains(AsyncMock())

    assert healed == 1
    assert dom.status == "Failed"
    assert dom.current_action is None


@pytest.mark.asyncio
async def test_pass3_fails_domain_with_only_some_storage_rows_left():
    """A domain that declares two disks and resolves one is PARTIALLY gone.

    ``Domain.storages`` drops ids whose row no longer exists, so the surviving
    disk being ``ready`` used to promote the domain to Stopped — a desktop that
    looks bootable and then fails at the next start, with the real cause (a
    deleted disk) lost.
    """
    from isardvdi_change_handler.streams import reconcile

    survivor = _storage("s1", status="ready", task=None)
    domain = _domain(
        "d1",
        storages=[survivor],
        disks=[{"storage_id": "s1"}, {"storage_id": "s2-gone"}],
    )

    assert reconcile._finalize_stuck_domain(domain) == 1
    assert domain.status == "Failed"


@pytest.mark.asyncio
async def test_pass3_leaves_domain_whose_storage_task_is_alive():
    """Storage is ready but a live task is running on it: the op is in flight,
    do not touch the domain (no race with the primary path)."""
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(status="ready")
    dom = _domain(
        status="Maintenance", storages=[storage], disks=[{"storage_id": "s1"}]
    )
    with (
        patch.object(reconcile.Domain, "get_index", return_value=[dom]),
        patch.object(reconcile, "_task_alive", return_value=True),
    ):
        healed = await reconcile._reconcile_stuck_domains(AsyncMock())

    assert healed == 0
    assert dom.status == "Maintenance"


@pytest.mark.asyncio
async def test_pass3_leaves_domain_whose_storage_still_in_maintenance():
    """Storage is still in maintenance (Pass 2 / the consumer owns it): leave
    the domain alone."""
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(status="maintenance")
    dom = _domain(
        status="Maintenance", storages=[storage], disks=[{"storage_id": "s1"}]
    )
    with (
        patch.object(reconcile.Domain, "get_index", return_value=[dom]),
        patch.object(reconcile, "_task_alive", return_value=False),
    ):
        healed = await reconcile._reconcile_stuck_domains(AsyncMock())

    assert healed == 0
    assert dom.status == "Maintenance"


# ---------------------------------------------------------------------------
# run() — eager pass + periodic loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_invokes_both_passes_then_sleeps():
    from isardvdi_change_handler.streams import reconcile

    calls = {"orphan": 0, "stuck": 0, "domains": 0}

    async def _fake_orphan(rm, *a, **k):
        calls["orphan"] += 1
        return 0

    async def _fake_stuck(rm, *a, **k):
        calls["stuck"] += 1
        return 0

    async def _fake_domains(rm, *a, **k):
        calls["domains"] += 1
        return 0

    class _Stop(Exception):
        pass

    async def _sleep_then_stop(_s):
        raise _Stop()

    with (
        patch.object(reconcile, "_reconcile_orphan_deferred", new=_fake_orphan),
        patch.object(reconcile, "_reconcile_stuck_storage", new=_fake_stuck),
        patch.object(reconcile, "_reconcile_stuck_domains", new=_fake_domains),
        patch.object(reconcile.asyncio, "sleep", new=_sleep_then_stop),
    ):
        with pytest.raises(_Stop):
            await reconcile.run(AsyncMock(), interval_s=1)

    assert calls["orphan"] == 1
    assert calls["stuck"] == 1
    assert calls["domains"] == 1


def test_orphan_gate_treats_vanished_dep_job_as_terminal():
    """A DEFERRED orphan whose only parent's RQ job data was evicted is a
    healable orphan (the vanished job is necessarily terminal and long
    settled). The gate must classify it True, never raise — regression for the
    production abandonment "reconcile: orphan heal failed ... Failed to retrieve
    status for job"."""
    from isardvdi_change_handler.streams import reconcile

    now = datetime.now(timezone.utc)
    task = _task(dependencies=[_gone_dep()])
    assert reconcile._deps_terminal_and_aged(task, now, grace_s=120) is True


def test_orphan_gate_live_dep_beats_vanished_dep():
    """A vanished dependency must not mask a still-live sibling: while any
    dependency is running the task is NOT a healable orphan."""
    from isardvdi_change_handler.streams import reconcile

    now = datetime.now(timezone.utc)
    task = _task(dependencies=[_gone_dep(), _dep(JobStatus.STARTED, 600)])
    assert reconcile._deps_terminal_and_aged(task, now, grace_s=120) is False


def test_orphan_gate_vanished_dep_with_finished_aged_sibling():
    """A vanished dep alongside a finished, aged sibling still heals (the
    readable sibling provides the age proof)."""
    from isardvdi_change_handler.streams import reconcile

    now = datetime.now(timezone.utc)
    task = _task(
        dependencies=[_gone_dep(NoSuchJobError()), _dep(JobStatus.FINISHED, 600)]
    )
    assert reconcile._deps_terminal_and_aged(task, now, grace_s=120) is True


# ---------------------------------------------------------------------------
# Pass 1 — orphaned DEFERRED jobs
# ---------------------------------------------------------------------------


# --- Pass 4: media left mid-delete -------------------------------------
#
# These rows are REAL ``Media`` objects, not stand-ins with a stub
# ``delete_file``. That is the whole point of them: an earlier revision of
# this pass selected exactly the statuses ``delete_file`` refused, so every
# row it found raised ``precondition_required``, got swallowed by the
# pass's own ``except Exception`` and healed nothing — and three tests
# built on a hand-written ``delete_file`` stayed green through all of it,
# because the precondition they had to exercise was the one thing they
# replaced. Only persistence and the queue are stubbed below; every
# precondition runs for real.

from isardvdi_change_handler.streams import reconcile  # noqa: E402
from isardvdi_common.models.media import Media  # noqa: E402
from isardvdi_common.models.storage_pool import StoragePool  # noqa: E402
from isardvdi_common.models.task import Task  # noqa: E402


class _StuckMedia(Media):
    """A real ``Media`` whose row lives in memory.

    Mirrors ``isardvdi_common.models.tests.test_media_delete_file``:
    ``RethinkCustomBase`` writes through to RethinkDB on every assignment,
    so the persisted attributes are held in a dict instead. ``delete_file``
    itself is inherited untouched.
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
@pytest.mark.parametrize("status", ["maintenance", "Deleting"])
async def test_pass4_reissues_the_delete_of_stuck_media(
    monkeypatch, _media_queue, status
):
    """Every status the pass selects must be one the real delete accepts.

    This is the regression test for the inert pass: it asserts the delete
    task actually exists afterwards, not merely that something was called.
    """
    media = _StuckMedia(status)
    _index_returns(monkeypatch, [media])

    assert await reconcile._reconcile_stuck_media(None) == 1

    assert len(media.created_tasks) == 1
    assert media.created_tasks[0]["task"] == "delete"
    assert media.created_tasks[0]["job_kwargs"]["kwargs"]["path"] == (
        "/isard/media/m.iso"
    )
    assert media.status == "maintenance"
    assert media.task == "task-1"


@pytest.mark.asyncio
async def test_pass4_settles_a_media_that_never_had_a_file(monkeypatch, _media_queue):
    """No path means no file to unlink, so ``delete_file`` ends it in place."""
    media = _StuckMedia("maintenance", path_downloaded="")
    _index_returns(monkeypatch, [media])

    assert await reconcile._reconcile_stuck_media(None) == 1
    assert media.status == "deleted"
    assert media.created_tasks == []


@pytest.mark.asyncio
async def test_pass4_leaves_media_whose_task_is_alive(monkeypatch, _media_queue):
    """Pass 1 and the consumer own it while the task is still running."""
    media = _StuckMedia("maintenance", task="task-9")
    _index_returns(monkeypatch, [media])
    monkeypatch.setattr(Task, "exists", staticmethod(lambda task_id: True))
    monkeypatch.setattr(Task, "__init__", lambda self, task_id: None)
    monkeypatch.setattr(Task, "pending", property(lambda self: True))

    assert await reconcile._reconcile_stuck_media(None) == 0
    assert media.created_tasks == []
    assert media.status == "maintenance"


@pytest.mark.asyncio
async def test_pass4_survives_a_media_that_cannot_be_re_issued(
    monkeypatch, _media_queue
):
    """A shedding queue must leave the row where it was, not half-moved."""
    media = _StuckMedia("maintenance")
    _index_returns(monkeypatch, [media])

    def boom(**kwargs):
        raise RuntimeError("queue down")

    monkeypatch.setattr(media, "create_task", boom)

    assert await reconcile._reconcile_stuck_media(None) == 0
    assert media.status == "maintenance"


@pytest.mark.asyncio
async def test_pass4_heals_every_status_it_claims_to_watch(monkeypatch, _media_queue):
    """Pin the tuple against the delete it feeds.

    If ``delete_file`` ever grows a precondition that refuses one of these
    statuses again, this fails instead of the pass silently going quiet.
    """
    rows = [_StuckMedia(s) for s in reconcile._MEDIA_STUCK_STATUSES]
    _index_returns(monkeypatch, rows)

    assert await reconcile._reconcile_stuck_media(None) == len(rows)
    assert all(row.created_tasks for row in rows)
