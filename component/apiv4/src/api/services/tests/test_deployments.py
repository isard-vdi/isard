# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for DeploymentService — façade over CommonDeployments,
DesktopEvents, and RethinkDeployment. Tests pin the not-found
dispatch + the merged owned/co-owned listing.
"""

from unittest.mock import patch

import pytest
from api.services.deployments import DeploymentService
from api.services.error import Error

JWT_PAYLOAD = {
    "user_id": "u1",
    "category_id": "default",
    "group_id": "default-default",
    "role_id": "advanced",
}


class TestGetOwnedDeployments:
    @patch(
        "api.services.deployments.CommonDeployments.get_co_owned_deployments",
        return_value=[{"id": "d2"}],
    )
    @patch(
        "api.services.deployments.CommonDeployments.get_owned_deployments",
        return_value=[{"id": "d1"}],
    )
    def test_concatenates_owned_and_co_owned(self, _owned, _co_owned):
        result = DeploymentService.get_owned_deployments(JWT_PAYLOAD)
        # owned first, then co-owned (order documented by service)
        assert [d["id"] for d in result] == ["d1", "d2"]


class TestGetDeployment:
    @patch(
        "api.services.deployments.CommonDeploymentUsers.get_users_info",
        return_value=[{"id": "u1"}, {"id": "u2"}],
    )
    @patch(
        "api.services.deployments.CommonDeployments.retrieve_deployment",
        return_value={"id": "d1", "create_dict": [1, 2]},
    )
    @patch("api.services.deployments.RethinkDeployment.exists", return_value=True)
    def test_computes_totals(self, _exists, _retrieve, _users):
        result = DeploymentService.get_deployment("d1")
        info = result["info"]
        assert info["total_users"] == 2
        assert info["desktops_each_user"] == 2
        assert info["total_desktops"] == 4  # len(create_dict) * total_users

    @patch("api.services.deployments.RethinkDeployment.exists", return_value=False)
    def test_raises_not_found(self, _exists):
        with pytest.raises(Error):
            DeploymentService.get_deployment("ghost")


class TestDeleteDeployment:
    @patch(
        "api.services.deployments.DesktopEvents.deployment_delete",
        return_value="task-1",
    )
    def test_forwards_id_user_and_permanent(self, mock_delete):
        result = DeploymentService.delete_deployment("d1", user_id="u1", permanent=True)
        mock_delete.assert_called_once_with(
            deployment_id="d1", agent_id="u1", permanent=True
        )
        assert result == "task-1"


class TestCreateDeployment:
    @patch(
        "api.services.deployments.CommonDeployments.create",
        return_value="d-new",
    )
    def test_forwards_required_fields_and_defaults(self, mock_create):
        data = {
            "name": "Lab",
            "allowed": {"groups": ["g1"]},
            "desktops": [{"id": "tpl1"}],
        }
        result = DeploymentService.create_deployment(data, JWT_PAYLOAD)
        kwargs = mock_create.call_args.kwargs
        assert result == "d-new"
        assert kwargs["name"] == "Lab"
        assert kwargs["selected"] == {"groups": ["g1"]}
        # Optional fields default
        assert kwargs["co_owners"] == []
        assert kwargs["visible"] is False
        assert kwargs["create_owner_desktop"] is True


class TestToggleVisibility:
    @patch("api.services.deployments.RethinkDeployment")
    @patch("api.services.deployments.RethinkDeployment.exists", return_value=True)
    def test_flips_tag_visible(self, _exists, mock_d):
        instance = mock_d.return_value
        instance.tag_visible = False
        DeploymentService.toggle_visibility("d1")
        assert instance.tag_visible is True

    @patch("api.services.deployments.RethinkDeployment.exists", return_value=False)
    def test_raises_not_found(self, _exists):
        with pytest.raises(Error):
            DeploymentService.toggle_visibility("ghost")
