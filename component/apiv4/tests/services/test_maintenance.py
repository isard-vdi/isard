# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for MaintenanceService — thin delegate over
isardvdi_common.helpers.maintenance.Maintenance. Tests pin the
contract: which static method forwards to which Maintenance attribute
or method, with which arguments.
"""

from unittest.mock import MagicMock, patch

from api.services.maintenance import MaintenanceService


class TestIsEnabled:
    @patch("api.services.maintenance.Maintenance")
    def test_returns_enabled_flag_true(self, mock_m):
        mock_m.enabled = True
        assert MaintenanceService.is_enabled() is True

    @patch("api.services.maintenance.Maintenance")
    def test_returns_enabled_flag_false(self, mock_m):
        mock_m.enabled = False
        assert MaintenanceService.is_enabled() is False


class TestCategoryStatus:
    @patch("api.services.maintenance.Maintenance.category_enabled", return_value=True)
    def test_delegates_category_id(self, mock_cat):
        assert MaintenanceService.get_category_status("default") is True
        mock_cat.assert_called_once_with("default")

    @patch("api.services.maintenance.Maintenance.category_enabled", return_value=False)
    def test_returns_false_for_non_maintenance_category(self, mock_cat):
        assert MaintenanceService.get_category_status("other") is False


class TestSetEnabled:
    @patch("api.services.maintenance.Maintenance")
    def test_sets_enabled_true(self, mock_m):
        MaintenanceService.set_enabled(True)
        assert mock_m.enabled is True

    @patch("api.services.maintenance.Maintenance")
    def test_sets_enabled_false(self, mock_m):
        MaintenanceService.set_enabled(False)
        assert mock_m.enabled is False


class TestUpdateText:
    @patch("api.services.maintenance.Maintenance.update_text")
    def test_serializes_pydantic_model_to_dict(self, mock_update):
        # The service calls text.model_dump(mode="json") before forwarding.
        fake_text = MagicMock()
        fake_text.model_dump.return_value = {"title": "Down", "body": "later"}
        MaintenanceService.update_text(fake_text)
        fake_text.model_dump.assert_called_once_with(mode="json")
        mock_update.assert_called_once_with({"title": "Down", "body": "later"})


class TestGetText:
    @patch(
        "api.services.maintenance.Maintenance.get_text",
        return_value="We'll be back soon",
    )
    def test_returns_helper_output_verbatim(self, mock_get):
        assert MaintenanceService.get_text() == "We'll be back soon"
        mock_get.assert_called_once_with()
