# SPDX-License-Identifier: AGPL-3.0-or-later

"""The job ETA follows the job's own committed throughput, not one tree's."""

from types import SimpleNamespace

from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.lib.storage import migration_run as mr

from .test_migration_recurring_drive import NOW, WINDOW, _item, _Mig, _runner

MIB = 1024**2
TIB = 1024**4
# a 1,741-tree pass at parallelism 4: every tree alone ran ~80 MB/s, the job
# as a whole committed 555 MiB/s, and ~4 TiB were left after half an hour
TREE_MBPS = 80.0
JOB_BPS = 555 * MIB
ACTIVE_S = 1800
REMAINING = 4 * TIB


def _job(**kw):
    base = dict(
        id="m",
        status="running",
        config={"parallelism": 4},
        throughput_ewma={"fast:slow": TREE_MBPS},
        job_rate={"seconds": ACTIVE_S, "bytes": JOB_BPS * ACTIVE_S},
        totals={"bytes_total": REMAINING + JOB_BPS * ACTIVE_S},
        current_window=None,
    )
    base["totals"]["bytes_done"] = JOB_BPS * ACTIVE_S
    base.update(kw)
    return SimpleNamespace(**base)


def test_aggregate_eta_uses_the_job_rate_not_one_trees():
    eta = mig.aggregate_summary(_job())["eta_seconds"]
    assert eta == int(REMAINING / JOB_BPS)  # 2 h 6 min
    assert eta < 2.2 * 3600  # the per-tree rate said over 15 h


def test_status_eta_uses_the_job_rate():
    size = REMAINING // 2
    items = [
        {"tree_id": t, "state": "pending", "size_bytes": size, "kind": "desktop"}
        for t in ("a", "b")
    ]
    job = _job(totals={})
    eta = mig.aggregate_status(job, items, include_trees=False)["eta_seconds"]
    assert eta == int(REMAINING / JOB_BPS)


def test_the_tree_rate_stands_in_until_the_job_has_a_minute_of_history():
    job = _job(job_rate={"seconds": 30, "bytes": JOB_BPS * 30})
    assert mig.job_eta_seconds(job, 10**9) == 10**9 / (TREE_MBPS * 1_000_000)


def test_no_rate_at_all_gives_no_eta():
    assert mig.job_eta_seconds(_job(job_rate={}, throughput_ewma={}), 10) is None


def test_nothing_left_is_zero():
    assert mig.job_eta_seconds(_job(), 0) == 0.0


def test_only_gaps_with_a_tree_in_flight_count():
    s = mig.job_rate_update({}, 0, True, 1000.0)
    s = mig.job_rate_update(s, 600, True, 1060.0)
    assert (s["seconds"], s["bytes"]) == (60.0, 600)
    s = mig.job_rate_update(s, 900, False, 1120.0)
    assert (s["seconds"], s["bytes"]) == (120.0, 900)
    # idle, paused or window closed: neither the hours nor the bytes count
    s = mig.job_rate_update(s, 950, True, 9000.0)
    assert (s["seconds"], s["bytes"]) == (120.0, 900)
    s = mig.job_rate_update(s, 1250, True, 9060.0)
    assert (s["seconds"], s["bytes"]) == (180.0, 1200)


def test_a_rearm_that_lowers_bytes_done_never_subtracts():
    s = mig.job_rate_update({}, 1000, True, 0.0)
    s = mig.job_rate_update(s, 400, True, 60.0)
    assert s["bytes"] == 0 and s["seconds"] == 60.0


def _clock(monkeypatch, t):
    monkeypatch.setattr(mr, "time", lambda: t)


def test_tick_accumulates_active_time_while_a_tree_is_in_flight(monkeypatch):
    items = [_item("r", "moving", move_task_id="mt")]
    m = _Mig("running", {"window": WINDOW})
    m.last_occurrence = "2026-07-01"
    m.job_rate = {}
    r = _runner(monkeypatch, items, m, now=NOW, job_status_fn=lambda t: "started")
    _clock(monkeypatch, 1000.0)
    r.tick()
    _clock(monkeypatch, 1060.0)
    r.tick()
    assert m.job_rate["seconds"] == 60.0
    assert m.job_rate["active"] is True


def test_tick_with_nothing_in_flight_stops_the_clock(monkeypatch):
    items = [_item("r", "released")]
    m = _Mig("running", {"window": WINDOW})
    m.last_occurrence = "2026-07-01"
    m.job_rate = {"at": 900.0, "active": False, "seconds": 5.0, "bytes": 5}
    r = _runner(monkeypatch, items, m, now=NOW)
    _clock(monkeypatch, 5000.0)
    r.tick()
    assert m.job_rate["seconds"] == 5.0
    assert m.job_rate["active"] is False
