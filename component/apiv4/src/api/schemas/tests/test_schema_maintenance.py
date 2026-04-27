# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/maintenance.py``."""

import pytest
from api.schemas.maintenance import (
    MaintenanceStatusResponse,
    MaintenanceStatusUpdate,
    MaintenanceTextGetResponse,
    MaintenanceTextResponse,
    MaintenanceTextUpdate,
)
from pydantic import ValidationError


class TestMaintenanceStatusResponse:
    def test_default_disabled(self):
        """Default enabled=False — pin so the maintenance probe never
        accidentally returns True without an explicit flag."""
        m = MaintenanceStatusResponse()
        assert m.enabled is False

    def test_accepts_true(self):
        assert MaintenanceStatusResponse(enabled=True).enabled is True


class TestMaintenanceTextResponse:
    def test_default_enabled_true(self):
        """Asymmetry with MaintenanceStatusResponse: this defaults
        enabled=True (custom maintenance text IS configured by default
        on a fresh install). Pin the asymmetry."""
        m = MaintenanceTextResponse()
        assert m.enabled is True
        assert m.title is None
        assert m.body is None

    def test_full(self):
        m = MaintenanceTextResponse(
            enabled=True, title="Maintenance", body="Down for upgrades"
        )
        assert m.title == "Maintenance"


class TestMaintenanceStatusUpdate:
    def test_default_disabled(self):
        m = MaintenanceStatusUpdate()
        assert m.enabled is False


class TestMaintenanceTextGetResponse:
    def test_text_required(self):
        with pytest.raises(ValidationError):
            MaintenanceTextGetResponse()

    def test_accepts_dict(self):
        r = MaintenanceTextGetResponse(text={"en": {"title": "x"}})
        assert r.text == {"en": {"title": "x"}}


class TestMaintenanceTextUpdate:
    def test_accepts_empty(self):
        m = MaintenanceTextUpdate()
        assert m.title is None
        assert m.body is None

    def test_partial_update(self):
        m = MaintenanceTextUpdate(title="Hi")
        dump = m.model_dump(exclude_none=True)
        assert dump == {"title": "Hi"}
