# SPDX-License-Identifier: AGPL-3.0-or-later

"""The adaptive load policy: how the pure decision steps parallelism,
soft-pauses and resumes by real load, and never oscillates."""

import pytest
from isardvdi_common.lib.storage import migration as mig

N = mig.LOAD_RAISE_AFTER_CLEAN_TICKS


def _policy(mode="adaptive", low=1, high=4, pause_above=0, baseline_window=5):
    return {
        "mode": mode,
        "parallelism_min": low,
        "parallelism_max": high,
        "pause_above": pause_above,
        "baseline_window": baseline_window,
    }


def _state(par, clean=0, paused=False):
    return {"parallelism": par, "clean_ticks": clean, "paused_by_load": paused}


def _drive(samples, policy, par, clean=0, paused=False):
    """Feed decide() tick by tick, applying its result forward exactly as the
    runner does, and return the list of decisions."""
    out = []
    for sample in samples:
        d = mig.decide(sample, _state(par, clean, paused), policy)
        par, clean = d.parallelism, d.clean_ticks
        if d.action == "pause":
            paused = True
        elif d.action == "resume":
            paused = False
        out.append(d)
    return out


# --- config helpers --------------------------------------------------------- #
def test_static_or_absent_is_not_adaptive():
    assert not mig.load_policy_is_adaptive(None)
    assert not mig.load_policy_is_adaptive({"load_policy": {"mode": "static"}})
    assert not mig.load_policy_is_adaptive({})


def test_adaptive_flag():
    assert mig.load_policy_is_adaptive({"load_policy": {"mode": "adaptive"}})


def test_normalize_fills_defaults_from_partial():
    p = mig.normalize_load_policy({"mode": "adaptive", "parallelism_max": 8})
    assert p["mode"] == "adaptive"
    assert p["parallelism_max"] == 8
    assert p["parallelism_min"] == mig.LOAD_POLICY_DEFAULTS["parallelism_min"]


def test_min_greater_than_max_is_an_error():
    errs = mig.load_policy_errors({"load_policy": _policy(low=5, high=4)})
    assert any("parallelism_min" in e for e in errs)


def test_adaptive_parallelism_out_of_range_is_an_error():
    cfg = {"parallelism": 1, "load_policy": _policy(low=2, high=4)}
    assert any("within" in e for e in mig.load_policy_errors(cfg))


def test_static_ignores_the_parallelism_range():
    cfg = {"parallelism": 10, "load_policy": _policy(mode="static", low=1, high=4)}
    assert mig.load_policy_errors(cfg) == []


def test_no_load_policy_is_no_error():
    assert mig.load_policy_errors({"parallelism": 9}) == []


# --- classify_load ---------------------------------------------------------- #
def test_governor_busy_classifies_busy():
    assert mig.classify_load({"governor_busy": True}, _policy()) == "busy"


def test_governor_idle_classifies_idle():
    assert mig.classify_load({"governor_busy": False}, _policy()) == "idle"


def test_any_busy_signal_wins_over_idle_ones():
    sample = {"governor_busy": False, "nfs_rpc_s": 400.0, "nfs_baseline": 100.0}
    assert mig.classify_load(sample, _policy()) == "busy"


def test_no_signals_is_neutral():
    assert mig.classify_load({}, _policy()) == "neutral"


def test_nfs_dead_band_abstains():
    # 120 rpc/s over a 100 baseline: above LOW (+20%) and below HIGH (+50%).
    assert (
        mig.classify_load({"nfs_rpc_s": 125.0, "nfs_baseline": 100.0}, _policy())
        == "neutral"
    )


def test_desktop_soft_band_votes_by_pause_above():
    pol = _policy(pause_above=100)
    assert mig.classify_load({"desktops_started": 90}, pol) == "busy"
    assert mig.classify_load({"desktops_started": 40}, pol) == "idle"
    assert mig.classify_load({"desktops_started": 60}, pol) == "neutral"


def test_desktop_signal_abstains_without_a_ceiling():
    assert (
        mig.classify_load({"desktops_started": 500}, _policy(pause_above=0))
        == "neutral"
    )


# --- load_over_hard_limit --------------------------------------------------- #
def test_hard_limit_fires_at_or_above_ceiling():
    pol = _policy(pause_above=50)
    assert mig.load_over_hard_limit({"desktops_started": 50}, pol)
    assert mig.load_over_hard_limit({"desktops_started": 51}, pol)
    assert not mig.load_over_hard_limit({"desktops_started": 49}, pol)


