# SPDX-License-Identifier: AGPL-3.0-or-later

"""The silent wedge a concurrent re-scan can leave behind: a ``pending`` disk that
still carries a move id. ``_start_move``'s resume claim needs ``state==moving`` and
fails silently on it, stranding the tree in ``drive.active`` for ever. These pin
that such a row is reconciled where the disk truly is (never a silent return, never
an orphaned source) and that a stalled drive pass is surfaced as a WARNING."""

from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.lib.storage import migration_run as mr

from .test_migration_recurring_drive import NOW, _item, _Mig, _runner


def test_decide_item_action_reconciles_a_pending_disk_carrying_a_move_id():
    item = _item("a", "pending", move_task_id="stale", preflight_task_id="pf")
    assert mig.decide_item_action(item, lambda t: "finished") == "reconcile_pending"


def _wedge_runner(
    monkeypatch,
    *,
    at_destination,
    move_delete=None,
    del_status=None,
    storage_status="ready",
    orig_status=None,
):
    item = _item(
        "r",
        "pending",
        tree="r",
        move_task_id="stale",
        preflight_task_id="pf",
        verify_passed=True,
        dst_dir="/dst",
    )
    if move_delete:
        item["move_delete_task_id"] = move_delete
    if orig_status:
        item["storage_orig_status"] = orig_status
    items = [item]
    m = _Mig("running", {"parallelism": 1})
    m.drive = {"active": ["r"], "window_open": True}
    m.record_activity = lambda delta=None: None

    def _jf(t):
        if t == "pf":
            return "finished"
        if move_delete and t == move_delete:
            return del_status
        return None

    r = _runner(monkeypatch, items, m, now=NOW, job_status_fn=_jf)
    r._incremental = False
    r._snapshot = None
    r._progressed = False
    r._space_deferred = False
    r._touched = []
    r._gate_tree = lambda ti: True
    r._is_media = lambda it: False
    storage_updates = []

    class _Storage:
        def __init__(self, sid):
            self.directory_path = "/dst" if at_destination else "/old"
            self.status = storage_status

        @staticmethod
        def exists(sid):
            return True

        @classmethod
        def update_document(cls, sid, fields, validate=True):
            storage_updates.append(fields)

    monkeypatch.setattr(mr, "Storage", _Storage)
    return r, m, item, items, storage_updates


def test_at_destination_with_finished_source_settles_released_and_frees_slot(
    monkeypatch,
):
    r, m, item, items, _su = _wedge_runner(
        monkeypatch, at_destination=True, move_delete="del", del_status="finished"
    )
    warnings = []
    monkeypatch.setattr(mr.log, "warning", lambda *a, **k: warnings.append(a))

    r._drive_tree("r", items, False, [])

    assert str(item["state"]) == "released"
    assert "r" not in (m.drive.get("active") or [])
    assert warnings


def test_at_destination_with_unfinished_source_settles_db_updated(monkeypatch):
    # Destination committed but the source step has NOT run: must settle db_updated
    # so the normal release action deletes/parks the source, never released direct.
    r, m, item, items, _su = _wedge_runner(monkeypatch, at_destination=True)

    r._step_tree("r", items, False, [])

    assert str(item["state"]) == "db_updated"


def test_at_destination_with_retained_source_settles_released(monkeypatch):
    r, m, item, items, _su = _wedge_runner(monkeypatch, at_destination=True)
    item["source_retained"] = True

    r._step_tree("r", items, False, [])

    assert str(item["state"]) == "released"


def test_not_at_destination_restores_storage_left_in_maintenance(monkeypatch):
    r, m, item, items, storage_updates = _wedge_runner(
        monkeypatch,
        at_destination=False,
        storage_status="maintenance",
        orig_status="ready",
    )
    r._restore_storage_status = mr.MigrationRunner._restore_storage_status.__get__(r)
    r._restore_domains = lambda it: None
    warnings = []
    monkeypatch.setattr(mr.log, "warning", lambda *a, **k: warnings.append(a))

    r._step_tree("r", items, False, [])

    assert {"status": "ready"} in storage_updates  # storage put back
    assert item.get("storage_orig_status") is None  # stale record dropped
    assert item.get("move_task_id") != "stale"
    assert str(item["state"]) == "pending"
    assert warnings


