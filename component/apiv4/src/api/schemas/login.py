#
#   Copyright © 2025 Naomi Hidalgo Piñar
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from pydantic import BaseModel


class CategoryResponseList(BaseModel):
    """List of categories response model"""

    categories: list["CategoryItem"]


class CategoryItem(BaseModel):
    """Category item model"""

    id: str
    name: str
    custom_url_name: str


class CategoryResponse(BaseModel):
    """Single category response model"""

    id: str
    name: str


class LoginNotificationButton(BaseModel):
    """Login notification button model"""

    extra_styles: str | None = None
    text: str | None = None
    url: str | None = None


class LoginNotification(BaseModel):
    """Login notification model"""

    title: str | None = None
    description: str | None = None
    button: LoginNotificationButton | None = None
    enabled: bool = False
    icon: str | None = None
    extra_styles: str | None = None


class Locale(BaseModel):
    """Locale model"""

    default: str | None = None
    hide: bool = False
    available_locales: list[str] | None = None


class ProviderDetails(BaseModel):
    """Provider details model"""

    description: str | None = None
    hide_categories_dropdown: bool = False
    hide_forgot_password: bool = False
    submit_extra_styles: str | None = None
    submit_icon: str | None = None
    submit_text: str | None = None


class ProviderAllDetails(BaseModel):
    """Details for 'all' providers model"""

    description: str | None = None
    hide_categories_dropdown: bool = False
    display_providers: list[str] | None = None


class Providers(BaseModel):
    """Providers model"""

    all: ProviderAllDetails | None = None
    form: ProviderDetails | None = None
    saml: ProviderDetails | None = None
    google: ProviderDetails | None = None


class LoginConfigInfo(BaseModel):
    title: str | None = None


class LoginConfigLogo(BaseModel):
    hide: bool = False


class LoginConfigMaintenance(BaseModel):
    title: str | None = None
    description: str | None = None


class LoginConfigResponse(BaseModel):
    """Login configuration response model"""

    notification_cover: LoginNotification | None = None
    notification_form: LoginNotification | None = None
    info: LoginConfigInfo | None = None
    locale: Locale | None = None
    providers: Providers | None = None
    logo: LoginConfigLogo | None = None
    maintenance: LoginConfigMaintenance | None = None


class DisclaimerResponse(BaseModel):
    """Disclaimer response model"""

    title: str
    body: str
    footer: str
