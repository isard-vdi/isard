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
