#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Single source of truth for the "template not ready" rejection.

``DesktopsProcessed.UNUSABLE_TEMPLATE_STATUSES`` and the guard that reads it,
``DesktopsProcessed.assert_template_usable``, are reused by the background
per-desktop create (``new_from_template``) AND by the synchronous deployment
create / edit-users / recreate paths. Pinned here so the status set and the
``template_not_ready`` code cannot drift or silently shrink — a guard that
stops covering ``CreatingTemplate`` is exactly how a deployment ends up empty
with no message to the user.
"""
import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktops as mod

DP = mod.DesktopsProcessed


@pytest.mark.parametrize(
    "status",
    ["CreatingTemplate", "Failed", "Maintenance", "DownloadStarting", "Downloading"],
)
def test_unusable_status_rejected_with_template_not_ready(status):
    with pytest.raises(Error) as exc:
        DP.assert_template_usable({"id": "t-1", "status": status})
    assert exc.value.error["error"] == "precondition_required"
    assert exc.value.error["description_code"] == "template_not_ready"


@pytest.mark.parametrize("status", ["Stopped", "Started"])
def test_ready_status_passes(status):
    # Returns None (does not raise) for a usable template.
    assert DP.assert_template_usable({"id": "t-1", "status": status}) is None


def test_constant_is_exactly_the_five_unusable_statuses():
    assert set(DP.UNUSABLE_TEMPLATE_STATUSES) == {
        "CreatingTemplate",
        "Failed",
        "Maintenance",
        "DownloadStarting",
        "Downloading",
    }
