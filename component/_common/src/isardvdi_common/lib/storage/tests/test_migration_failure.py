# SPDX-License-Identifier: AGPL-3.0-or-later

"""Failure-path regression tests for the migration saga (qcow-1 / scheduler-1 /
qcow-3 / saga-5).

The happy-path tests never exercised a failed move/rebase, so four real wedges
went untested:
  * qcow-1: a "fail"/"blocked" task action had no handler -> silent no-op,
    disk stuck forever, job never terminal, autostart never restored.
  * scheduler-1: a single FAILED disk made the tree permanently "blocked";
    descendant_item_ids()/cascade existed but was never wired in.
  * qcow-3: a failed/blocked disk's storage stayed in "maintenance" -> the
    desktop was unstartable.
  * saga-5: _release hardcoded status "ready", un-binning a "recycled" disk.
"""

import isardvdi_common.lib.storage.migration_run as mr
from isardvdi_common.lib.storage import migration as mig


def _it(sid, parent, state, **kw):
    base = {
        "id": f"i-{sid}",
        "storage_id": sid,
        "tree_id": "s0",
        "topo_index": 0 if sid == "s0" else 1,
        "parent_storage_id": parent,
        "state": state,
    }
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# plan_tree_failure (pure) — cascade-skip descendants + abandon the rest
# --------------------------------------------------------------------------- #
def test_plan_tree_failure_cascades_and_abandons():
    items = [
        _it("s0", None, "db_updated"),  # committed ancestor — abandoned
        _it("s1", "s0", "moving"),  # the disk that fails
        _it("s2", "s1", "pending"),  # descendant of the failed disk
        _it("s3", "s0", "pending"),  # sibling subtree — abandoned
    ]
    plan = {
        it["id"]: (state, why) for it, state, why in mig.plan_tree_failure(items, "s1")
    }
    assert plan["i-s1"][0] == "failed"
    assert plan["i-s2"][0] == "skipped"  # descendant
    assert plan["i-s0"][0] == "skipped"  # committed ancestor abandoned (source kept)
    assert plan["i-s3"][0] == "skipped"  # sibling abandoned
    # reasons distinguish descendants from the rest
    assert "ancestor" in plan["i-s2"][1]


def test_plan_tree_failure_leaves_terminal_disks_untouched():
    items = [
        _it("s0", None, "released"),  # already terminal
        _it("s1", "s0", "failed"),  # already failed (e.g. generic handler)
        _it("s2", "s1", "skipped"),  # already skipped
    ]
    # everything terminal already -> nothing to change
    assert mig.plan_tree_failure(items, "s1") == []


# --------------------------------------------------------------------------- #
# qcow-1: the executor MUST handle "fail" and "blocked" (not silently no-op)
# --------------------------------------------------------------------------- #
def test_actions_table_handles_fail_and_blocked():
    assert "fail" in mr.MigrationRunner._ACTIONS
    assert "blocked" in mr.MigrationRunner._ACTIONS


# --------------------------------------------------------------------------- #
# saga-5 / qcow-3: storage status is restored to the RECORDED original, and a
# disk we never put into maintenance is left untouched.
# --------------------------------------------------------------------------- #
def _runner():
    return object.__new__(mr.MigrationRunner)


def test_restore_storage_status_uses_recorded_original(monkeypatch):
    updates = []

    class _S:
        @classmethod
        def update_document(cls, sid, fields, validate=True):
            updates.append((sid, fields))

    monkeypatch.setattr(mr, "Storage", _S)
    # a recycled disk dragged into a subtree must be restored to recycled,
    # never hardcoded "ready" (which would un-bin it for a later purge).
    _runner()._restore_storage_status(
        {"storage_id": "s1", "storage_orig_status": "recycled"}
    )
    assert updates == [("s1", {"status": "recycled"})]


