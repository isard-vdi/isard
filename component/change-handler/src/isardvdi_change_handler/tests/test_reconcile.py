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
    # Every real Task carries ``_redis`` (it is how the durable cancel record is
    # read), so the stub must too — otherwise a pass that consults it dies with
    # AttributeError inside the per-task ``except`` and the orphan is abandoned,
    # which reads as "the heal is broken" instead of "the stub is incomplete".
    # ``hget`` -> None means: no cancel record for this member.
    redis = MagicMock(name=f"redis-{task_id}")
    redis.hget.return_value = None
    return SimpleNamespace(
        id=task_id,
        task=task_name,
        queue=queue,
        user_id=user_id,
        dependencies=dependencies if dependencies is not None else [_dep()],
        dependents=dependents or [],
        job=job,
        _redis=redis,
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
    converted_from=None,
    parked_by=None,
):
    s = MagicMock(name=f"storage-{sid}")
    s.id = sid
    s.status = status
    s.task = task
    s.user_id = user_id
    # A convert destination carries no task of its own; the convert task lives on
    # the origin it points at via ``converted_from``. Default None mirrors a
    # non-convert row (MagicMock would otherwise auto-create a truthy attr).
    s.converted_from = converted_from
    # Same shape one step further: a row parked by another row's chain (the new
    # template storage of a template creation) names its parker via ``parked_by``.
    s.parked_by = parked_by
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
async def test_pass2_never_promotes_from_the_rows_cached_disk_info():
    """A positive ``virtual-size`` on the row is not an observation.

    It is written only when an info task succeeded, the branch that concludes
    ``deleted`` does not write it, and the row update merges — so after a
    delete the stale size survives and used to be enough to assert ``ready``.
    The worker is asked instead.
    """
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(virtual_size=171798691840)
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
    # spec off the real class, captured before the patch: a bare MagicMock
    # accepts any attribute name, so a renamed or missing property would read
    # as "settled" and the test would pass against broken code.
    inst = MagicMock(spec=reconcile.Task)
    inst.chain_pending = False
    with (
        patch.object(reconcile.Task, "exists", return_value=True),
        patch.object(reconcile, "Task", wraps=reconcile.Task) as TaskCls,
    ):
        TaskCls.exists.return_value = True
        TaskCls.return_value = inst
        assert reconcile._task_alive(storage) is False


def test_task_alive_creating_without_task_or_origin_is_treated_live():
    """A ``creating`` row with no task and no resolvable origin cannot be proven
    dead — never finalize a disk that may still be mid-build."""
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(status="creating", task=None, converted_from=None)
    assert reconcile._task_alive(storage) is True


def test_task_alive_convert_target_live_while_origin_task_runs():
    """The blocker: a convert destination (task=None) must be seen as LIVE while
    the origin's convert task is still running, so Pass 2 never finalizes the
    half-written destination as ready."""
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(status="creating", task=None, converted_from="origin-1")
    origin = MagicMock()
    origin.task = "convert-task"
    running = MagicMock()
    running.pending = True
    with (
        patch.object(reconcile, "Storage", return_value=origin),
        patch.object(reconcile.Task, "exists", return_value=True),
        patch.object(reconcile, "Task", return_value=running),
        patch.object(reconcile, "_metadata_finalize_orphaned", return_value=False),
    ):
        assert reconcile._task_alive(storage) is True


def test_task_alive_convert_target_recoverable_once_origin_settled():
    """Once the origin's convert task settles, the destination is no longer live
    and Pass 2 may recover it (e.g. a finalize lost to a crash)."""
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(status="creating", task=None, converted_from="origin-1")
    origin = MagicMock()
    origin.task = "convert-task"
    settled = MagicMock(spec=reconcile.Task)
    settled.chain_pending = False
    with (
        patch.object(reconcile, "Storage", return_value=origin),
        patch.object(reconcile.Task, "exists", return_value=True),
        patch.object(reconcile, "Task", return_value=settled),
    ):
        assert reconcile._task_alive(storage) is False


