# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_operations.py``."""

import pytest
from api.schemas.admin_operations import OperationsHypervisorResponse
from pydantic import ValidationError


class TestOperationsHypervisorResponse:
    _required = {"id": "h-1", "state": "ON"}

    def test_accepts_required(self):
        r = OperationsHypervisorResponse(**self._required)
        assert r.id == "h-1"
        assert r.state == "ON"

    @pytest.mark.parametrize("missing", ["id", "state"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            OperationsHypervisorResponse(**payload)

    def test_optional_fields_default_none(self):
        r = OperationsHypervisorResponse(**self._required)
        for field in (
            "isard_state",
            "orchestrator_managed",
            "only_forced",
            "buffering_hyper",
            "destroy_time",
            "gpu_only",
            "desktops_started",
            "cpu",
            "ram",
            "capabilities",
            "gpus",
            "destroy_allowed",
        ):
            assert getattr(r, field) is None

    def test_capabilities_and_gpus_string_lists(self):
        r = OperationsHypervisorResponse(
            **self._required,
            capabilities=["nested", "tcg"],
            gpus=["nvidia-1", "nvidia-2"],
        )
        assert r.capabilities == ["nested", "tcg"]
        assert r.gpus == ["nvidia-1", "nvidia-2"]
