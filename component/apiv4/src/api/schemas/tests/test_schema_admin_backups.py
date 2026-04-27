# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_backups.py``."""

import pytest
from api.schemas.admin_backups import BackupReportRequest
from pydantic import ValidationError


class TestBackupReportRequest:
    """The backupninja submission schema. The route's exception handler
    classifies any non-Error exception as ``bad_request`` (NOT
    ``internal_server``) precisely because external systems post here —
    keep validation tight enough to surface real problems early."""

    _required = {
        "timestamp": "2026-04-27T12:00:00",
        "status": "ok",
        "type": "automated",
        "scope": "full",
    }

    def test_accepts_required(self):
        r = BackupReportRequest(**self._required)
        assert r.status == "ok"
        assert r.type == "automated"
        assert r.scope == "full"
        assert r.details is None
        assert r.created_at is None

    @pytest.mark.parametrize("missing", ["timestamp", "status", "type", "scope"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            BackupReportRequest(**payload)

    def test_timestamp_accepts_any(self):
        """timestamp is typed Any — pin so the wide net stays. backupninja
        sends a unix int sometimes, an ISO string others."""
        assert (
            BackupReportRequest(**{**self._required, "timestamp": 1234567890}).timestamp
            == 1234567890
        )
        assert BackupReportRequest(
            **{**self._required, "timestamp": {"epoch": 1}}
        ).timestamp == {"epoch": 1}

    def test_details_optional_dict(self):
        r = BackupReportRequest(
            **self._required,
            details={"checks": [], "warnings": [], "time_breakdown": {"db": 12.3}},
        )
        assert r.details["time_breakdown"]["db"] == 12.3

    def test_round_trip(self):
        r = BackupReportRequest(**self._required, details={"x": 1})
        assert BackupReportRequest(**r.model_dump()) == r
