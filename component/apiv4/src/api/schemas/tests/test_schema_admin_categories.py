# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_categories.py``.

Covers per-category branding, branding-update body, and the
per-category login_notification request shapes.
"""

import pytest
from api.schemas.admin_categories import (
    BrandingDomain,
    BrandingLogo,
    BrandingUpdateData,
    CategoryLoginNotificationData,
    CategoryLoginNotificationEnableData,
)
from pydantic import ValidationError


class TestBrandingDomain:
    def test_defaults(self):
        b = BrandingDomain()
        assert b.enabled is False
        assert b.name is None
        assert b.certificate_source is None
        assert b.certificate_data is None

    def test_certificate_source_literal(self):
        """certificate_source is a Literal['acme', 'custom'] — pin so
        an unsupported source fails fast."""
        BrandingDomain(certificate_source="acme")
        BrandingDomain(certificate_source="custom")
        with pytest.raises(ValidationError):
            BrandingDomain(certificate_source="self-signed")

    def test_full(self):
        b = BrandingDomain(
            enabled=True,
            name="example.com",
            certificate_source="acme",
            certificate_data="---PEM---",
        )
        assert b.enabled is True
        assert b.certificate_data == "---PEM---"


class TestBrandingLogo:
    def test_defaults(self):
        b = BrandingLogo()
        assert b.enabled is False
        assert b.data is None

    def test_data_passes_through(self):
        """data is a base64 data URL — schema doesn't validate the
        format, the route does."""
        b = BrandingLogo(enabled=True, data="data:image/png;base64,iVBORw...")
        assert b.data.startswith("data:image/png;")


class TestBrandingUpdateData:
    def test_accepts_empty(self):
        """All sub-models optional; an empty body is a no-op update."""
        u = BrandingUpdateData()
        assert u.domain is None
        assert u.logo is None

    def test_nested_models_validated(self):
        """Pin that sub-model validation propagates: an invalid
        certificate_source on the nested BrandingDomain still fails."""
        with pytest.raises(ValidationError):
            BrandingUpdateData(domain={"certificate_source": "bogus"})

    def test_partial_update(self):
        u = BrandingUpdateData(logo={"enabled": True})
        assert u.logo.enabled is True
        assert u.domain is None


class TestCategoryLoginNotificationData:
    def test_accepts_empty(self):
        d = CategoryLoginNotificationData()
        assert d.cover is None
        assert d.form is None

    def test_arbitrary_dict(self):
        """Dict[str, Any] — the route does its own validation.
        Same shape as the global LoginNotificationUpdateRequest."""
        d = CategoryLoginNotificationData(cover={"enabled": True, "title": "x"})
        assert d.cover["title"] == "x"


class TestCategoryLoginNotificationEnableData:
    def test_enabled_required(self):
        with pytest.raises(ValidationError):
            CategoryLoginNotificationEnableData()

    def test_accepts_bool(self):
        assert CategoryLoginNotificationEnableData(enabled=True).enabled is True
        assert CategoryLoginNotificationEnableData(enabled=False).enabled is False
