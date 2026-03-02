#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Editing a deployment's alloweds must not create desktops twice.

Desktop creation is fire-and-forget, so a second ``recreate`` right after the
first still sees the new users without desktops and creates them again.
``edit_deployment_data`` therefore leaves creating them to its caller, which
runs a single ``recreate`` once the whole edit is applied, while the alloweds
route keeps creating them straight away.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.lib.deployments import deployment_users as users_mod
from isardvdi_common.lib.deployments import deployments as mod

DP = mod.DeploymentsProcessed
DU = users_mod.DeploymentUsers

ALLOWED = {"users": ["u-1", "u-2"], "groups": False}


@pytest.fixture
def recreate(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(DP, "recreate", mock)
    return mock


class TestEditDeploymentDataAlloweds:
    @pytest.fixture(autouse=True)
    def _deployment(self, monkeypatch):
        monkeypatch.setattr(
            mod.Caches,
            "get_document",
            classmethod(lambda cls, *a, **k: {"id": "dep-1"}),
        )
        monkeypatch.setattr(mod.Caches, "invalidate_cache", MagicMock())
        monkeypatch.setattr(DP, "_rdb_context", MagicMock())
        monkeypatch.setattr(mod, "r", MagicMock())

    def test_saves_alloweds_without_creating_desktops(self, monkeypatch, recreate):
        edit_users = MagicMock()
        monkeypatch.setattr(mod.DeploymentUsers, "edit_deployment_users", edit_users)

        DP.edit_deployment_data({"user_id": "owner"}, "dep-1", {"allowed": ALLOWED})

        edit_users.assert_called_once_with(
            payload={"user_id": "owner"},
            deployment_id="dep-1",
            allowed=ALLOWED,
            recreate=False,
        )
        recreate.assert_not_called()


class TestEditDeploymentUsersRecreate:
    @pytest.fixture(autouse=True)
    def _deployment(self, monkeypatch):
        monkeypatch.setattr(
            users_mod.Caches,
            "get_document",
            classmethod(lambda cls, *a, **k: {"id": "dep-1"}),
        )
        monkeypatch.setattr(users_mod.Caches, "invalidate_cache", MagicMock())
        monkeypatch.setattr(DU, "_rdb_context", MagicMock())
        rdb = MagicMock()
        rdb.table.return_value.get.return_value.run.return_value = {
            "id": "dep-1",
            "allowed": {"users": ["u-1"], "groups": False},
        }
        # No desktops of removed users to delete
        domains = rdb.table.return_value.get_all.return_value
        domains.pluck.return_value.__getitem__.return_value.run.return_value = []
        monkeypatch.setattr(users_mod, "r", rdb)
        monkeypatch.setattr(DP, "_parse_booking", MagicMock(return_value={}))
        monkeypatch.setattr(DU, "get_selected_users", MagicMock(return_value=[]))

    def test_creates_missing_desktops_by_default(self, recreate):
        DU.edit_deployment_users({"user_id": "owner"}, "dep-1", ALLOWED)
        recreate.assert_called_once_with({"user_id": "owner"}, "dep-1")

    def test_leaves_creating_them_to_the_caller(self, recreate):
        DU.edit_deployment_users({"user_id": "owner"}, "dep-1", ALLOWED, recreate=False)
        recreate.assert_not_called()
