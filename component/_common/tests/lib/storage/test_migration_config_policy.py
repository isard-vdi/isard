# SPDX-License-Identifier: AGPL-3.0-or-later

"""What a running migration lets an admin change, and what it refuses."""

import pytest
from isardvdi_common.lib.storage import migration as mig

CURRENT = {
    "parallelism": 1,
    "bwlimit_kbs": 0,
    "verify": True,
    "force_stop_desktops": False,
    "failure_policy": "pause",
    "min_free_bytes": 10**9,
    "order": "none",
}


def test_a_hot_field_changes_freely():
    assert mig.config_change_verdicts(CURRENT, {"parallelism": 4}) == []


def test_verify_is_frozen_once_the_job_has_moved_anything():
    """Turning it off mid-run changes the safety contract of every disk still
    to come: each one would release its source against an unverified copy."""
    assert mig.config_change_verdicts(CURRENT, {"verify": False}) == [
        ("verify", "frozen")
    ]


def test_sending_the_same_frozen_value_is_not_a_change():
    assert mig.config_change_verdicts(CURRENT, {"verify": True}) == []


@pytest.mark.parametrize(
    "change",
    [
        {"min_free_bytes": 0},
        {"failure_policy": "retry_quarantine"},
        {"force_stop_desktops": True},
    ],
)
def test_weakening_a_guarantee_is_named(change):
    (field,) = change
    assert mig.config_change_verdicts(CURRENT, change) == [(field, "weakening")]


@pytest.mark.parametrize(
    "change",
    [
        {"min_free_bytes": 2 * 10**9},
        {"failure_policy": "pause"},
        {"force_stop_desktops": False},
    ],
)
def test_strengthening_or_keeping_a_guarantee_is_hot(change):
    assert mig.config_change_verdicts(CURRENT, change) == []


def test_a_job_that_moved_nothing_may_change_anything():
    for status in ("draft", "planned"):
        assert not mig.config_is_live(status)
    for status in (
        "running",
        "paused",
        "window_closed",
        "budget_reached",
        "finishing_tree",
        "scheduled",
    ):
        assert mig.config_is_live(status)
