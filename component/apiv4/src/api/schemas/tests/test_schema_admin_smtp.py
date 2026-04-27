# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_smtp.py``."""

import pytest
from api.schemas.admin_smtp import SmtpConfigRequest, SmtpTestResponse
from pydantic import ValidationError


class TestSmtpConfigRequest:
    """All fields Optional — used for partial updates AND the test-connection
    body. The route does NOT validate that host/port/username/password are
    set together; that's the service's job.
    """

    def test_accepts_empty(self):
        r = SmtpConfigRequest()
        assert r.host is None
        assert r.port is None

    def test_accepts_partial(self):
        r = SmtpConfigRequest(enabled=False)
        assert r.enabled is False

    def test_accepts_full(self):
        r = SmtpConfigRequest(
            host="smtp.example.com",
            port=587,
            username="isardvdi",
            password="secret",
            enabled=True,
        )
        assert r.port == 587
        assert r.password == "secret"

    def test_port_string_int_coerced(self):
        """Pydantic v2 default coerces "587" to 587 — pin the current
        behavior so a strict-mode flip is noticed."""
        r = SmtpConfigRequest(port="587")
        assert r.port == 587

    def test_port_non_int_rejected(self):
        with pytest.raises(ValidationError):
            SmtpConfigRequest(port="not-a-number")

    def test_round_trip(self):
        r = SmtpConfigRequest(host="x", port=25)
        assert SmtpConfigRequest(**r.model_dump()) == r

    def test_exclude_none_drops_unset_fields(self):
        """The smtp PUT route uses model_dump(exclude_none=True) to feed
        the service. Pin that unset fields are dropped so the service's
        partial-update contract holds."""
        r = SmtpConfigRequest(enabled=True)
        dump = r.model_dump(exclude_none=True)
        assert dump == {"enabled": True}


class TestSmtpTestResponse:
    def test_result_required(self):
        with pytest.raises(ValidationError):
            SmtpTestResponse()

    def test_success_no_error(self):
        r = SmtpTestResponse(result=True)
        assert r.result is True
        assert r.error is None

    def test_failure_with_error(self):
        r = SmtpTestResponse(result=False, error="auth failed")
        assert r.result is False
        assert r.error == "auth failed"

    def test_round_trip(self):
        r = SmtpTestResponse(result=False, error="x")
        assert SmtpTestResponse(**r.model_dump()) == r
