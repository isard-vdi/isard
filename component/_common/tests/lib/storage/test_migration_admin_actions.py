# SPDX-License-Identifier: AGPL-3.0-or-later

"""The admin start/pause/cancel matrix (pure), mirrored from the webapp's
migActionEnabled so the apiv4 service enforces the same gate the UI shows."""

import pytest
from isardvdi_common.lib.storage import migration as mig

NON_TERMINAL = [
    "draft",
    "planned",
    "running",
    "paused",
    "window_closed",
    "finishing_tree",
    "scheduled",
    "budget_reached",
]
TERMINAL = ["completed", "completed_with_skips", "failed", "canceled"]


@pytest.mark.parametrize("action", ["start", "pause", "cancel"])
@pytest.mark.parametrize("status", TERMINAL)
def test_no_admin_action_on_a_terminal_job(status, action):
    assert mig.admin_action_allowed(status, action) is False


@pytest.mark.parametrize("status", NON_TERMINAL)
def test_cancel_allowed_on_any_non_terminal_job(status):
    assert mig.admin_action_allowed(status, "cancel") is True


@pytest.mark.parametrize(
    "status,allowed",
    [
        ("draft", True),
        ("planned", True),
        ("paused", True),
        ("window_closed", True),
        ("scheduled", True),
        ("budget_reached", True),
        ("running", False),  # already running
        ("finishing_tree", False),  # a cancel is in progress; start must not abort it
    ],
)
def test_start_matrix(status, allowed):
    assert mig.admin_action_allowed(status, "start") is allowed


@pytest.mark.parametrize(
    "status,allowed",
    [
        ("running", True),
        ("window_closed", True),
        ("draft", False),
        ("planned", False),
        ("paused", False),  # already paused
        ("finishing_tree", False),
        ("scheduled", False),
        ("budget_reached", False),
    ],
)
def test_pause_matrix(status, allowed):
    assert mig.admin_action_allowed(status, "pause") is allowed


@pytest.mark.parametrize(
    "pause_reason,allowed",
    [
        ("load", True),  # an auto-pause may be converted to a manual one
        ("space", True),
        ("manual", False),  # already manual: set_action no-ops it, gate says no
        ("failure", False),
        (None, False),
    ],
)
def test_pause_on_a_paused_job_only_from_an_auto_pause(pause_reason, allowed):
    assert mig.admin_action_allowed("paused", "pause", pause_reason) is allowed


def test_an_unknown_action_is_refused():
    assert mig.admin_action_allowed("running", "teleport") is False
