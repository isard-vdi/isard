# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the P2.2 window + EWMA-ETA admission DECISION layer (pure).

These pin the admission rules that gate when a tree may start:
  * the daily window (incl. overnight wrap) and the time left in it,
  * the self-correcting EWMA throughput estimate,
  * the per-disk 12h move-timeout guard and the optimistic cold-start admit.
The live wiring (now-in-tz, ledger throughput sample) is exercised in the gate.
"""

from math import inf

from isardvdi_common.lib.storage import migration as mig


# --------------------------------------------------------------------------- #
# parse_hhmm
# --------------------------------------------------------------------------- #
def test_parse_hhmm():
    assert mig.parse_hhmm("00:00") == 0
    assert mig.parse_hhmm("06:30") == 390
    assert mig.parse_hhmm("23:59") == 1439
    for bad in (None, "", "24:00", "12:60", "nope", "12", 7):
        assert mig.parse_hhmm(bad) is None


# --------------------------------------------------------------------------- #
# window_is_open
# --------------------------------------------------------------------------- #
def test_window_open_same_day():
    s, e = mig.parse_hhmm("22:00"), mig.parse_hhmm("23:30")
    assert mig.window_is_open(s, e, mig.parse_hhmm("22:30")) is True
    assert mig.window_is_open(s, e, mig.parse_hhmm("21:59")) is False
    assert mig.window_is_open(s, e, mig.parse_hhmm("23:30")) is False  # end exclusive


def test_window_open_overnight():
    s, e = mig.parse_hhmm("22:00"), mig.parse_hhmm("06:00")
    assert mig.window_is_open(s, e, mig.parse_hhmm("23:00")) is True
    assert mig.window_is_open(s, e, mig.parse_hhmm("02:00")) is True
    assert mig.window_is_open(s, e, mig.parse_hhmm("12:00")) is False


def test_window_no_window_always_open():
    assert mig.window_is_open(None, 360, 120) is True
    assert mig.window_is_open(360, None, 120) is True
    assert mig.window_is_open(360, 360, 120) is True  # zero-width


# --------------------------------------------------------------------------- #
# window_remaining_seconds
# --------------------------------------------------------------------------- #
def test_window_remaining_same_day():
    s, e = mig.parse_hhmm("22:00"), mig.parse_hhmm("23:00")
    assert mig.window_remaining_seconds(s, e, mig.parse_hhmm("22:00")) == 3600
    assert mig.window_remaining_seconds(s, e, mig.parse_hhmm("22:45")) == 900


def test_window_remaining_overnight():
    s, e = mig.parse_hhmm("22:00"), mig.parse_hhmm("06:00")
    # 02:00 -> 4h to close
    assert mig.window_remaining_seconds(s, e, mig.parse_hhmm("02:00")) == 4 * 3600
    # 23:00 -> 7h to close (wraps midnight)
    assert mig.window_remaining_seconds(s, e, mig.parse_hhmm("23:00")) == 7 * 3600


def test_window_remaining_closed_and_unbounded():
    s, e = mig.parse_hhmm("22:00"), mig.parse_hhmm("23:00")
    assert mig.window_remaining_seconds(s, e, mig.parse_hhmm("12:00")) == 0
    assert mig.window_remaining_seconds(None, None, 600) == inf


# --------------------------------------------------------------------------- #
# ewma_update
# --------------------------------------------------------------------------- #
def test_ewma_seeds_then_blends():
    assert mig.ewma_update(None, 100.0) == 100.0  # cold start seeds
    # 0.3*200 + 0.7*100 = 130
    assert mig.ewma_update(100.0, 200.0, alpha=0.3) == 130.0


def test_ewma_ignores_bad_samples():
    assert mig.ewma_update(100.0, None) == 100.0
    assert mig.ewma_update(100.0, 0) == 100.0
    assert mig.ewma_update(100.0, -5) == 100.0


# --------------------------------------------------------------------------- #
# tree_eta_seconds
# --------------------------------------------------------------------------- #
def test_tree_eta():
    # 100 MB at 50 MB/s = 2s
    assert mig.tree_eta_seconds(100_000_000, 50.0) == 2.0
    assert mig.tree_eta_seconds(0, 50.0) == 0.0
    assert mig.tree_eta_seconds(100, None) is None  # unknown throughput
    assert mig.tree_eta_seconds(100, 0) is None


# --------------------------------------------------------------------------- #
# tree_admitted
# --------------------------------------------------------------------------- #
def test_admit_unknown_eta_is_optimistic():
    # cold start (no sample): admit regardless of window
    assert mig.tree_admitted(None, None, 10) is True


def test_admit_fits_window():
    assert mig.tree_admitted(100.0, 100.0, 200) is True
    assert mig.tree_admitted(300.0, 300.0, 200) is False  # won't finish in window


def test_admit_unbounded_window():
    assert mig.tree_admitted(10_000.0, 10_000.0, inf) is True


def test_admit_rejects_disk_over_task_timeout():
    # a single disk whose ETA exceeds 12h can never finish a move
    assert mig.tree_admitted(100.0, 50_000.0, inf, task_timeout=43200) is False
