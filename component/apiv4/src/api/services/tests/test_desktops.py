# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for DesktopService — partial coverage of the highest-traffic
service in apiv4. Tests focus on dispatcher/forward methods that are
safe to mock; full creation-flow tests would require a live MockThink
DB and live up to the routes/tests/ layer.
"""

from unittest.mock import patch

import pytest
from api.services.desktops import DesktopService
from api.services.error import Error

JWT_PAYLOAD = {
    "user_id": "u1",
    "category_id": "default",
    "group_id": "default-default",
    "role_id": "user",
}


class TestGetUserAllowedReservables:
    """The picker must list exactly what creation accepts."""

    @patch(
        "api.services.desktops.Quotas.get_hardware_kind_allowed",
        return_value={"reservables": {"vgpus": [{"id": "vgpu-1", "name": "T4"}]}},
    )
    def test_uses_the_same_source_as_creation(self, mock_quotas):
        vgpus = DesktopService.get_user_allowed_reservables(JWT_PAYLOAD)

        mock_quotas.assert_called_once_with(JWT_PAYLOAD, "reservables")
        assert vgpus == [{"id": "vgpu-1", "name": "T4"}]


class TestCreateDesktopGuards:
    @patch("api.services.desktops.RethinkUser.exists", return_value=False)
    def test_raises_not_found_for_unknown_user(self, _exists):
        # Build a minimal stand-in for the request body — only the
        # template_id field is touched before the user-existence guard
        # kicks in.
        from types import SimpleNamespace

        data = SimpleNamespace(
            template_id="t1",
            name="d1",
            description="",
            persistent=True,
            hardware=None,
            guest_properties=None,
            reservables=None,
            image=None,
            bastion_target=None,
        )
        with pytest.raises(Error):
            DesktopService.create_desktop("ghost", data)


class TestCreateDesktopQuotas:
    """``desktop_create``'s used counter only includes persistent desktops, so
    gating a temporal one with it would never bound it."""

    def _data(self, persistent):
        from types import SimpleNamespace

        return SimpleNamespace(
            template_id="t1",
            name="d1",
            description="",
            persistent=persistent,
            hardware=None,
            guest_properties=None,
            reservables=None,
            image=None,
            bastion_target=None,
        )

    @patch(
        "api.services.desktops.CommonDesktopsNonpersistent.new_desktop",
        return_value="np-1",
    )
    @patch("api.services.desktops.Helpers.check_user_duplicated_domain_name")
    @patch("api.services.desktops.Alloweds.is_allowed", return_value=True)
    @patch("api.services.desktops.Helpers.gen_payload_from_user", return_value={})
    @patch("api.services.desktops.CommonTemplates.check_template_status")
    @patch("api.services.desktops.CommonTemplates.get_template", return_value={})
    @patch("api.services.desktops.Quotas")
    @patch("api.services.desktops.RethinkUser.exists", return_value=True)
    def test_nonpersistent_checks_volatile_quota(self, _exists, quotas, *_mocks, **__):
        desktop_id = DesktopService.create_desktop("u1", self._data(persistent=False))

        assert desktop_id == "np-1"
        quotas.volatile_create.assert_called_once_with("u1")
        quotas.desktop_start.assert_called_once_with("u1", "t1")
        quotas.desktop_create.assert_not_called()

    @patch(
        "api.services.desktops.CommonDesktops.new_from_template",
        return_value={"id": "p-1"},
    )
    @patch("api.services.desktops.Helpers.check_user_duplicated_domain_name")
    @patch("api.services.desktops.Alloweds.is_allowed", return_value=True)
    @patch("api.services.desktops.Helpers.gen_payload_from_user", return_value={})
    @patch("api.services.desktops.CommonTemplates.check_template_status")
    @patch("api.services.desktops.CommonTemplates.get_template", return_value={})
    @patch("api.services.desktops.Quotas")
    @patch("api.services.desktops.RethinkUser.exists", return_value=True)
    def test_persistent_checks_desktop_quota(self, _exists, quotas, *_mocks, **__):
        desktop_id = DesktopService.create_desktop("u1", self._data(persistent=True))

        assert desktop_id == "p-1"
        quotas.desktop_create.assert_called_once_with("u1")
        quotas.volatile_create.assert_not_called()


class TestCreateNonpersistentDesktop:
    @patch("api.services.desktops.RethinkUser.exists", return_value=False)
    def test_raises_not_found_for_unknown_user(self, _exists):
        with pytest.raises(Error):
            DesktopService.create_nonpersistent_desktop({"user_id": "ghost"}, "t1")