def test_restore_storage_status_skips_untouched_disk(monkeypatch):
    updates = []

    class _S:
        @classmethod
        def update_document(cls, sid, fields, validate=True):
            updates.append((sid, fields))

    monkeypatch.setattr(mr, "Storage", _S)
    # never put into maintenance (no recorded original) -> do not touch it
    _runner()._restore_storage_status({"storage_id": "s2"})
    assert updates == []


def test_terminalize_resets_storage_and_cascades(monkeypatch):
    items = [
        _it("s0", None, "db_updated", storage_orig_status="ready"),
        _it("s1", "s0", "moving", storage_orig_status="recycled"),  # fails
        _it("s2", "s1", "pending"),  # descendant, never touched
    ]
    item_updates = []
    storage_updates = []

    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "dicts_by_migration",
        classmethod(lambda cls, mid: items),
    )
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "update_document",
        classmethod(
            lambda cls, iid, fields, validate=True: item_updates.append((iid, fields))
        ),
    )

    class _S:
        @classmethod
        def update_document(cls, sid, fields, validate=True):
            storage_updates.append((sid, fields))

    monkeypatch.setattr(mr, "Storage", _S)

    r = _runner()
    r.migration_id = "m"
    r._terminalize_tree_failure(items[1])  # s1's task failed

    states = {iid: f["state"] for iid, f in item_updates if "state" in f}
    assert states["i-s1"] == "failed"
    assert states["i-s2"] == "skipped"  # cascade to descendant
    assert states["i-s0"] == "skipped"  # committed ancestor abandoned
    su = dict(storage_updates)
    # qcow-3 + saga-5: maintenance disks reset to their ORIGINAL status
    assert su["s1"] == {"status": "recycled"}
    assert su["s0"] == {"status": "ready"}
    assert "s2" not in su  # never in maintenance -> untouched


# --------------------------------------------------------------------------- #
# job_status() failure classification — the PRODUCTION gap the real e2e exposed.
# A raised storage task reports rq Job.get_status()=="finished" WITH exc_info set
# (it does NOT flip to "failed"); the reconciler must classify exc_info-bearing
# jobs as failed or it advances the saga and move_deletes the live source (data
# loss). These exercise the REAL job_status() against the REAL rq condition — no
# job_status_fn mock, which is exactly the mask that hid this from the earlier
# fail-cluster unit tests.
# --------------------------------------------------------------------------- #
class _RqLikeTask:
    """Mimics real rq: a task that RAISED ends status="finished" but carries
    exc_info; a clean task is "finished" with exc_info None."""

    _raised = {"raised", "t-move", "t-rebase"}

    def __init__(self, tid):
        self._id = tid

    @classmethod
    def exists(cls, tid):
        return tid is not None

    @property
    def job_status(self):
        return "finished"  # rq reports FINISHED even for a raised task

    @property
    def exc_info(self):
        return "Traceback...\nNotADirectoryError" if self._id in self._raised else None

    @property
    def result(self):
        # a clean (non-raised) storage task returns 0; move/rebase/verify all do
        return 0


def test_job_status_classifies_raised_task_as_failed(monkeypatch):
    monkeypatch.setattr(mr, "Task", _RqLikeTask)
    # raised task: rq says finished, but exc_info present -> classified failed
    assert mr.job_status("raised") == "failed"
    # clean task: no exc_info -> the rq status passes through
    assert mr.job_status("ok") == "finished"
    # no task id yet (pending) -> None
    assert mr.job_status(None) is None


def test_decide_item_action_fails_a_raised_move(monkeypatch):
    """End-to-end of the gap: with the REAL job_status() over a raised task, a
    disk in `moving`/`moved` resolves to `fail`, never mark_moved/mark_rebased."""
    monkeypatch.setattr(mr, "Task", _RqLikeTask)
    moving = {
        "state": "moving",
        "move_task_id": "t-move",
        "topo_index": 1,
        "parent_dst_path": "/p/parent.qcow2",
    }
    assert mig.decide_item_action(moving, mr.job_status) == "fail"
    moved = {
        "state": "moved",
        "rebase_task_id": "t-rebase",
        "topo_index": 1,
        "parent_dst_path": "/p/parent.qcow2",
    }
    assert mig.decide_item_action(moved, mr.job_status) == "fail"


