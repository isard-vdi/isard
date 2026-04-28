# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_backups.py``."""

import pytest
from api.schemas.admin_backups import BackupIntegritySetRequest, BackupReportRequest
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


class TestBackupIntegritySetRequest:
    """The PUT /admin/backups/integrity body. The service-layer
    ``set_integrity_enabled`` rejects non-bool to avoid
    ``bool("false") == True`` foot-guns; the schema is the first line
    of defence — pin both ends."""

    def test_accepts_true(self):
        assert (
            BackupIntegritySetRequest(integrity_enabled=True).integrity_enabled is True
        )

    def test_accepts_false(self):
        assert (
            BackupIntegritySetRequest(integrity_enabled=False).integrity_enabled
            is False
        )

    def test_missing_field_rejected(self):
        with pytest.raises(ValidationError):
            BackupIntegritySetRequest()

    def test_round_trip(self):
        r = BackupIntegritySetRequest(integrity_enabled=True)
        assert BackupIntegritySetRequest(**r.model_dump()) == r

    def test_string_true_coerced(self):
        """Pydantic v2 default mode coerces ``'true'`` → ``True``. The
        service layer rejects this anyway, but pin so a future strict-mode
        flip is noticed (and doesn't quietly start sending 422s)."""
        r = BackupIntegritySetRequest(integrity_enabled="true")
        assert r.integrity_enabled is True

    def test_arbitrary_string_rejected(self):
        with pytest.raises(ValidationError):
            BackupIntegritySetRequest(integrity_enabled="enabled")
