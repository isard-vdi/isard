# SPDX-License-Identifier: AGPL-3.0-or-later

"""R3 — the adaptive loop must not rewrite the whole config from its stale copy.

The runner reads ``self.config`` once at construction and keeps it for a whole
drain (up to 500 ticks). The old load policy wrote ``{**self.config, parallelism}``
back as the entire config, so an ``update_config`` an admin made mid-drain (e.g.
raising ``min_free_pct``) was silently reverted on the next lower/raise. The fix
writes ONLY parallelism (rethinkdb deep-merges) and refreshes ``self.config`` from
the row at the top of every tick, so a live edit is both kept and honoured.
"""

import isardvdi_common.lib.storage.migration_run as mr
import pytest


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


class _Row:
    """A migration row whose writes model rethinkdb's nested deep-merge."""

    def __init__(self, status, config, pause_reason=None):
        self.id = "m"
        self.status = status
        self.config = config
        self.pause_reason = pause_reason
        self.load_state = {}
        self.logs = []

    def _update_cache(self, **fields):
        for key, value in fields.items():
            setattr(self, key, value)

    def fresh_status(self):
        return self.status, self.pause_reason

    def fresh_config(self):
        return self.config

    def update_document(self, _doc_id, update_data, *, validate=True):
        for key, value in update_data.items():
            if isinstance(value, dict) and isinstance(getattr(self, key, None), dict):
                getattr(self, key).update(value)
            else:
                setattr(self, key, value)

    @staticmethod
    def update_document_if(*a, **k):
        return True


def _runner(row, *, stale_config, sample):
    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "m"
    r.migration = row
    r.config = stale_config  # the drain's cached copy, deliberately out of date
    r._load_sample_fn = lambda: sample
    return r


def test_load_policy_writes_only_parallelism_and_keeps_a_concurrent_edit():
    # the row now holds a min_free_pct an admin raised mid-drain; the runner's
    # cached self.config still carries the old value.
    row = _Row("running", {"parallelism": 4, "min_free_pct": 5, "load_policy": _lp()})
    r = _runner(
        row,
        stale_config={"parallelism": 4, "min_free_pct": 10, "load_policy": _lp()},
        sample={"governor_busy": True},  # -> decide "lower"
    )
    r._apply_load_policy()
    assert row.config["parallelism"] == 3  # the loop's decision landed
    assert row.config["min_free_pct"] == 5  # the live edit was NOT clobbered to 10


def test_tick_refreshes_config_from_the_row():
    row = _Row(
        "paused",
        {"parallelism": 2, "min_free_pct": 5, "load_policy": _lp(pause_above=50)},
        pause_reason="load",
    )
    r = _runner(
        row,
        stale_config={
            "parallelism": 2,
            "min_free_pct": 10,
            "load_policy": _lp(pause_above=50),
        },
        sample={"desktops_started": 999},  # stays load-parked -> tick returns []
    )
    r._publish_progress = lambda: None

    def _boom():
        raise AssertionError("tick drove trees while load-parked")

    r._items = _boom
    assert r.tick() == []
    assert r.config["min_free_pct"] == 5  # refreshed from the row, not the stale 10