# --------------------------------------------------------------------------- #
# Sibling data-loss path: a move whose rsync FAILS returns a non-zero rc WITHOUT
# raising (run_with_progress returns the rc on a non-cancel non-zero exit), so
# the job is finished/exc_info=None with a non-zero int return. Before the fix
# job_status() returned "finished" -> the disk was marked moved and (for a ROOT
# disk, which skips rebase) reached release and move_deleted a live source
# against an absent/partial destination. These pin the REAL job_status() over
# that real rq condition — no job_status mock.
# --------------------------------------------------------------------------- #
class _RqNonZeroMove:
    """A move task that rsync-failed: finished, no exc_info, non-zero int rc."""

    def __init__(self, tid):
        self._id = tid

    @classmethod
    def exists(cls, tid):
        return tid is not None

    @property
    def job_status(self):
        return "finished"

    @property
    def exc_info(self):
        return None  # rsync returned non-zero; the worker did NOT raise

    @property
    def result(self):
        return 23 if self._id == "rsync-fail" else 0  # 23 == rsync partial xfer


def test_job_status_classifies_nonzero_move_return_as_failed(monkeypatch):
    monkeypatch.setattr(mr, "Task", _RqNonZeroMove)
    # rsync-failed move: finished + non-zero rc + no exc_info -> failed
    assert mr.job_status("rsync-fail") == "failed"
    # a clean move returns 0 -> the rq status passes through
    assert mr.job_status("ok") == "finished"


def test_decide_item_action_fails_a_nonzero_move(monkeypatch):
    """A ROOT disk's rsync-failed move resolves to fail at the moving step, so it
    never reaches mark_moved -> skip_rebase -> release -> move_delete."""
    monkeypatch.setattr(mr, "Task", _RqNonZeroMove)
    root_moving = {"state": "moving", "move_task_id": "rsync-fail", "topo_index": 0}
    assert mig.decide_item_action(root_moving, mr.job_status) == "fail"


# --------------------------------------------------------------------------- #
# The unconditional pre-release destination gate: a committed (db_updated) disk's
# source is NEVER released/move_deleted until a verify task proves the
# destination is good. This is the core invariant the second data-loss path
# violated for ROOT disks (which skip rebase, so had no destination check at
# all). Asserted on the pure tree_next/decide_release_action — no mocks of the
# saga; a dict job_status_fn drives only the verify task's status.
# --------------------------------------------------------------------------- #
def _committed_root():
    # a single-disk (root) tree, fully committed, awaiting release
    return {
        "id": "i-r",
        "storage_id": "s-r",
        "tree_id": "s-r",
        "topo_index": 0,
        "state": "db_updated",
        "src_path": "/src/s-r.qcow2",
        "dst_path": "/dst/s-r.qcow2",
    }


def test_release_blocked_until_destination_verified():
    item = _committed_root()
    # no verify task yet -> the saga enqueues the gate, NOT release
    it, action = mig.tree_next([item], lambda tid: None)
    assert action == "start_verify"
    assert it["id"] == "i-r"
    # gate enqueued, still running -> wait (still no release)
    item["verify_task_id"] = "v1"
    assert mig.tree_next([item], lambda tid: "started")[1] == "wait"
    # gate passed -> NOW release is allowed
    assert mig.tree_next([item], lambda tid: "finished")[1] == "release"


def test_failed_verify_terminalizes_never_releases():
    item = _committed_root()
    item["verify_task_id"] = "v1"
    # destination gate FAILED -> fail (terminalize), never release/move_delete
    it, action = mig.tree_next([item], lambda tid: "failed")
    assert action == "fail"


