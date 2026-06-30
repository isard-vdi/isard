"""Row-level trim (prune-deleted / cap-history) tests."""

from __future__ import annotations

from anonymize_db.prune import Pruner

NOW = 1_700_000_000.0
DAY = 86400


def reql(epoch):
    return {"$reql_type$": "TIME", "epoch_time": epoch}


def test_off_by_default():
    p = Pruner(0, 0)
    assert not p.active
    assert not p.should_drop("recycle_bin", {"accessed": 0})
    assert not p.should_drop("usage_consumption", {"date": reql(0)})


def test_prune_deleted_recycle_bin_by_age():
    p = Pruner(prune_deleted_days=30, now=NOW)
    assert p.should_drop("recycle_bin", {"accessed": NOW - 40 * DAY})
    assert not p.should_drop("recycle_bin", {"accessed": NOW - 10 * DAY})


def test_prune_deleted_storage_needs_status_and_age():
    p = Pruner(prune_deleted_days=30, now=NOW)
    mk = lambda s, t: {"status": s, "status_logs": [{"status": s, "time": t}]}
    assert p.should_drop("storage", mk("deleted", NOW - 40 * DAY))
    assert not p.should_drop("storage", mk("deleted", NOW - 10 * DAY))  # too recent
    assert not p.should_drop("storage", mk("ready", NOW - 40 * DAY))  # not deleted
    assert not p.should_drop("storage", {"status": "deleted"})  # no time -> keep


def test_prune_deleted_media_case_insensitive():
    p = Pruner(prune_deleted_days=30, now=NOW)
    assert p.should_drop("media", {"status": "deleted", "status_time": NOW - 40 * DAY})
    assert p.should_drop("media", {"status": "Deleted", "accessed": NOW - 40 * DAY})
    assert not p.should_drop(
        "media", {"status": "Downloaded", "status_time": NOW - 40 * DAY}
    )


def test_cap_history_logs_and_usage():
    p = Pruner(cap_history_days=30, now=NOW)
    assert p.should_drop("logs_desktops", {"started_time": reql(NOW - 40 * DAY)})
    assert not p.should_drop("logs_desktops", {"started_time": reql(NOW - 10 * DAY)})
    assert p.should_drop("logs_users", {"started_time": reql(NOW - 40 * DAY)})
    assert p.should_drop("usage_consumption", {"date": reql(NOW - 40 * DAY)})
    assert not p.should_drop("usage_consumption", {"date": reql(NOW - 10 * DAY)})


def test_policies_are_independent():
    pd = Pruner(prune_deleted_days=30, now=NOW)
    assert not pd.affects("logs_desktops")
    assert not pd.should_drop("usage_consumption", {"date": reql(NOW - 40 * DAY)})
    ph = Pruner(cap_history_days=30, now=NOW)
    assert not ph.affects("recycle_bin")
    assert not ph.should_drop("recycle_bin", {"accessed": NOW - 40 * DAY})


def test_counts_tracked():
    p = Pruner(prune_deleted_days=30, cap_history_days=30, now=NOW)
    p.should_drop("recycle_bin", {"accessed": NOW - 40 * DAY})
    p.should_drop("usage_consumption", {"date": reql(NOW - 40 * DAY)})
    assert p.counts == {"recycle_bin": 1, "usage_consumption": 1}
