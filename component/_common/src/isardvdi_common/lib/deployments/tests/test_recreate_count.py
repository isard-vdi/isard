#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression tests for the recreate desktop count shown before confirming."""

from unittest.mock import patch

from isardvdi_common.lib.deployments import deployments as mod

PAYLOAD = {"user_id": "u1", "role_id": "admin", "category_id": "default"}


def _plan(*user_lists):
    return [
        ({"tag": "d1"}, {"name": f"r{i}"}, users) for i, users in enumerate(user_lists)
    ]


def test_counts_only_the_users_the_plan_would_create_for():
    # The plan already dropped disabled users and those owning the desktop.
    with patch.object(
        mod.DeploymentsProcessed,
        "_prepare_recreate",
        return_value=(
            {"id": "d1"},
            _plan([{"id": "u2"}, {"id": "u3"}], [{"id": "u2"}]),
        ),
    ):
        assert mod.DeploymentsProcessed.count_recreate_desktops(PAYLOAD, "d1") == 3


def test_counts_zero_when_nothing_is_missing():
    with patch.object(
        mod.DeploymentsProcessed,
        "_prepare_recreate",
        return_value=({"id": "d1"}, _plan([], [])),
    ):
        assert mod.DeploymentsProcessed.count_recreate_desktops(PAYLOAD, "d1") == 0