def test_verify_gate_state_transitions():
    """Direct pin of the gate states: 'passed' (the only state that licenses a
    release) is reached ONLY when the verify task finished clean."""
    item = _committed_root()
    assert mig.verify_gate_state(item, lambda tid: "finished") == "start"  # no task
    item["verify_task_id"] = "v1"
    assert mig.verify_gate_state(item, lambda tid: None) == "start"  # lost -> redo
    assert mig.verify_gate_state(item, lambda tid: "failed") == "fail"
    assert mig.verify_gate_state(item, lambda tid: "started") == "wait"
    assert mig.verify_gate_state(item, lambda tid: "finished") == "passed"


def test_no_source_released_until_every_destination_verified():
    """verify-all-then-release-all: in a parent+child tree, a child whose
    destination FAILS verification must terminalize the tree with NO release of
    the parent — the parent source is never recycled while a child gate is unmet,
    so the retained sources stay an intact bootable chain."""
    parent = {
        "id": "i-p",
        "storage_id": "s-p",
        "tree_id": "s-p",
        "topo_index": 0,
        "state": "db_updated",
        "src_path": "/src/p.qcow2",
        "dst_path": "/dst/p.qcow2",
        "verify_task_id": "vp",
    }
    child = {
        "id": "i-c",
        "storage_id": "s-c",
        "tree_id": "s-p",
        "topo_index": 1,
        "state": "db_updated",
        "src_path": "/src/c.qcow2",
        "dst_path": "/dst/c.qcow2",
        "parent_dst_path": "/dst/p.qcow2",
        "verify_task_id": "vc",
    }
    # parent gate PASSED, child gate FAILED -> the tree fails on the child and
    # NO release action is ever issued (parent source stays put).
    status = {"vp": "finished", "vc": "failed"}
    it, action = mig.tree_next([parent, child], lambda tid: status.get(tid))
    assert action == "fail" and it["id"] == "i-c"
    # while the child gate is still running, the parent is NOT released either.
    status = {"vp": "finished", "vc": "started"}
    it, action = mig.tree_next([parent, child], lambda tid: status.get(tid))
    assert action == "wait"
    # only once BOTH gates pass does a release begin (parent first).
    status = {"vp": "finished", "vc": "finished"}
    it, action = mig.tree_next([parent, child], lambda tid: status.get(tid))
    assert action == "release"


def test_in_place_disk_skips_verify_and_release():
    """An in-place disk (dst == src) never moved and has no separate source to
    delete; it must skip straight to skip_release (no verify, no move_delete)."""
    item = _committed_root()
    item["dst_path"] = item["src_path"]  # in place
    assert mig.tree_next([item], lambda tid: "finished")[1] == "skip_release"


# --------------------------------------------------------------------------- #
# R2 cancel-aware skip (pure): under an admin cancel (finishing_tree), a tree
# that has committed NO disk must be SKIPPED rather than start/resume an
# un-started — possibly large — move/rebase/verify (the abandoned-move-resumed-
# 10x-on-cancel wedge). A tree that already committed a disk finishes normally.
# --------------------------------------------------------------------------- #
def test_tree_has_committed_disk():
    def tree(*states):
        return [{"state": s} for s in states]

    assert mig.tree_has_committed_disk(tree("db_updated", "pending")) is True
    assert mig.tree_has_committed_disk(tree("moving", "released")) is True
    # nothing past 'moving'/'rebased' counts as committed
    assert mig.tree_has_committed_disk(tree("pending", "moving")) is False
    assert mig.tree_has_committed_disk(tree("moved", "rebased")) is False


def test_cancel_skips_uncommitted_tree_resuming_work():
    uncommitted = [{"state": "moving"}, {"state": "pending"}]
    # cancel + a resume/start of move/rebase/verify on an uncommitted tree -> skip
    for action in ("start_move", "start_rebase", "start_verify"):
        assert mig.cancel_skips_tree(uncommitted, action, finishing=True) is True


