# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Copyright © 2025 Naomi Hidalgo Piñar
#
# This file is part of IsardVDI.
#
# IsardVDI is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License
# along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.

import pytest
from api.routes.tests.helpers import MockJWT


@pytest.fixture()
def login_db_factory():
    """Fixture to create a mock database for login."""

    def login_db_tables_data(jwt):
        return {
            "users": [
                {
                    "id": jwt.payload["user_id"],
                    "category": jwt.payload["category_id"],
                    "group": jwt.payload["group_id"],
                    "name": jwt.payload["name"],
                    "username": jwt.payload["name"],
                    "password": "f0ckt3Rf$",
                    "lang": "en",
                    "provider": jwt.payload["provider"],
                    "role": jwt.payload["role_id"],
                    "uid": jwt.payload["name"],
                    "accessed": 1234567890,
                    "photo": "",
                },
                {
                    "id": "another-user",
                    "category": jwt.payload["category_id"],
                    "group": f"another-group-{jwt.payload['category_id']}",
                    "name": "Another User",
                    "username": "another-user",
                    "password": "another-password",
                    "provider": "local",
                    "role": "advanced",
                    "uid": "another-user",
                    "accessed": 1234567890,
                    "photo": "",
                },
                {
                    "id": "cat2-user",
                    "category": "cat2",
                    "group": "group-cat2",
                    "name": "Cat2 User",
                    "username": "cat2-user",
                    "password": "cat2-password",
                    "provider": "local",
                    "role": "advanced",
                    "uid": "cat2-user",
                    "accessed": 1234567890,
                    "photo": "",
                },
            ],
            "categories": [
                {
                    "id": jwt.payload["category_id"],
                    "name": "Default Category",
                    "uid": jwt.payload["category_id"],
                    "custom_url_name": "default_url",
                    "frontend": True,
                },
                {
                    "id": "00000000-0000-0000-0000-000000000002",
                    "name": "Another Category",
                    "uid": "cat2",
                    "custom_url_name": "another",
                    "frontend": False,
                },
            ],
            "config": [
                {
                    "id": 1,
                    "login": {
                        "notification_cover": {
                            "button": {
                                "extra_styles": "color: #114955;",
                                "text": "Link",
                                "url": "#",
                            },
                            "description": "Cover notification description",
                            "enabled": True,
                            "extra_styles": "background-color: #f9ecec;",
                            "icon": "tool-01",
                            "title": "TITLE",
                        },
                        "notification_form": {
                            "button": {
                                "extra_styles": "color: #f18ae0;",
                                "text": "",
                                "url": "",
                            },
                            "description": "Form notification description",
                            "enabled": False,
                            "extra_styles": "background-color: #ffffff;",
                            "icon": "",
                            "title": "TITLE",
                        },
                        "providers": {
                            "all": {"hide_forgot_password": True},
                            "form": {"hide_forgot_password": True},
                        },
                    },
                }
            ],
            "authentication": [
                {
                    "category": "all",
                    "disclaimer": True,
                    "email_verification": False,
                    "id": "f5162e25-519e-482c-a8d9-8a8611f7bea2",
                    "password": {
                        "digits": 0,
                        "expiration": 0,
                        "length": 8,
                        "lowercase": 0,
                        "not_username": True,
                        "old_passwords": 0,
                        "special_characters": 0,
                        "uppercase": 0,
                    },
                    "role": "all",
                    "type": "local",
                }
            ],
            "notification_tmpls": [
                {
                    "default": "en",
                    "description": "Disclaimer text",
                    "id": "5591df66-1cbd-4ed6-94a9-4d53f683c066",
                    "kind": "none",
                    "lang": {
                        "en": {
                            "body": "<p>This is a <b>disclaimer</b> in english</p>",
                            "footer": "Beware of risks",
                            "title": "DISCLAIMER",
                        },
                    },
                    "name": "Bastion enabled disclaimer",
                    "system": {
                        "body": "<p>This is a <b>disclaimer</b> in system language by default</p>",
                        "footer": "Beware of risks",
                        "title": "DISCLAIMER",
                    },
                    "vars": {},
                }
            ],
        }

    return login_db_tables_data


