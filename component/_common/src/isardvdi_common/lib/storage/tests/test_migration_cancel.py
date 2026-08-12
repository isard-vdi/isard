# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the P2.4 cancel-target decision (pure).

Cancel means finish-current-tree: a started job drains its in-flight tree (and
restores autostart) via finishing_tree before becoming canceled; a job that
never started cancels outright.
"""

from isardvdi_common.lib.storage import migration as mig


def test_cancel_started_job_finishes_tree_first():
    for status in ("running", "window_closed", "paused", "finishing_tree"):
        assert mig.cancel_target(status) == "finishing_tree"


def test_cancel_unstarted_job_is_immediate():
    for status in ("draft", "planned"):
        assert mig.cancel_target(status) == "canceled"
