# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_user_storage.py``.

All three request schemas carry credentials (password) — pin every
required field so a regression that defaults `password` to None
silently registers a credentials-free provider.
"""

import pytest
from api.schemas.admin_user_storage import (
    UserStorageAddRequest,
    UserStorageAutoRegisterRequest,
    UserStorageConnTestRequest,
)
from pydantic import ValidationError


class TestUserStorageAutoRegisterRequest:
    _required = {
        "domain": "https://nc.example.com",
        "user": "admin",
        "password": "s3cret",
        "intra_docker": False,
        "verify_cert": True,
    }

    def test_accepts_required(self):
        r = UserStorageAutoRegisterRequest(**self._required)
        assert r.domain == "https://nc.example.com"
        assert r.password == "s3cret"

    @pytest.mark.parametrize(
        "missing", ["domain", "user", "password", "intra_docker", "verify_cert"]
    )
    def test_every_field_required(self, missing):
        """All five fields required — no defaults. Pin so password
        never quietly becomes Optional."""
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            UserStorageAutoRegisterRequest(**payload)

    def test_round_trip_preserves_password(self):
        r = UserStorageAutoRegisterRequest(**self._required)
        round_tripped = UserStorageAutoRegisterRequest(**r.model_dump())
        assert round_tripped.password == "s3cret"


class TestUserStorageConnTestRequest:
    _required = {
        "provider": "nextcloud",
        "url": "https://nc.example.com",
        "urlprefix": "/remote.php/dav/",
        "user": "admin",
        "password": "s3cret",
        "verify_cert": True,
    }

    def test_accepts_required(self):
        r = UserStorageConnTestRequest(**self._required)
        assert r.provider == "nextcloud"
        assert r.urlprefix == "/remote.php/dav/"

    @pytest.mark.parametrize(
        "missing",
        ["provider", "url", "urlprefix", "user", "password", "verify_cert"],
    )
    def test_every_field_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            UserStorageConnTestRequest(**payload)


class TestUserStorageAddRequest:
    _required = {
        "provider": "nextcloud",
        "name": "Personal NC",
        "description": "User personal NC",
        "url": "https://nc.example.com",
        "urlprefix": "/remote.php/dav/",
        "access": "ro",
        "quota": 0,
        "verify_cert": True,
    }

    def test_accepts_required(self):
        r = UserStorageAddRequest(**self._required)
        assert r.access == "ro"
        assert r.quota == 0

    @pytest.mark.parametrize(
        "missing",
        [
            "provider",
            "name",
            "description",
            "url",
            "urlprefix",
            "access",
            "quota",
            "verify_cert",
        ],
    )
    def test_every_field_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            UserStorageAddRequest(**payload)

    def test_quota_accepts_any(self):
        """quota: Any — pin that the field passes through int / dict /
        None alike. Some providers report quota as a structure."""
        r = UserStorageAddRequest(**{**self._required, "quota": None})
        assert r.quota is None
        r = UserStorageAddRequest(
            **{**self._required, "quota": {"used": 1024, "max": 4096}}
        )
        assert r.quota == {"used": 1024, "max": 4096}