def test_get_frontend_categories(test_client, login_db_factory):
    jwt = MockJWT()

    db_data = login_db_factory(jwt)

    expected = {
        "categories": [
            {
                "custom_url_name": "default_url",
                "id": jwt.payload["category_id"],
                "name": "Default Category",
            }
        ]
    }
    response = test_client(db_tables_data=db_data, url="/items/categories", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == expected


def test_get_category_custom_url(test_client, login_db_factory):
    jwt = MockJWT()

    db_data = login_db_factory(jwt)

    expected = {
        "id": "00000000-0000-0000-0000-000000000002",
        "name": "Another Category",
    }
    response = test_client(
        db_tables_data=db_data, url="/item/category/another", jwt=jwt, method="GET"
    )

    assert response.status_code == 200
    assert response.json() == expected


def test_get_login_config(test_client, login_db_factory):
    jwt = MockJWT()

    db_data = login_db_factory(jwt)

    response = test_client(
        db_tables_data=db_data, url="/item/login-config", jwt=jwt, method="GET"
    )

    assert response.status_code == 200
    data = response.json()
    # Notifications come back as 1-item lists so the public login page can
    # render the global notification next to the per-category one when a
    # category id is supplied. Pre-feature single-dict notifications stored
    # on the config row are wrapped server-side. See
    # services/config.py::get_login_config and the schema docstring.
    assert isinstance(data["notification_cover"], list)
    assert data["notification_cover"][0]["enabled"] is True
    assert data["notification_cover"][0]["title"] == "TITLE"
    assert (
        data["notification_cover"][0]["description"] == "Cover notification description"
    )
    assert isinstance(data["notification_form"], list)
    assert data["notification_form"][0]["enabled"] is False
    # Verify providers
    assert data["providers"] is not None


# ─── Admin login config (global notification) ──────────────────────────


def test_admin_update_login_notification(monkeypatch, test_client):
    """PUT /login_config/notification — global cover/form config update."""
    jwt = MockJWT()
    captured = {}

    def fake_update(dump):
        captured["cover_enabled"] = dump["cover"]["enabled"]

    monkeypatch.setattr(
        "api.services.admin.login_config.AdminLoginConfigService.update_login_notification",
        staticmethod(fake_update),
    )

    response = test_client(
        url="/login_config/notification",
        method="PUT",
        body={"cover": {"enabled": True}, "form": {"enabled": False}},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured == {"cover_enabled": True}


def test_admin_enable_cover_login_notification(monkeypatch, test_client):
    """PUT /login_config/notification/cover/enable — enable/disable toggle."""
    jwt = MockJWT()
    captured = {}

    def fake_enable(kind, enabled):
        captured["kind"] = kind
        captured["enabled"] = enabled

    monkeypatch.setattr(
        "api.services.admin.login_config.AdminLoginConfigService.enable_login_notification",
        staticmethod(fake_enable),
    )

    response = test_client(
        url="/login_config/notification/cover/enable",
        method="PUT",
        body={"enabled": True},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured == {"kind": "cover", "enabled": True}


# def test_get_disclaimer(test_client, login_db_factory):
#     jwt = MockJWT(token_type="disclaimer-acknowledgement-required")
#     print(jwt)

#     db_data = login_db_factory(jwt)

#     expected = {
#         "body": "<p>This is a <b>disclaimer</b> in english</p>",
#         "footer": "Beware of risks",
#         "title": "DISCLAIMER",
#     }

#     response = test_client(
#         db_tables_data=db_data, url="/item/disclaimer", jwt=jwt, method="GET"
#     )

#     assert response.status_code == 200
#     assert response.json() == expected