def test_cancel_does_not_skip_committed_tree():
    committed = [{"state": "db_updated"}, {"state": "moving"}]
    # a tree that already committed a disk finishes normally even under cancel
    for action in ("start_move", "start_rebase", "start_verify"):
        assert mig.cancel_skips_tree(committed, action, finishing=True) is False


def test_cancel_skip_only_for_starting_actions_and_only_when_finishing():
    uncommitted = [{"state": "moving"}]
    # not finishing -> never skip (normal resume applies)
    assert mig.cancel_skips_tree(uncommitted, "start_move", finishing=False) is False
    # finishing but the action is NOT a start/resume (advance/commit/release) ->
    # let it proceed; only un-started work is discarded on cancel
    for action in ("mark_moved", "db_update", "release", "wait", "blocked"):
        assert mig.cancel_skips_tree(uncommitted, action, finishing=True) is False


# --------------------------------------------------------------------------- #
# R2 cancel-aware skip + orphan-resume bound (BEHAVIORAL, runner-level): the
# pure-decision tests above pin tree_next/cancel_skips_tree; these drive the real
# MigrationRunner.tick() over an in-memory ledger (StorageMigrationItem / Storage
# / DesktopEvents / enqueue stubbed at the boundary, like
# test_terminalize_resets_storage_and_cascades) so the data-loss-critical side
# effects are committed regression nets on a path that DELETES disks:
#   * the orphan-RESUME is BOUNDED — a task whose worker keeps dying terminalizes
#     the tree (FAILED) instead of resuming forever, and NEVER move_deletes a
#     source (no data loss); storage is restored, autostart reactivated.
#   * an admin cancel (finishing_tree) of an in-flight UNCOMMITTED tree skips it
#     (sources retained, recycled status preserved not clobbered, autostart
#     restored, CANCELED) and never enqueues a move_delete; a COMMITTED tree under
#     the same cancel still finishes (its verified source IS released) — only
#     un-committed work is discarded on cancel.
#   * abandon_restarts resets to 0 on a genuine phase advance (so the bound counts
#     CONSECUTIVE abandonments per phase) yet still climbs to terminalize a disk
#     whose worker dies every time.
# --------------------------------------------------------------------------- #
class _FakeMig:
    """Only the migration fields MigrationRunner.tick() reads/writes."""

    def __init__(self, status):
        self.status = status
        self.current_window = None

    def recompute_totals(self):
        pass


def _tick_runner(monkeypatch, items, status, job_status_fn):
    """A MigrationRunner whose ledger is the in-memory ``items`` list and whose
    Storage / DesktopEvents / enqueue are captured (no DB, no redis). Mirrors the
    boundary-stub pattern of test_terminalize_resets_storage_and_cascades; returns
    ``(runner, caps)`` where caps records every side effect tick() produces."""
    caps = {
        "item_updates": [],
        "storage_updates": [],
        "enqueued": [],
        "activated": [],
        "deactivated": [],
    }

    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "dicts_by_migration",
        classmethod(lambda cls, mid: items),
    )

    def _upd(cls, iid, fields, validate=True):
        caps["item_updates"].append((iid, dict(fields)))
        for it in items:
            if it["id"] == iid:
                it.update(fields)

    monkeypatch.setattr(mr.StorageMigrationItem, "update_document", classmethod(_upd))

    class _S:
        def __init__(self, sid):
            self._sid = sid

        @property
        def status(self):
            for it in items:
                if it["storage_id"] == self._sid:
                    return it.get("_live_status", "ready")
            return "ready"

        @classmethod
        def update_document(cls, sid, fields, validate=True):
            caps["storage_updates"].append((sid, dict(fields)))

    monkeypatch.setattr(mr, "Storage", _S)

    class _DE:
        @staticmethod
        def activate_autostart(ids):
            caps["activated"].extend(ids)

        @staticmethod
        def deactivate_autostart(ids):
            caps["deactivated"].extend(ids)

    monkeypatch.setattr(mr, "DesktopEvents", _DE)

    r = _runner()
    r.migration_id = "m"
    r.migration = _FakeMig(status)
    r.config = {}
    r.user_id = "admin"
    r.dst_pool = None
    r.job_status_fn = job_status_fn

    def _enq(task, queue, kwargs, timeout=None):
        caps["enqueued"].append(task)
        return f"tid-{task}"

    r._enqueue = _enq
    r._pool_queue = lambda path: "q"
    r._move_queue = lambda path: "q"
    r._domains = lambda sid: []
    r._publish_progress = lambda: None
    r.prepare = lambda: None
    return r, caps