def test_task_alive_parked_template_live_while_its_parker_runs():
    """The other half of the same class: template creation parks the NEW
    template row ``maintenance`` with no task of its own — the move's task
    is on the DESKTOP's row, which the parked row names via ``parked_by``.
    Live until that task settles, or Pass 2 re-checks a path the move has
    not produced yet and fails the template mid-copy."""
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(status="maintenance", task=None, parked_by="desktop-1")
    parker = MagicMock()
    parker.task = "move-task"
    running = MagicMock()
    running.pending = True
    with (
        patch.object(reconcile, "Storage", return_value=parker),
        patch.object(reconcile.Task, "exists", return_value=True),
        patch.object(reconcile, "Task", return_value=running),
        patch.object(reconcile, "_metadata_finalize_orphaned", return_value=False),
    ):
        assert reconcile._task_alive(storage) is True


def test_task_alive_parked_template_recoverable_once_its_parker_settles():
    """Once the parking chain settles, a row still parked IS stuck, and Pass 2
    must recover it — the marker buys the chain its runtime, not immunity."""
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(status="maintenance", task=None, parked_by="desktop-1")
    parker = MagicMock()
    parker.task = "move-task"
    settled = MagicMock(spec=reconcile.Task)
    settled.chain_pending = False
    with (
        patch.object(reconcile, "Storage", return_value=parker),
        patch.object(reconcile.Task, "exists", return_value=True),
        patch.object(reconcile, "Task", return_value=settled),
    ):
        assert reconcile._task_alive(storage) is False


def test_task_alive_ignores_a_stale_parker_on_an_unparked_row():
    """Nothing clears the marker when the chain unparks the row, so it is read
    only while the row is still parked. A ``ready`` row must not borrow the
    liveness of whatever its old parker is doing now — Pass 3 asks this very
    question about ``ready`` storages before finalizing a stuck domain."""
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(status="ready", task=None, parked_by="desktop-1")
    parker = MagicMock()
    parker.task = "some-unrelated-task"
    running = MagicMock()
    running.pending = True
    with (
        patch.object(reconcile, "Storage", return_value=parker),
        patch.object(reconcile.Task, "exists", return_value=True),
        patch.object(reconcile, "Task", return_value=running),
    ):
        assert reconcile._task_alive(storage) is False


def test_task_alive_maintenance_without_task_or_parker_is_still_an_orphan():
    """The door 7425e27021 deliberately left shut stays shut: a ``maintenance``
    row that names neither a task nor a parker is a genuine abandoned op."""
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(status="maintenance", task=None, parked_by=None)
    assert reconcile._task_alive(storage) is False


@pytest.mark.asyncio
async def test_pass2_skips_a_parked_template_row_whose_chain_still_runs():
    """End to end through Pass 2: the parked template row survives the tick
    instead of being finalized from a disk the move has not written yet."""
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(
        status="maintenance", task=None, parked_by="desktop-1", virtual_size=0
    )
    storage.check_backing_chain = MagicMock()
    parker = MagicMock()
    parker.task = "move-task"
    running = MagicMock()
    running.pending = True
    # One double for both uses of the class: the Pass 2 listing and the
    # ``Storage(parked_by)`` lookup the liveness check makes.
    storage_cls = MagicMock()
    storage_cls.get_index.return_value = [storage]
    storage_cls.return_value = parker
    with (
        patch.object(reconcile, "Storage", storage_cls),
        patch.object(reconcile.Task, "exists", return_value=True),
        patch.object(reconcile, "Task", return_value=running),
        patch.object(reconcile, "_metadata_finalize_orphaned", return_value=False),
        patch.object(reconcile, "_apply_storage_update") as apply_u,
        patch.object(reconcile, "send_status_socket", new=AsyncMock()),
    ):
        healed = await reconcile._reconcile_stuck_storage(AsyncMock())

    assert healed == 0
    apply_u.assert_not_called()
    storage.check_backing_chain.assert_not_called()


