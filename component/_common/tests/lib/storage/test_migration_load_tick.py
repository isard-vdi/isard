# SPDX-License-Identifier: AGPL-3.0-or-later

"""The runner side of the adaptive load policy: the tick applies the pure
decision (writes only parallelism, or soft-pauses/resumes), a manual pause is
never auto-resumed, and advance() drives a load-paused job but not a manual one."""

import isardvdi_common.lib.storage.migration_run as mr
import pytest

N = mr.mig.LOAD_RAISE_AFTER_CLEAN_TICKS
PAUSED = mr.MigrationStatus.PAUSED.value
RUNNING = mr.MigrationStatus.RUNNING.value


def _lp(**over):
    lp = {
        "mode": "adaptive",
        "parallelism_min": 1,
        "parallelism_max": 4,
        "pause_above": 50,
        "baseline_window": 5,
    }
    lp.update(over)
    return lp


class _Mig:
    def __init__(self, status, config, pause_reason=None, load_state=None, logs=None):
        self.status = status
        self.config = config
        self.pause_reason = pause_reason
        self.load_state = load_state if load_state is not None else {}
        self.logs = logs if logs is not None else []


def _runner(mig_obj, sample):
    r = object.__new__(mr.MigrationRunner)
    r.migration = mig_obj
    r.config = mig_obj.config
    r._load_sample_fn = lambda: sample
    return r


# --- _apply_load_policy: step down ------------------------------------------ #
def test_busy_lowers_parallelism_and_preserves_the_rest_of_config():
    m = _Mig("running", {"parallelism": 4, "verify": True, "load_policy": _lp()})
    r = _runner(m, {"governor_busy": True})
    parked = r._apply_load_policy()
    assert parked is False
    assert m.config["parallelism"] == 3
    assert m.config["verify"] is True  # only parallelism changed
    assert m.config["load_policy"]["mode"] == "adaptive"
    assert r.config["parallelism"] == 3  # in-memory copy updated for THIS tick
    assert m.load_state["last_action"] == "lower"
    assert m.load_state["effective_parallelism"] == 3
    assert [e["event"] for e in m.logs] == ["load_lower"]


def test_hold_writes_no_config_and_no_log_but_records_reason():
    m = _Mig("running", {"parallelism": 2, "load_policy": _lp()})
    r = _runner(m, {})  # no signals -> neutral -> hold
    r._apply_load_policy()
    assert m.config["parallelism"] == 2
    assert m.logs == []  # holds are not logged (keeps the log bounded)
    assert m.load_state["last_action"] == "hold"


# --- _apply_load_policy: soft pause + auto-resume --------------------------- #
def test_hard_limit_soft_pauses_with_load_reason():
    m = _Mig("running", {"parallelism": 3, "load_policy": _lp(pause_above=50)})
    r = _runner(m, {"desktops_started": 80})
    parked = r._apply_load_policy()
    assert parked is True
    assert str(m.status) == PAUSED
    assert m.pause_reason == "load"
    assert m.config["parallelism"] == 3  # keeps the level to resume at
    assert m.logs[-1]["event"] == "load_pause"


def test_load_paused_resumes_itself_after_clean_ticks():
    m = _Mig(
        "paused",
        {"parallelism": 2, "load_policy": _lp()},
        pause_reason="load",
        load_state={"clean_ticks": N - 1},
    )
    r = _runner(m, {"desktops_started": 5})
    parked = r._apply_load_policy()
    assert parked is False
    assert str(m.status) == RUNNING
    assert m.pause_reason is None
    assert m.logs[-1]["event"] == "load_resume"


def test_load_paused_stays_paused_while_load_persists():
    m = _Mig(
        "paused",
        {"parallelism": 2, "load_policy": _lp()},
        pause_reason="load",
        load_state={"clean_ticks": N - 1},
    )
    r = _runner(m, {"desktops_started": 80})  # still over the ceiling
    parked = r._apply_load_policy()
    assert parked is True
    assert str(m.status) == PAUSED
    assert m.load_state["clean_ticks"] == 0  # reset by the busy tick


# --- a manual/failure pause is never the loop's to resume ------------------- #
@pytest.mark.parametrize("reason", ["manual", "failure", None])
def test_a_non_load_pause_is_left_untouched_and_never_sampled(reason):
    m = _Mig("paused", {"parallelism": 2, "load_policy": _lp()}, pause_reason=reason)
    sampled = {"hit": False}
    r = object.__new__(mr.MigrationRunner)
    r.migration = m
    r.config = m.config

    def _sample():
        sampled["hit"] = True
        return {}

    r._load_sample_fn = _sample
    parked = r._apply_load_policy()
    assert parked is True
    assert str(m.status) == PAUSED
    assert m.pause_reason == reason  # unchanged
    assert sampled["hit"] is False  # never even sampled


# --- a non-running (window/budget/scheduled) job is not throttled ----------- #
def test_window_closed_job_is_not_touched_by_the_loop():
    m = _Mig("window_closed", {"parallelism": 3, "load_policy": _lp()})
    r = _runner(m, {"governor_busy": True})
    parked = r._apply_load_policy()
    assert parked is False
    assert str(m.status) == "window_closed"
    assert m.config["parallelism"] == 3  # untouched


# --- tick() short-circuits when load-parked -------------------------------- #
def test_tick_drives_no_trees_while_load_parked():
    m = _Mig(
        "paused",
        {"parallelism": 2, "load_policy": _lp(pause_above=50)},
        pause_reason="load",
    )
    r = object.__new__(mr.MigrationRunner)
    r.migration = m
    r.config = m.config
    r._load_sample_fn = lambda: {"desktops_started": 999}  # stays parked
    r._publish_progress = lambda: None

    def _boom():
        raise AssertionError("tick drove trees while load-parked")

    r._items = _boom
    assert r.tick() == []


# --- advance() drivability gate -------------------------------------------- #
def _fake_migration(monkeypatch, *, status, pause_reason=None):
    class _M:
        @classmethod
        def exists(cls, mid):
            return True

        def __init__(self, mid):
            self.status = status
            self.pause_reason = pause_reason

    monkeypatch.setattr(mr, "StorageMigration", _M)


def _busy_conn():
    class _Lock:
        def acquire(self):
            return False  # someone else holds it -> advance returns "busy"

    class _Conn:
        def lock(self, *a, **k):
            return _Lock()

        def close(self):
            pass

    return _Conn()


def test_advance_drives_a_load_paused_job(monkeypatch):
    _fake_migration(monkeypatch, status=PAUSED, pause_reason="load")
    monkeypatch.setattr(mr.redis, "from_url", lambda *a, **k: _busy_conn())
    # "busy" (not "not_drivable") proves it passed the gate to the lock
    assert mr.advance("m") == "busy"


@pytest.mark.parametrize("reason", ["manual", "failure", None])
def test_advance_skips_a_non_load_pause(monkeypatch, reason):
    _fake_migration(monkeypatch, status=PAUSED, pause_reason=reason)
    assert mr.advance("m") == "not_drivable"
