# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_login_config.py``."""

import pytest
from api.schemas.admin_login_config import (
    LoginNotificationEnableRequest,
    LoginNotificationUpdateRequest,
)
from pydantic import ValidationError


class TestLoginNotificationUpdateRequest:
    """Both `cover` and `form` are Optional[Dict[str, Any]] so an empty
    body is valid (a no-op update). The route does its own URL-scheme
    validation on `cover.button.url` / `form.button.url`."""

    def test_accepts_empty(self):
        r = LoginNotificationUpdateRequest()
        assert r.cover is None
        assert r.form is None

    def test_accepts_partial(self):
        r = LoginNotificationUpdateRequest(cover={"enabled": True, "title": "Hi"})
        assert r.cover["title"] == "Hi"
        assert r.form is None

    def test_accepts_full(self):
        body = {
            "cover": {
                "enabled": True,
                "title": "Cover",
                "button": {"url": "https://x"},
            },
            "form": {"enabled": False, "title": "Form"},
        }
        r = LoginNotificationUpdateRequest(**body)
        assert r.cover["button"]["url"] == "https://x"
        assert r.form["enabled"] is False

    def test_dict_values_arbitrary(self):
        """Dict[str, Any] — nested arbitrary structures pass through.
        Pin so a future change to a typed sub-model fails loud here."""
        r = LoginNotificationUpdateRequest(cover={"any": [1, "two", {"three": 3}]})
        assert r.cover == {"any": [1, "two", {"three": 3}]}


class TestLoginNotificationEnableRequest:
    def test_accepts_true(self):
        assert LoginNotificationEnableRequest(enabled=True).enabled is True

    def test_accepts_false(self):
        assert LoginNotificationEnableRequest(enabled=False).enabled is False

    def test_missing_enabled_rejected(self):
        with pytest.raises(ValidationError):
            LoginNotificationEnableRequest()

    def test_round_trip(self):
        r = LoginNotificationEnableRequest(enabled=True)
        assert LoginNotificationEnableRequest(**r.model_dump()) == r

    def test_string_true_coerced(self):
        """Pydantic v2 default mode coerces 'true'/'false' strings to bool.
        Pin the current behavior so a future strict-mode flip is noticed."""
        r = LoginNotificationEnableRequest(enabled="true")
        assert r.enabled is True
