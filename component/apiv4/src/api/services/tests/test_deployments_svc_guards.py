# SPDX-License-Identifier: AGPL-3.0-or-later

"""Membership / state guards of ``DeploymentService`` (services/deployments.py).

* ``stop_user_desktops`` -- unknown deployment -> not_found; a user_id not in an
  explicit ``allowed.users`` list -> forbidden (blocks probing arbitrary users);
  a member with no desktops -> not_found; a member with desktops is stopped.
* ``toggle_domain_visibility`` -- unknown domain -> not_found; a desktop with no
  deployment tag -> bad_request/not_in_deployment; a tagged one toggles.

The real method decides; only the models / Common layer / DesktopEvents are
stubbed. Asserts ``Error`` type / ``description_code``.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from api.services.deployments import DeploymentService
from api.services.error import Error


class TestStopUserDesktops:
    def test_unknown_deployment_not_found(self):
        with patch("api.services.deployments.Caches.get_document", return_value=None):
            with pytest.raises(Error) as exc:
                DeploymentService.stop_user_desktops("gone", "u1")
        assert exc.value.error["error"] == "not_found"

    def test_non_member_forbidden(self):
        dep = {"allowed": {"users": ["alice", "bob"]}}
        with patch("api.services.deployments.Caches.get_document", return_value=dep):
            with pytest.raises(Error) as exc:
                DeploymentService.stop_user_desktops("dep1", "intruder")
        assert exc.value.error["description_code"] == "not_enough_rights"

    def test_member_without_desktops_not_found(self):
        dep = {"allowed": {"users": ["alice"]}}
        with (
            patch("api.services.deployments.Caches.get_document", return_value=dep),
            patch(
                "api.services.deployments.CommonDeploymentDesktops.get_user_desktop_ids",
                return_value=[],
            ),
        ):
            with pytest.raises(Error) as exc:
                DeploymentService.stop_user_desktops("dep1", "alice")
        assert exc.value.error["error"] == "not_found"

    def test_member_with_desktops_is_stopped(self):
        dep = {"allowed": {"users": ["alice"]}}
        with (
            patch("api.services.deployments.Caches.get_document", return_value=dep),
            patch(
                "api.services.deployments.CommonDeploymentDesktops.get_user_desktop_ids",
                return_value=["d1", "d2"],
            ),
            patch("api.services.deployments.DesktopEvents.desktops_stop") as stop,
        ):
            DeploymentService.stop_user_desktops("dep1", "alice")
        stop.assert_called_once_with(["d1", "d2"])


class TestToggleDomainVisibility:
    @patch("api.services.deployments.RethinkDomain.exists", return_value=False)
    def test_unknown_domain_not_found(self, _exists):
        with pytest.raises(Error) as exc:
            DeploymentService.toggle_domain_visibility("ghost")
        assert exc.value.error["error"] == "not_found"

    def test_untagged_desktop_bad_request(self):
        toggle = MagicMock(name="toggle_user_visible")
        inst = SimpleNamespace(tag=None, toggle_user_visible=toggle)
        with (
            patch("api.services.deployments.RethinkDomain.exists", return_value=True),
            patch("api.services.deployments.RethinkDomain", return_value=inst) as D,
        ):
            D.exists.return_value = True
            with pytest.raises(Error) as exc:
                DeploymentService.toggle_domain_visibility("d1")
        assert exc.value.error["description_code"] == "not_in_deployment"
        toggle.assert_not_called()

    def test_tagged_desktop_toggles(self):
        toggle = MagicMock(name="toggle_user_visible")
        inst = SimpleNamespace(tag="dep1", toggle_user_visible=toggle)
        with patch("api.services.deployments.RethinkDomain", return_value=inst) as D:
            D.exists.return_value = True
            DeploymentService.toggle_domain_visibility("d1")
        toggle.assert_called_once()