@pytest.mark.asyncio
async def test_pass2_recovers_a_stuck_creating_storage_by_re_observing():
    """A ``creating`` convert target whose finalize was lost is still
    recovered — through the worker's recheck, not the row's cached size."""
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(status="creating", virtual_size=171798691840)
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
async def test_run_drains_once_then_invokes_passes_then_sleeps():
    from isardvdi_change_handler.streams import reconcile

    calls = {"drain": 0, "orphan": 0, "stuck": 0, "domains": 0}

    async def _fake_drain(rm, *a, **k):
        calls["drain"] += 1
        return 0

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
        patch.object(reconcile, "_drain_core_once", new=_fake_drain),
        patch.object(reconcile, "_reconcile_orphan_deferred", new=_fake_orphan),
        patch.object(reconcile, "_reconcile_stuck_storage", new=_fake_stuck),
        patch.object(reconcile, "_reconcile_stuck_domains", new=_fake_domains),
        patch.object(reconcile, "_assert_core_empty", new=AsyncMock()),
        patch.object(reconcile.asyncio, "sleep", new=_sleep_then_stop),
    ):
        with pytest.raises(_Stop):
            await reconcile.run(AsyncMock(), interval_s=1)

    assert calls["drain"] == 1
    assert calls["orphan"] == 1
    assert calls["stuck"] == 1
    assert calls["domains"] == 1


@pytest.mark.asyncio
async def test_run_retries_drain_until_it_succeeds():
    """A drain that fails (redis not ready yet) leaves the gate open and retries
    on the next tick; once it succeeds it never runs again."""
    from isardvdi_change_handler.streams import reconcile

    drain_calls = []

    async def _flaky_drain(rm, *a, **k):
        drain_calls.append(1)
        if len(drain_calls) == 1:
            raise RuntimeError("redis not ready")
        return 0

    ticks = {"n": 0}

    class _Stop(Exception):
        pass

    async def _sleep(_s):
        ticks["n"] += 1
        if ticks["n"] >= 3:
            raise _Stop()

    with (
        patch.object(reconcile, "_drain_core_once", new=_flaky_drain),
        patch.object(
            reconcile, "_reconcile_orphan_deferred", new=AsyncMock(return_value=0)
        ),
        patch.object(
            reconcile, "_reconcile_stuck_storage", new=AsyncMock(return_value=0)
        ),
        patch.object(
            reconcile, "_reconcile_stuck_domains", new=AsyncMock(return_value=0)
        ),
        patch.object(reconcile, "_assert_core_empty", new=AsyncMock()),
        patch.object(reconcile.asyncio, "sleep", new=_sleep),
    ):
        with pytest.raises(_Stop):
            await reconcile.run(AsyncMock(), interval_s=1)

    # tick1 drain raises (gate open), tick2 drain succeeds (gate closes),
    # tick3 skips it -> exactly two drain attempts.
    assert len(drain_calls) == 2


@pytest.mark.asyncio
async def test_drain_lrange_error_propagates_for_retry():
    """A redis-connectivity failure in the drain must propagate so run() retries;
    it is not swallowed like a per-job error."""
    from isardvdi_change_handler.streams import reconcile

    conn = MagicMock()
    conn.lrange.side_effect = RuntimeError("redis down")
    with patch.object(reconcile, "_drain_connection", return_value=conn):
        with pytest.raises(RuntimeError):
            await reconcile._drain_core_once(AsyncMock())


@pytest.mark.asyncio
async def test_assert_core_empty_warns_when_backlog(caplog):
    from isardvdi_change_handler.streams import reconcile

    conn = MagicMock()
    conn.llen.return_value = 3
    with patch.object(reconcile, "_drain_connection", return_value=conn):
        with caplog.at_level("WARNING"):
            await reconcile._assert_core_empty()
    assert "ConsumerlessQueueBacklog" in caplog.text


@pytest.mark.asyncio
async def test_assert_core_empty_silent_when_zero(caplog):
    from isardvdi_change_handler.streams import reconcile

    conn = MagicMock()
    conn.llen.return_value = 0
    with patch.object(reconcile, "_drain_connection", return_value=conn):
        with caplog.at_level("WARNING"):
            await reconcile._assert_core_empty()
    assert "ConsumerlessQueueBacklog" not in caplog.text


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