# -- the production wedge: a re-scan rewound a disk whose move had FINISHED back to
#    pending. The copy is on the destination but the row is not verified; it must
#    rejoin at ``moved`` (the verify gate settles it), never clear + re-preflight
#    (which trips destination_exists on the copy already written). ---------------- #
def _regressed_mid_move(monkeypatch, move_status):
    r, m, item, items, storage_updates = _wedge_runner(
        monkeypatch,
        at_destination=False,  # db row not repointed yet (directory_path != dst)
        storage_status="maintenance",
        orig_status="ready",
    )
    item["verify_passed"] = False  # the verify gate never ran (the real wedge)
    item["move_task_id"] = "mv"
    item["dst_owned"] = True
    r.job_status_fn = lambda t: move_status if t == "mv" else None
    return r, m, item, items, storage_updates


def test_regressed_pending_with_finished_move_rejoins_at_moved(monkeypatch):
    r, m, item, items, storage_updates = _regressed_mid_move(monkeypatch, "finished")
    r._restore_storage_status = mr.MigrationRunner._restore_storage_status.__get__(r)
    r._restore_domains = lambda it: None

    r._reconcile_regressed_pending(item)

    assert str(item["state"]) == "moved"  # back where the finished move left it
    assert item["move_task_id"] == "mv"  # id kept, not cleared
    assert item.get("storage_orig_status") == "ready"  # kept for the eventual release
    assert {"status": "ready"} not in storage_updates  # storage NOT un-maintenanced


def test_regressed_pending_with_finished_move_next_action_is_not_preflight(monkeypatch):
    r, m, item, items, _su = _regressed_mid_move(monkeypatch, "finished")
    r._reconcile_regressed_pending(item)
    # a root whose move finished -> skip_rebase -> (phase B) verify, never a fresh
    # preflight that would trip destination_exists on the copy already written.
    assert mig.decide_item_action(item, r.job_status_fn) == "skip_rebase"


def test_regressed_pending_with_finished_move_drives_to_verify(monkeypatch):
    r, m, item, items, _su = _regressed_mid_move(monkeypatch, "finished")
    enq = []
    r._enqueue = lambda action, *a, **k: (enq.append(action), "tid")[1]
    r.lane_is_drainable = lambda *a, **k: True
    r._claim_storage_task = lambda *a, **k: None
    # the move id reads finished; the verify task it enqueues ("tid") is still
    # running, so the drive stops cleanly at the verify wait.
    r.job_status_fn = lambda t: "finished" if t == "mv" else "started"

    r._drive_tree("r", items, False, [])

    assert "migration_verify_destination" in enq  # verification enqueued
    assert "migration_verify_destination_absent" not in enq  # NOT re-preflighted
    assert "move" not in enq  # NOT re-copied
    assert str(item["state"]) != "failed"  # no destination_exists terminalization


def test_regressed_pending_with_in_flight_move_restores_moving(monkeypatch):
    r, m, item, items, _su = _regressed_mid_move(monkeypatch, "started")
    r._reconcile_regressed_pending(item)
    assert str(item["state"]) == "moving"  # let the running copy finish
    assert item["move_task_id"] == "mv"  # id kept, the running task is not orphaned


# -- a drive pass that fills every slot but advances nothing is surfaced ------- #
def test_drive_is_stalled_truth_table():
    assert mig.drive_is_stalled(1, 1, progressed=False, awaiting=False) is True
    assert mig.drive_is_stalled(2, 2, progressed=False, awaiting=False) is True
    assert mig.drive_is_stalled(1, 1, progressed=True, awaiting=False) is False
    assert mig.drive_is_stalled(1, 1, progressed=False, awaiting=True) is False
    assert mig.drive_is_stalled(0, 2, progressed=False, awaiting=False) is False


def _stall_runner(monkeypatch):
    item = _item("r", "moving", tree="r", move_task_id="t-r")
    items = [item]
    m = _Mig("running", {"parallelism": 1})
    m.record_activity = lambda delta=None: None
    r = _runner(monkeypatch, items, m, now=NOW)

    def _stuck_step(tree_id, tree_items, finishing, results):
        results.append((tree_id, tree_items[0]["id"], "start_move"))
        return False, False

    r._step_tree = _stuck_step
    warnings = []
    monkeypatch.setattr(mr.log, "warning", lambda *a, **k: warnings.append(a[0]))
    return r, warnings


def test_full_pass_warns_when_slots_full_and_nothing_progresses(monkeypatch):
    r, warnings = _stall_runner(monkeypatch)
    r.tick()
    assert any("not making progress" in w for w in warnings)


def test_stall_warning_is_ascii(monkeypatch):
    r, warnings = _stall_runner(monkeypatch)
    r.tick()
    msg = next(w for w in warnings if "not making progress" in w)
    assert msg.isascii()
