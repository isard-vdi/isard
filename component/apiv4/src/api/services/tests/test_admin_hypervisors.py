# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for AdminHypervisorsService — façade over HypervisorsProcessed.
Tests pin the status-filter validation and a few delegate methods.
"""

from unittest.mock import patch

import pytest
from api.services.admin.hypervisors import AdminHypervisorsService
from api.services.error import Error


class TestGetHypervisors:
    @patch(
        "api.services.admin.hypervisors.HypervisorsProcessed.get_hypervisors",
        return_value=[{"id": "h1", "status": "Online"}],
    )
    def test_returns_listing_when_no_filter(self, mock_get):
        result = AdminHypervisorsService.get_hypervisors()
        mock_get.assert_called_once_with(None)
        assert result[0]["id"] == "h1"

    @patch(
        "api.services.admin.hypervisors.HypervisorsProcessed.get_hypervisors",
        return_value=[],
    )
    @pytest.mark.parametrize("status", ["Online", "Offline", "Error"])
    def test_accepts_valid_status_filter(self, mock_get, status):
        AdminHypervisorsService.get_hypervisors(status)
        mock_get.assert_called_once_with(status)

    @pytest.mark.parametrize("bad", ["online", "Foo", "starting", ""])
    def test_rejects_invalid_status_filter(self, bad):
        # Empty string is falsy → no filter validation, falls through to dispatch.
        # Test only the truthy bad cases here.
        if not bad:
            return
        with pytest.raises(Error):
            AdminHypervisorsService.get_hypervisors(bad)


class TestGetHyperStatus:
    @patch(
        "api.services.admin.hypervisors.HypervisorsProcessed.get_hyper_status",
        return_value={"status": "Online", "only_forced": False},
    )
    def test_passes_id_through(self, mock_get):
        result = AdminHypervisorsService.get_hyper_status("h1")
        mock_get.assert_called_once_with("h1")
        assert result["status"] == "Online"


class TestEnableHyper:
    @patch(
        "api.services.admin.hypervisors.HypervisorsProcessed.enable_hyper",
        return_value={"status": True, "data": {"id": "h1", "enabled": True}},
    )
    def test_enable_default_true(self, mock_enable):
        # enable_hyper signature: (hyper_id, enable=True). Returns data dict
        # on success, raises bad_request Error when status is False.
        result = AdminHypervisorsService.enable_hyper("h1")
        mock_enable.assert_called_once_with("h1", True)
        assert result == {"id": "h1", "enabled": True}

    @patch(
        "api.services.admin.hypervisors.HypervisorsProcessed.enable_hyper",
        return_value={"status": True, "data": {"id": "h1", "enabled": False}},
    )
    def test_enable_explicit_false(self, mock_enable):
        AdminHypervisorsService.enable_hyper("h1", enable=False)
        mock_enable.assert_called_once_with("h1", False)

    @patch(
        "api.services.admin.hypervisors.HypervisorsProcessed.enable_hyper",
        return_value={"status": False, "msg": "no such hyper"},
    )
    def test_failed_status_raises_typed_error(self, _mock_enable):
        with pytest.raises(Error):
            AdminHypervisorsService.enable_hyper("ghost")


class TestRemoveHyper:
    @patch(
        "api.services.admin.hypervisors.HypervisorsProcessed.remove_hyper",
        return_value={"status": True, "data": {"id": "h1"}},
    )
    def test_passes_id_through(self, mock_remove):
        AdminHypervisorsService.remove_hyper("h1")
        mock_remove.assert_called_once_with("h1")

    @patch(
        "api.services.admin.hypervisors.HypervisorsProcessed.remove_hyper",
        return_value={"status": False, "msg": "in use"},
    )
    def test_failed_status_raises_typed_error(self, _mock_remove):
        with pytest.raises(Error):
            AdminHypervisorsService.remove_hyper("h1")


class TestNormalizeGpuModel:
    """Lock the apiv4 mirror of ``normalize_gpu_model`` against drift.

    The model is embedded verbatim in a URL path segment (the
    BRAND-MODEL-PROFILE reservable id), so the output must be space-,
    dash- AND slash-free. Stays in lockstep with
    ``docker/hypervisor/src/lib/gpu_discovery.py::normalize_gpu_model``
    and ``isardvdi_common.lib.hypervisors.hypervisors.
    HypervisorsProcessed._normalize_gpu_model``.
    """

    @pytest.mark.parametrize(
        "gpu_name, expected",
        [
            ("NVIDIA A16", "A16"),
            ("NVIDIA RTX A6000", "RTXA6000"),
            ("NVIDIA GA107GL [A2 / A16]", "GA107GL[A2A16]"),
            ("GA107GL[A2/A16]", "GA107GL[A2A16]"),
        ],
    )
    def test_name_path_is_clean(self, gpu_name, expected):
        result = AdminHypervisorsService._normalize_gpu_model(gpu_name)
        assert result == expected
        assert "/" not in result
        assert "-" not in result
        assert " " not in result

    @pytest.mark.parametrize(
        "profile_name, expected",
        [
            ("A16-2Q", "A16"),
            ("A100-1-5C", "A100"),
            ("GA107GL[A2/A16]-2Q", "GA107GL[A2A16]"),
        ],
    )
    def test_profile_path_is_clean(self, profile_name, expected):
        result = AdminHypervisorsService._normalize_gpu_model(
            "irrelevant", vgpu_profiles=[{"name": profile_name}]
        )
        assert result == expected
        assert "/" not in result
