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
        # selected must carry all four allowed buckets so CommonDeployments
        # can index them directly; unset buckets default to False.
        assert kwargs["selected"] == {
            "groups": ["g1"],
            "users": False,
            "categories": False,
            "roles": False,
        }
        # Optional fields default
        assert kwargs["co_owners"] == []
        assert kwargs["visible"] is False
        assert kwargs["create_owner_desktop"] is True


class TestToggleVisibility:
    @patch("api.services.deployments.RethinkDeployment")
    @patch("api.services.deployments.RethinkDeployment.exists", return_value=True)
    def test_flips_tag_visible(self, _exists, mock_d):
        # The service now delegates to model.toggle_visible(stop_started_domains),
        # which cascades the new value to every tagged desktop instead of just
        # flipping the row's tag_visible.
        instance = mock_d.return_value
        DeploymentService.toggle_visibility("d1")
        instance.toggle_visible.assert_called_once_with(True)

    @patch("api.services.deployments.RethinkDeployment")
    @patch("api.services.deployments.RethinkDeployment.exists", return_value=True)
    def test_passes_stop_started_domains_through(self, _exists, mock_d):
        instance = mock_d.return_value
        DeploymentService.toggle_visibility("d1", stop_started_domains=False)
        instance.toggle_visible.assert_called_once_with(False)

    @patch("api.services.deployments.RethinkDeployment.exists", return_value=False)
    def test_raises_not_found(self, _exists):
        with pytest.raises(Error):
            DeploymentService.toggle_visibility("ghost")


class TestGetDeploymentBastion:
    @patch(
        "api.services.deployments.Caches.get_document",
        return_value={"bastion": {"ssh": {"enabled": True, "port": 22}}},
    )
    @patch("api.services.deployments.RethinkDeployment.exists", return_value=True)
    def test_returns_stored_config(self, _exists, _cache):
        result = DeploymentService.get_deployment_bastion("d1")
        assert result["ssh"]["enabled"] is True

    @patch("api.services.deployments.Caches.get_document", return_value={})
    @patch("api.services.deployments.RethinkDeployment.exists", return_value=True)
    def test_returns_defaults_when_unset(self, _exists, _cache):
        result = DeploymentService.get_deployment_bastion("d1")
        assert result == DeploymentService._default_bastion_config()

    @patch("api.services.deployments.RethinkDeployment.exists", return_value=False)
    def test_raises_not_found(self, _exists):
        with pytest.raises(Error):
            DeploymentService.get_deployment_bastion("ghost")


class TestSetDeploymentBastion:
    @patch("api.services.deployments.BastionService.apply_bastion_config")
    @patch(
        "api.services.deployments.CommonDeploymentDesktops.get_desktop_ids",
        return_value=["desk-1", "desk-2"],
    )
    @patch("api.services.deployments.Caches.invalidate_cache")
    @patch("api.services.deployments.RethinkDeployment.update_document")
    @patch("api.services.deployments.RethinkDeployment.exists", return_value=True)
    def test_persists_and_applies_to_each_desktop(
        self, _exists, mock_update, _inval, _ids, mock_apply
    ):
        config = {
            "ssh": {"enabled": True, "port": 22},
            "http": {"enabled": False, "http_port": 80, "https_port": 443},
        }
        result = DeploymentService.set_deployment_bastion("d1", config)
        # persisted on the deployment doc
        assert mock_update.call_args[0][0] == "d1"
        assert mock_update.call_args[0][1]["bastion"]["ssh"]["enabled"] is True
        # applied to every desktop
        assert mock_apply.call_count == 2
        assert result["ssh"]["enabled"] is True

    @patch("api.services.deployments.RethinkDeployment.exists", return_value=False)
    def test_raises_not_found(self, _exists):
        with pytest.raises(Error):
            DeploymentService.set_deployment_bastion("ghost", {})


class TestGetDeploymentDesktopBastion:
    @patch(
        "api.services.deployments.BastionService.get_desktop_bastion_active",
        return_value={"exists": True, "ssh": {"enabled": True, "port": 22}},
    )
    @patch("api.services.deployments.Caches.get_document", return_value="d1")
    @patch("api.services.deployments.RethinkDeployment.exists", return_value=True)
    def test_returns_status_for_member_desktop(self, _exists, _tag, _active):
        result = DeploymentService.get_deployment_desktop_bastion("d1", "desk-1")
        assert result["exists"] is True

    @patch("api.services.deployments.Caches.get_document", return_value="other-dep")
    @patch("api.services.deployments.RethinkDeployment.exists", return_value=True)
    def test_rejects_desktop_not_in_deployment(self, _exists, _tag):
        with pytest.raises(Error):
            DeploymentService.get_deployment_desktop_bastion("d1", "desk-x")


class TestBastionCsv:
    @patch(
        "api.services.deployments.BastionService.get_admin_bastion_config",
        return_value={"bastion_domain": "bastion.example", "bastion_ssh_port": "443"},
    )
    @patch("api.services.deployments.Targets.get_domain_target")
    @patch("api.services.deployments.Caches.get_document")
    @patch(
        "api.services.deployments.CommonDeploymentDesktops.get_desktop_ids",
        return_value=["desk-1"],
    )
    @patch("api.services.deployments.RethinkDeployment.exists", return_value=True)
    def test_emits_header_and_row(self, _exists, _ids, mock_cache, mock_target, _cfg):
        def cache_side_effect(table, item_id, *args, **kwargs):
            if table == "domains":
                return {"user": "u1", "name": "Desk One", "status": "Started"}
            if table == "users":
                return {"username": "alice", "email": "a@example.com"}
            return None

        mock_cache.side_effect = cache_side_effect
        mock_target.return_value = {
            "id": "aaaa-bbbb",
            "ssh": {"enabled": True, "port": 22},
            "http": {"enabled": False, "http_port": 80, "https_port": 443},
            "domains": [],
        }
        csv_text = DeploymentService.bastion_csv("d1")
        lines = csv_text.strip().split("\n")
        assert lines[0].startswith("username,email,desktop_name")
        assert "alice" in lines[1]
        assert "ssh aaaa-bbbb@bastion.example" in lines[1]

    @patch("api.services.deployments.RethinkDeployment.exists", return_value=False)
    def test_raises_not_found(self, _exists):
        with pytest.raises(Error):
            DeploymentService.bastion_csv("ghost")