def test_hard_limit_off_when_ceiling_is_zero():
    assert not mig.load_over_hard_limit(
        {"desktops_started": 9999}, _policy(pause_above=0)
    )


# --- decide: step down ------------------------------------------------------ #
def test_busy_lowers_one_step():
    d = mig.decide({"governor_busy": True}, _state(4), _policy())
    assert (d.parallelism, d.action) == (3, "lower")


def test_busy_at_min_holds():
    d = mig.decide({"governor_busy": True}, _state(1), _policy(low=1))
    assert (d.parallelism, d.action) == (1, "hold")


def test_lower_is_immediate_no_clean_ticks_needed():
    # one busy tick drops it, unlike the raise which waits N clean ticks
    d = mig.decide({"governor_busy": True}, _state(4, clean=0), _policy())
    assert d.action == "lower"


# --- decide: step up (slow, hysteresis) ------------------------------------- #
def test_idle_raises_only_after_n_clean_ticks():
    ds = _drive([{"governor_busy": False}] * N, _policy(high=4), par=2)
    assert [d.action for d in ds[:-1]] == ["hold"] * (N - 1)
    assert ds[-1].action == "raise"
    assert ds[-1].parallelism == 3


def test_raise_capped_at_max():
    ds = _drive([{"governor_busy": False}] * (N + 2), _policy(high=2), par=2)
    assert all(d.action == "hold" for d in ds)
    assert all(d.parallelism == 2 for d in ds)


# --- decide: no oscillation ------------------------------------------------- #
def test_a_neutral_tick_resets_the_clean_counter():
    # idle, idle, neutral, idle, idle -> never raises: the neutral tick breaks
    # the run, so N CONSECUTIVE clean ticks are required.
    samples = [
        {"governor_busy": False},
        {"governor_busy": False},
        {},  # neutral
        {"governor_busy": False},
        {"governor_busy": False},
    ]
    ds = _drive(samples, _policy(high=8), par=2)
    assert all(d.action == "hold" for d in ds)
    assert all(d.parallelism == 2 for d in ds)


def test_busy_then_immediate_idle_does_not_bounce_back_up():
    samples = [{"governor_busy": True}, {"governor_busy": False}]
    ds = _drive(samples, _policy(high=4), par=3)
    assert ds[0].action == "lower" and ds[0].parallelism == 2
    assert ds[1].action == "hold" and ds[1].parallelism == 2


# --- decide: soft pause + auto-resume --------------------------------------- #
def test_hard_limit_soft_pauses():
    d = mig.decide({"desktops_started": 60}, _state(3), _policy(pause_above=50))
    assert d.action == "pause"
    assert d.parallelism == 3  # keeps the level to resume at


def test_paused_stays_paused_while_load_persists():
    d = mig.decide(
        {"desktops_started": 60}, _state(3, paused=True), _policy(pause_above=50)
    )
    assert d.action == "hold"
    assert d.clean_ticks == 0  # persistent load keeps resetting the counter


def test_paused_resumes_after_n_clean_ticks():
    ds = _drive(
        [{"desktops_started": 10}] * N,
        _policy(pause_above=50),
        par=3,
        paused=True,
    )
    assert [d.action for d in ds[:-1]] == ["hold"] * (N - 1)
    assert ds[-1].action == "resume"
    assert ds[-1].parallelism == 3


def test_a_busy_tick_mid_ease_defers_the_resume():
    # easing, easing, BUSY (resets), then it takes N fresh clean ticks again
    samples = [
        {"desktops_started": 10},
        {"desktops_started": 10},
        {"desktops_started": 60},
    ]
    ds = _drive(samples, _policy(pause_above=50), par=3, paused=True)
    assert [d.action for d in ds] == ["hold", "hold", "hold"]
    assert ds[-1].clean_ticks == 0


def test_full_cycle_lower_then_pause_then_resume():
    samples = (
        [{"governor_busy": True}]  # lower 3->2
        + [{"desktops_started": 80}]  # pause (over 50)
        + [{"desktops_started": 5}] * N  # clean -> resume
    )
    ds = _drive(samples, _policy(low=1, high=4, pause_above=50), par=3)
    assert ds[0].action == "lower"
    assert ds[1].action == "pause"
    assert ds[-1].action == "resume"
