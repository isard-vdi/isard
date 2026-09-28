# SPDX-License-Identifier: AGPL-3.0-or-later

"""``RECOVERABLE_STATUSES`` and the verdict built on it; the reconcile side of the
contract is in the change-handler suite, which is not installed here."""

import pytest
from isardvdi_common.models.storage import (
    RECOVERABLE_STATUSES,
    verdict_for_blocked_disks,
)


def test_a_terminal_status_is_not_in_the_list():
    for terminal in ("deleted", "non_existing", "orphan", "broken_chain", "recycled"):
        assert terminal not in RECOVERABLE_STATUSES


def test_the_list_is_not_empty_and_is_immutable():
    assert RECOVERABLE_STATUSES
    assert isinstance(RECOVERABLE_STATUSES, tuple)


@pytest.mark.parametrize(
    "statuses", [["maintenance"], ["creating"], ["maintenance", "creating"]]
)
def test_only_recoverable_blockers_keep_the_desktop_stopped(statuses):
    assert verdict_for_blocked_disks(statuses) == "Stopped"


@pytest.mark.parametrize(
    "statuses",
    [
        ["deleted"],
        ["orphan"],
        ["broken_chain"],
        ["recycled"],
        ["non_existing"],
        ["maintenance", "deleted"],
    ],
)
def test_one_terminal_blocker_fails_the_desktop(statuses):
    assert verdict_for_blocked_disks(statuses) == "Failed"


def test_no_blockers_at_all_is_stopped_which_keeps_todays_behaviour():
    # An empty list is a race, not a terminal disk: keep what the code did before.
    assert verdict_for_blocked_disks([]) == "Stopped"


def test_a_generator_is_accepted_because_the_call_site_passes_one():
    assert verdict_for_blocked_disks(s for s in ["deleted"]) == "Failed"