def test_orphan_resume_is_bounded_and_never_move_deletes(monkeypatch):
    """The bound: a move whose worker dies every tick (job_status -> None ==
    abandoned) is resumed exactly MAX_ABANDON_RESTARTS times, then the tree is
    terminalized FAILED — never an infinite resume, and NEVER a move_delete (the
    live source is retained). Storage is restored to its original (recycled, not
    clobbered to ready) and autostart is reactivated from the ledger."""
    root = _it(
        "s0",
        None,
        "moving",
        move_task_id="mt",
        storage_orig_status="recycled",  # was binned; must NOT be un-binned
        autostart_domains=[{"id": "d1", "was_on": True}],
        src_path="/src/s0.qcow2",
        dst_path="/dst/s0.qcow2",
    )
    child = _it("s1", "s0", "pending")
    items = [root, child]
    r, caps = _tick_runner(monkeypatch, items, "running", lambda tid: None)

    ticks = 0
    for _ in range(mr.MAX_ABANDON_RESTARTS + 5):
        r.tick()
        ticks += 1
        if r.is_complete():
            break

    # resumed exactly MAX times, then terminalized on the (MAX+1)th tick
    assert ticks == mr.MAX_ABANDON_RESTARTS + 1
    assert caps["enqueued"].count("move") == mr.MAX_ABANDON_RESTARTS
    # the data-loss invariant: a bounded failure NEVER deletes a source
    assert "move_delete" not in caps["enqueued"]
    # tree terminalized FAILED (failed disk -> failed, descendant -> skipped)
    assert root["state"] == "failed"
    assert child["state"] == "skipped"
    assert r.migration.status == mr.MigrationStatus.FAILED.value
    # storage restored to its ORIGINAL recycled, never hardcoded ready (saga-5)
    s0_status = [f["status"] for sid, f in caps["storage_updates"] if sid == "s0"]
    assert s0_status[-1] == "recycled"
    assert "ready" not in s0_status
    # autostart reactivated from the ledger
    assert caps["activated"] == ["d1"]


def test_cancel_skips_uncommitted_in_flight_tree(monkeypatch):
    """Admin cancel (finishing_tree) of an in-flight tree that has committed no
    disk and whose next action would RESUME a move (worker died -> job_status
    None): the tree is SKIPPED, not resumed. Nothing is enqueued (no resumed
    move, crucially no move_delete), the recycled status is restored (not
    clobbered to ready), autostart is reactivated, and the job ends CANCELED."""
    root = _it(
        "s0",
        None,
        "moving",
        move_task_id="mt",
        storage_orig_status="recycled",
        autostart_domains=[{"id": "d1", "was_on": True}],
        src_path="/src/s0.qcow2",
        dst_path="/dst/s0.qcow2",
    )
    child = _it("s1", "s0", "pending")
    items = [root, child]
    r, caps = _tick_runner(monkeypatch, items, "finishing_tree", lambda tid: None)
    r.tick()

    assert r.is_complete()
    assert root["state"] == "skipped" and child["state"] == "skipped"
    # nothing enqueued at all -> no resumed move, and no move_delete (no data loss)
    assert caps["enqueued"] == []
    # recycled status restored, never clobbered to ready
    assert ("s0", {"status": "recycled"}) in caps["storage_updates"]
    assert ("s0", {"status": "ready"}) not in caps["storage_updates"]
    # autostart restored + job canceled (not completed/failed)
    assert caps["activated"] == ["d1"]
    assert r.migration.status == mr.MigrationStatus.CANCELED.value


