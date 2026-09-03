#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Every lane the migration runner enqueues on is a governed one.

The runner is the only storage producer that builds its own tasks instead of
going through ``Storage.create_task``, so nothing else applies the tier rules on
its behalf. Hand-building ``storage.<pool>.default`` left its two middle steps --
a ``qemu-img rebase`` that walks the whole backing chain, and a destination
verify that reads the copied disk end to end -- on a lane that is neither
fair-scheduled per category nor PSI-deferred, for work that runs for hours.

The floor has to live in the tier rules rather than at the call site: resolving
``default`` for an action with no floor yields ``interactive``, so retiering the
lane without giving these two actions a home would have promoted them onto the
reserved lane desktops start on -- worse than the ungoverned lane they were on.
"""

import pytest
from isardvdi_common.lib import queue_tiers
from isardvdi_common.lib.storage import migration_run as mr

MIGRATION_ACTIONS = ("move", "rebase", "migration_verify_destination", "move_delete")


@pytest.mark.parametrize("action", ["rebase", "migration_verify_destination"])
def test_the_middle_steps_are_floored_to_maintenance(action):
    assert queue_tiers.normalize_tier("default", action) == "maintenance"


@pytest.mark.parametrize("action", ["rebase", "migration_verify_destination"])
def test_a_foreground_request_cannot_lift_them(action):
    """A floored action ignores what the caller asked for."""
    for requested in ("interactive", "standard", "high"):
        assert queue_tiers.normalize_tier(requested, action) == "maintenance"


@pytest.mark.parametrize("action", MIGRATION_ACTIONS)
def test_every_action_the_runner_enqueues_lands_on_a_governed_tier(action):
    """No task this runner produces may reach a reserved or std-lane worker."""
    tier = queue_tiers.normalize_tier(mr.DEFAULT_PRIORITY, action)
    assert tier in queue_tiers._GOVERNED_TIERS


@pytest.mark.parametrize("action", MIGRATION_ACTIONS)
def test_every_action_the_runner_enqueues_is_fair_scheduled(action):
    tier = queue_tiers.normalize_tier(mr.DEFAULT_PRIORITY, action)
    assert tier in queue_tiers._FAIR_TIERS


def _runner(pool_id="p-dst"):
    runner = object.__new__(mr.MigrationRunner)

    class _Pool:
        id = pool_id

    runner._pool_of = lambda path: _Pool()
    return runner


@pytest.mark.parametrize(
    "action,tier",
    [
        ("rebase", "maintenance"),
        ("migration_verify_destination", "maintenance"),
        ("move_delete", "reclaim"),
    ],
)
def test_pool_queue_tiers_the_lane_it_hands_back(action, tier):
    assert _runner()._pool_queue("/pool/disk.qcow2", action) == f"storage.p-dst.{tier}"


def test_pool_queue_will_not_build_an_untiered_lane():
    """The action is not optional: the signature is the guard.

    A caller that forgets it is the exact defect this fixes, so it must fail
    loudly here rather than quietly produce ``storage.<pool>.default`` again.
    """
    with pytest.raises(TypeError):
        _runner()._pool_queue("/pool/disk.qcow2")