# ---------------------------------------------------------------------------
# Pass 1 must honour the durable cancel record, like the consumer does.
#
# A member a worker had already dequeued runs to completion and its success
# handler rewrites the rq status to ``finished`` — so ``job_status`` reads
# finished for a cancelled member and a metadata ``CoreStep`` never reports
# CANCELED at all. Only ``was_canceled`` on the real root sees the cancel. These
# drive the REAL ``_set_job_status`` (spying on ``job.set_status``) rather than
# mocking it away, or they would prove nothing about the flip.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pass1_cancelled_orphan_is_not_flipped_finished():
    """A cancelled chain healed by Pass 1 must NOT have its member flipped
    FINISHED (which would tell a downstream step its dependency succeeded and
    run its success body for an operation the user cancelled)."""
    from isardvdi_change_handler.streams import reconcile

    orphan = _task("core1", queue="core", task_name="storage_update")
    # A redis whose HGET returns the cancel record -> the real ``was_canceled``
    # answers True for this root (no mock of ``was_canceled`` or ``_set_job_status``).
    orphan._redis = MagicMock(name="redis")
    orphan._redis.hget.return_value = b"1"
    # get_status must not read CANCELED, so _set_job_status' own (CoreStep-inert)
    # guard cannot be what saves us — the external was_canceled guard must.
    orphan.job.get_status.return_value = JobStatus.FINISHED

    with (
        patch.object(reconcile.Task, "get_by_status", return_value=[orphan]),
        patch.object(reconcile, "_walk_core_dependents", return_value=[]),
        patch.object(reconcile, "_run_handler", new=AsyncMock(return_value=True)),
        patch.object(reconcile, "_release_storage_dependents", new=AsyncMock()),
    ):
        healed = await reconcile._reconcile_orphan_deferred(AsyncMock())

    assert healed == 1  # it is still healed (handlers run) — just not advanced
    orphan.job.set_status.assert_not_called()


@pytest.mark.asyncio
async def test_pass1_non_cancelled_orphan_is_still_flipped_finished():
    """The guard must not break the normal path: a chain that was NOT cancelled
    is still marked FINISHED by the heal."""
    from isardvdi_change_handler.streams import reconcile

    orphan = _task("core1", queue="core", task_name="storage_update")
    orphan._redis = MagicMock(name="redis")
    orphan._redis.hget.return_value = None  # no cancel record -> was_canceled False
    orphan.job.get_status.return_value = JobStatus.QUEUED

    with (
        patch.object(reconcile.Task, "get_by_status", return_value=[orphan]),
        patch.object(reconcile, "_walk_core_dependents", return_value=[]),
        patch.object(reconcile, "_run_handler", new=AsyncMock(return_value=True)),
        patch.object(reconcile, "_release_storage_dependents", new=AsyncMock()),
    ):
        await reconcile._reconcile_orphan_deferred(AsyncMock())

    orphan.job.set_status.assert_called_once_with(JobStatus.FINISHED)


@pytest.mark.asyncio
async def test_pass1_does_not_release_the_children_of_a_cancelled_member():
    """A member cancelled on its own must not have its storage children released.

    ``doomed`` is computed from the ROOT's dependencies, so a chain whose root
    is alive passes it — and that is exactly the shape rq leaves when a worker
    had already dequeued the member: the member is CANCELED while the root is
    not. Releasing there runs real disk work for an operation that is over. The
    consumer gates its own release per member; the heal did not.
    """
    from isardvdi_change_handler.streams import reconcile

    orphan = _task("core1", queue="core", task_name="storage_update")
    orphan._redis = MagicMock(name="redis")
    orphan._redis.hget.return_value = None  # the ROOT carries no cancel record
    orphan.job.get_status.return_value = JobStatus.QUEUED
    orphan.job_status = JobStatus.QUEUED

    member = _task("core2", queue="core", task_name="update_status")
    member._redis = orphan._redis
    member.job.get_status.return_value = JobStatus.CANCELED
    member.job_status = JobStatus.CANCELED

    with (
        patch.object(reconcile.Task, "get_by_status", return_value=[orphan]),
        patch.object(reconcile, "_walk_core_dependents", return_value=[member]),
        patch.object(reconcile, "_run_handler", new=AsyncMock(return_value=True)),
        patch.object(reconcile, "_release_storage_dependents", new=AsyncMock()) as rel,
    ):
        healed = await reconcile._reconcile_orphan_deferred(AsyncMock())

    assert healed == 1
    released = [call.args[0].id for call in rel.await_args_list]
    assert "core1" in released  # the live root still advances
    assert "core2" not in released  # the cancelled member does not
