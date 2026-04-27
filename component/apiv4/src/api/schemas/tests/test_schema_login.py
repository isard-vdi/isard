# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/login.py``."""

import pytest
from api.schemas.login import (
    CategoryItem,
    CategoryResponse,
    CategoryResponseList,
    DisclaimerResponse,
    Locale,
    LoginConfigInfo,
    LoginConfigLogo,
    LoginConfigMaintenance,
    LoginConfigResponse,
    LoginNotification,
    LoginNotificationButton,
    ProviderAllDetails,
    ProviderDetails,
    Providers,
)
from pydantic import ValidationError


class TestCategoryResponseList:
    def test_categories_required(self):
        with pytest.raises(ValidationError):
            CategoryResponseList()

    def test_accepts_empty(self):
        assert CategoryResponseList(categories=[]).categories == []

    def test_nested_categoryitem_validation(self):
        """Forward ref to CategoryItem — pin that nested dict validation
        propagates."""
        with pytest.raises(ValidationError):
            CategoryResponseList(categories=[{"id": "default"}])  # name missing


class TestCategoryItem:
    @pytest.mark.parametrize("missing", ["id", "name", "custom_url_name"])
    def test_required(self, missing):
        payload = {"id": "default", "name": "Default", "custom_url_name": "default"}
        del payload[missing]
        with pytest.raises(ValidationError):
            CategoryItem(**payload)


class TestCategoryResponse:
    @pytest.mark.parametrize("missing", ["id", "name"])
    def test_required(self, missing):
        payload = {"id": "default", "name": "Default"}
        del payload[missing]
        with pytest.raises(ValidationError):
            CategoryResponse(**payload)


class TestLoginNotificationButton:
    def test_all_optional(self):
        b = LoginNotificationButton()
        assert b.text is None
        assert b.url is None
        assert b.extra_styles is None


class TestLoginNotification:
    def test_default_disabled(self):
        n = LoginNotification()
        assert n.enabled is False
        assert n.title is None
        assert n.button is None

    def test_full(self):
        n = LoginNotification(
            title="Hi",
            description="welcome",
            button={"text": "ok", "url": "https://x"},
            enabled=True,
            icon="info",
            extra_styles="font-bold",
        )
        assert n.button.url == "https://x"


class TestLocale:
    def test_default_hide_false(self):
        loc = Locale()
        assert loc.default is None
        assert loc.hide is False
        assert loc.available_locales is None

    def test_full(self):
        loc = Locale(default="en", hide=True, available_locales=["en", "ca", "es"])
        assert "en" in loc.available_locales


class TestProviderDetails:
    def test_defaults(self):
        p = ProviderDetails()
        assert p.hide_categories_dropdown is False
        assert p.hide_forgot_password is False


class TestProviderAllDetails:
    def test_defaults(self):
        p = ProviderAllDetails()
        assert p.hide_categories_dropdown is False
        assert p.display_providers is None


class TestProviders:
    def test_all_optional(self):
        p = Providers()
        assert p.all is None
        assert p.form is None

    def test_nested_validation(self):
        p = Providers(form={"description": "Local login"})
        assert p.form.description == "Local login"


class TestLoginConfigSubmodels:
    def test_info_optional(self):
        assert LoginConfigInfo().title is None

    def test_logo_default_hide_false(self):
        assert LoginConfigLogo().hide is False

    def test_maintenance_optional(self):
        m = LoginConfigMaintenance()
        assert m.title is None
        assert m.description is None


class TestLoginConfigResponse:
    """The full /login_config response — every sub-model Optional so a
    minimally-configured deployment doesn't 500."""

    def test_accepts_empty(self):
        r = LoginConfigResponse()
        assert r.notification_cover is None
        assert r.providers is None

    def test_full_nested(self):
        r = LoginConfigResponse(
            notification_cover={"enabled": True, "title": "x"},
            info={"title": "Welcome"},
            logo={"hide": True},
            providers={"form": {"description": "Local"}},
        )
        assert r.notification_cover.enabled is True
        assert r.providers.form.description == "Local"


class TestDisclaimerResponse:
    @pytest.mark.parametrize("missing", ["title", "body", "footer"])
    def test_required(self, missing):
        payload = {"title": "T", "body": "B", "footer": "F"}
        del payload[missing]
        with pytest.raises(ValidationError):
            DisclaimerResponse(**payload)
