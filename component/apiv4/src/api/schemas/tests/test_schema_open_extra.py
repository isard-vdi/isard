# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/open_extra.py``."""

import pytest
from api.schemas.open_extra import CategoryResponse, LoginConfigResponse
from pydantic import ValidationError


class TestCategoryResponse:
    """Public per-category response (used for the login picker). All
    fields except `id` are optional so a partial DB row doesn't break
    rendering."""

    def test_id_required(self):
        with pytest.raises(ValidationError):
            CategoryResponse()

    def test_minimal(self):
        c = CategoryResponse(id="default")
        assert c.id == "default"
        assert c.name is None
        assert c.frontend is None

    def test_full(self):
        c = CategoryResponse(
            id="default",
            name="Default",
            frontend=True,
            custom_url_name="default",
            photo="data:image/png;base64,iVBORw...",
        )
        assert c.frontend is True


class TestLoginConfigResponse:
    """The flat-shape `/item/login-config` response — must stay compatible
    with both per-category and global endpoints (per
    ``test_admin_categories.py::TestLoginConfigByCategory``)."""

    def test_accepts_empty(self):
        r = LoginConfigResponse()
        assert r.notification_cover is None
        assert r.notification_form is None

    def test_accepts_full(self):
        r = LoginConfigResponse(
            notification_cover={"enabled": True, "title": "Hi"},
            notification_form={"enabled": False, "title": "Form"},
        )
        assert r.notification_cover["title"] == "Hi"
