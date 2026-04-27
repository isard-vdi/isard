# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/open.py``."""

import pytest
from api.schemas.open import ApiVersion
from pydantic import ValidationError


class TestApiVersion:
    """Public unauth endpoint — pin so a future schema tightening that
    breaks the version-probe handshake (used by the frontend's startup
    code path) is intentional."""

    _required = {
        "name": "isardvdi",
        "api_version": "v4",
        "isardvdi_version": "3.4.0",
    }

    def test_accepts_required(self):
        v = ApiVersion(**self._required, usage="production")
        assert v.api_version == "v4"
        assert v.usage == "production"

    def test_usage_optional(self):
        """usage: Optional[str] — production endpoints sometimes omit it."""
        v = ApiVersion(**self._required, usage=None)
        assert v.usage is None

    @pytest.mark.parametrize("missing", ["name", "api_version", "isardvdi_version"])
    def test_missing_required_rejected(self, missing):
        payload = {**self._required, "usage": "production"}
        del payload[missing]
        with pytest.raises(ValidationError):
            ApiVersion(**payload)