def test_cancel_still_finishes_a_committed_tree(monkeypatch):
    """The same admin cancel must NOT skip a tree that already committed a disk:
    a db_updated root whose destination is verified finishes normally — its
    source IS released (move_deleted) — and only then does the finishing job flip
    to CANCELED."""
    root = _it(
        "s0",
        None,
        "db_updated",
        verify_task_id="vt",
        storage_orig_status="recycled",
        src_path="/src/s0.qcow2",
        dst_path="/dst/s0.qcow2",
    )
    items = [root]
    r, caps = _tick_runner(monkeypatch, items, "finishing_tree", lambda tid: "finished")
    r.tick()

    assert r.is_complete()
    assert root["state"] == "released"
    # committed tree finishes -> the verified source IS deleted (not skipped)
    assert "move_delete" in caps["enqueued"]
    # a finishing job ends canceled even though the committed tree finished
    assert r.migration.status == mr.MigrationStatus.CANCELED.value


def _capture_item_sets(monkeypatch):
    sets = []
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "update_document",
        classmethod(
            lambda cls, iid, fields, validate=True: sets.append((iid, dict(fields)))
        ),
    )
    return sets


def test_abandon_restarts_reset_on_phase_advance(monkeypatch):
    """Every genuine phase advance (moved / rebased / db_updated) resets
    abandon_restarts to 0, so the bound counts CONSECUTIVE abandonments per phase
    rather than cumulatively over the disk's whole move->rebase->db lifetime."""
    sets = _capture_item_sets(monkeypatch)

    class _S:
        @classmethod
        def update_document(cls, sid, fields, validate=True):
            pass

    monkeypatch.setattr(mr, "Storage", _S)
    r = _runner()
    r.migration_id = "m"

    r._mark_moved(_it("s0", None, "moving", abandon_restarts=5))
    r._mark_rebased(_it("s0", None, "moved", abandon_restarts=5))
    r._db_update(
        _it(
            "s0",
            None,
            "rebased",
            abandon_restarts=5,
            dst_dir="/dst",
            dst_path="/dst/s0.qcow2",
        )
    )

    advances = [f for _, f in sets if "abandon_restarts" in f]
    assert advances and all(f["abandon_restarts"] == 0 for f in advances)
    assert {f["state"] for f in advances} == {"moved", "rebased", "db_updated"}


def test_abandon_resume_climbs_to_terminalize_when_stuck(monkeypatch):
    """A disk whose worker dies on every resume still terminalizes: the first
    MAX_ABANDON_RESTARTS resumes are permitted (budget climbs 1..MAX), the
    (MAX+1)th is blocked and terminalizes the tree FAILED."""
    _capture_item_sets(monkeypatch)
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "dicts_by_migration",
        classmethod(lambda cls, mid: [item]),
    )

    class _S:
        @classmethod
        def update_document(cls, sid, fields, validate=True):
            pass

    monkeypatch.setattr(mr, "Storage", _S)
    r = _runner()
    r.migration_id = "m"

    item = _it("s0", None, "moving", move_task_id="mt", abandon_restarts=0)
    for n in range(1, mr.MAX_ABANDON_RESTARTS + 1):
        assert r._abandon_resume_blocked(item) is False
        assert item["abandon_restarts"] == n
    # budget spent -> terminalize, do NOT resume again
    assert r._abandon_resume_blocked(item) is True
    assert item["state"] == "failed"
