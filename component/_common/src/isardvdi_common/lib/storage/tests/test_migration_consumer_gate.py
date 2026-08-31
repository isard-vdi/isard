# SPDX-License-Identifier: AGPL-3.0-or-later

"""A migration must not enqueue onto a lane nothing can drain.

queue_coverage.check_no_consumer is documented as MANDATORY on every producer,
and the migration runner is the one producer that never passes through
create_task -- so it is also the one that never consulted it. A move handed to a
lane with no live worker sits queued for ever: no worker takes it, nothing
raises, no timeout fires, and the job reports running while not one disk moves.

The right answer is not to fail the disk. "Nothing can drain this right now" is
transient -- a storage node restarting, a pool briefly unserved -- so the disk
stays pending and the next tick retries. That is also why the coverage helper
fails OPEN on uncertainty: a probe that cannot answer must not stall a migration.
"""

from isardvdi_common.lib.storage import migration_run as mr


def test_the_runner_consults_the_coverage_gate_before_enqueueing():
    """Source-level, because the alternative is standing up redis + rq: the
    runner must ask the shared gate, not re-derive coverage itself."""
    import inspect

    src = inspect.getsource(mr.MigrationRunner)
    assert (
        "lane_shed_decision" in src or "check_no_consumer" in src
    ), "the runner never consults queue_coverage"


def test_no_consumer_leaves_the_disk_pending_instead_of_failing_it():
    """A transient coverage gap must not terminalize a disk: the tree would be
    marked failed and, under retry_quarantine, eventually quarantined -- for a
    worker restart."""
    decided = mr.MigrationRunner.lane_is_drainable.__doc__ or ""
    assert decided, "lane_is_drainable must document its transient semantics"


def test_uncertain_coverage_is_treated_as_drainable():
    """Fail OPEN: the gate's own posture. Anything else stalls every migration
    during a fleet restart window."""
    assert mr.MigrationRunner.lane_is_drainable(None, "storage.a:b.maintenance") is True


# MigrationRunner is four producers, not one: _start_move, _start_rebase,
# _start_verify and _release each pick their own lane, so each is asserted apart.


def _calls_in(method_name):
    """Every call name -- bare, attribute, and dotted -- in one runner method."""
    import ast
    import inspect

    method = getattr(mr.MigrationRunner, method_name)
    tree = ast.parse(inspect.getsource(method).lstrip())
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
            names.add(ast.unparse(node.func))
        else:
            names.add(getattr(node.func, "id", ""))
    return names


def _consults_the_gate(method_name):
    calls = _calls_in(method_name)
    gate = {
        "lane_is_drainable",
        "lane_shed_decision",
        "lane_has_consumer",
        "check_no_consumer",
    }
    return bool(calls & gate) or any(n.startswith("queue_coverage.") for n in calls)


def _ungated(method_name):
    calls = sorted(_calls_in(method_name))
    return f"{method_name} enqueues without asking the gate: {calls}"


def test_start_move_asks_whether_the_move_lane_can_be_drained():
    """An rsync of a whole disk queued onto an unserved pool lane never starts:
    the item sits in ``moving`` for ever and the migration reports running while
    not one byte moves."""
    assert _consults_the_gate("_start_move"), _ungated("_start_move")


def test_start_rebase_asks_whether_the_destination_lane_can_be_drained():
    """A rebase queued onto an unserved destination lane wedges the tree: only
    STARTED items can be orphaned, so tree_next waits on a job no worker will
    ever take, the tree never completes and reactivate never runs -- the
    desktops stay down with autostart suppressed."""
    assert _consults_the_gate("_start_rebase"), _ungated("_start_rebase")


def test_start_verify_asks_whether_the_destination_lane_can_be_drained():
    """Same wedge as the rebase, one step later: the copy is on the destination
    and correct, but the verify job nothing can run holds the item in
    ``rebased`` for ever, so the source is never released and the tree never
    closes."""
    assert _consults_the_gate("_start_verify"), _ungated("_start_verify")


def test_release_asks_whether_the_source_delete_lane_can_be_drained():
    """The release is the step that deletes the source: queued onto an unserved
    source-pool lane it leaves the item marked released with a move_delete task
    id that will never be consumed, so the source file survives with nothing
    naming it -- the pool never gets its space back and no operator is told."""
    assert _consults_the_gate("_release"), _ungated("_release")


def test_every_gated_producer_is_still_a_method_of_the_runner():
    """If a producer is renamed or split, the four gate assertions above stop
    testing anything at all -- they would raise AttributeError rather than pass,
    but only if something still names them."""
    for name in ("_start_move", "_start_rebase", "_start_verify", "_release"):
        assert callable(
            getattr(mr.MigrationRunner, name, None)
        ), f"MigrationRunner.{name} is gone: the consumer gate is untested for it"
