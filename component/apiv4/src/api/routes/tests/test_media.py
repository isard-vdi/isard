#
#   Copyright © 2025 Pau Abril Iranzo
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


import pytest
from api.routes.tests.factories import make_category, make_group, make_user
from api.routes.tests.helpers import MockJWT


@pytest.fixture()
def media_db_factory():
    """Fixture to create a mock database for templates."""

    def media_db_tables_data(jwt: MockJWT):
        p = jwt.payload
        return {
            "domains": [
                {
                    "id": "template-1",
                    "kind": "template",
                    "user": jwt.payload["user_id"],
                    "group": jwt.payload["group_id"],
                    "category": jwt.payload["category_id"],
                    "create_dict": {"hardware": {"isos": []}},
                    "name": "Template 1",
                    "description": "Test template 1",
                    "image": "dGVzdA==",
                    "status": "Stopped",
                },
                {
                    "id": "desktop-1",
                    "kind": "desktop",
                    "user": jwt.payload["user_id"],
                    "group": jwt.payload["group_id"],
                    "category": jwt.payload["category_id"],
                    "create_dict": {
                        "hardware": {
                            "isos": [
                                {
                                    "description": "lorem ipsum dolor sit amet, consectetur adipiscing elit",
                                    "id": "media-1",
                                    "name": "dsl-4.4.10.iso",
                                }
                            ]
                        }
                    },
                    "name": "Desktop 1",
                    "description": "Test desktop 1",
                    "image": "aW1hZ2U=",
                    "status": "Stopped",
                },
                {
                    "id": "desktop-2",
                    "kind": "desktop",
                    "user": jwt.payload["user_id"],
                    "group": jwt.payload["group_id"],
                    "category": jwt.payload["category_id"],
                    "create_dict": {"hardware": {"isos": []}},
                    "name": "Desktop 2",
                    "description": "Test desktop 2",
                    "image": "aW1hZ2U=",
                    "status": "Stopped",
                },
                {
                    "id": "desktop-3",
                    "kind": "desktop",
                    "user": "another-user",
                    "group": jwt.payload["group_id"],
                    "category": jwt.payload["category_id"],
                    "create_dict": {
                        "hardware": {
                            "isos": [
                                {
                                    "description": "lorem ipsum dolor sit amet, consectetur adipiscing elit",
                                    "id": "media-1",
                                    "name": "dsl-4.4.10.iso",
                                }
                            ]
                        }
                    },
                    "name": "Desktop 3",
                    "description": "Test desktop 3",
                    "image": "aW1hZ2U=",
                    "status": "Stopped",
                },
            ],
            "media": [
                {
                    "accessed": 1709728599,
                    "allowed": {
                        "categories": False,
                        "groups": False,
                        "roles": False,
                        "users": ["another-user"],
                    },
                    "category": jwt.payload["category_id"],
                    "description": "lorem ipsum dolor sit amet, consectetur adipiscing elit",
                    "group": jwt.payload["group_id"],
                    "icon": "fa-circle-o",
                    "id": "media-1",
                    "kind": "iso",
                    "name": "dsl-4.4.10.iso",
                    "path": "{category}/{group}/{provider}/{user}/dsl-4.4.10.iso".format(
                        category=jwt.payload["category_id"],
                        group=jwt.payload["group_id"],
                        provider=jwt.payload["provider"],
                        user=jwt.payload["user_id"],
                    ),
                    "path_downloaded": "/isard/media/media-1.iso",
                    "progress": {
                        "received": "415M",
                        "received_percent": 97,
                        "speed_current": "19.2M",
                        "speed_download_average": "25.9M",
                        "speed_upload_average": "0",
                        "time_left": "0:00:01",
                        "time_spent": "0:00:15",
                        "time_total": "0:00:16",
                        "total": "415M",
                        "total_bytes": 435159040,
                        "total_percent": 100,
                        "xferd": "0",
                        "xferd_percent": "0",
                    },
                    "status": "Downloaded",
                    "status_time": 1709896679.0916216,
                    "url-isard": False,
                    "url-web": "https://example.org/dsl-4.4.10.iso",
                    "user": jwt.payload["user_id"],
                    "username": jwt.payload["name"],
                },
            ],
            "users": [
                make_user(jwt=jwt, role_id=p["role_id"]),
                make_user(
                    id="another-user",
                    name="Another User",
                    username="another-user",
                    uid="another-user",
                    role="advanced",
                    role_id="advanced",
                    provider="local",
                    group=p["group_id"],
                    category=p["category_id"],
                ),
                make_user(
                    id="another-user-2",
                    name="Another Another User",
                    username="another-user-2",
                    role="manager",
                    role_id="manager",
                    provider="local",
                    group=p["group_id"],
                    category=p["category_id"],
                ),
            ],
            "groups": [
                make_group(
                    id=p["group_id"],
                    name="Default Group",
                    uid=p["group_id"],
                    parent_category=p["category_id"],
                )
            ],
            "categories": [make_category(id=p["category_id"], uid=p["category_id"])],
        }

    return media_db_tables_data


def test_get_user_media(test_client, media_db_factory):
    jwt = MockJWT()

    db_data = media_db_factory(jwt)

    response = test_client(
        db_tables_data=db_data,
        method="GET",
        url="/items/media",
        jwt=jwt,
    )

    assert response.status_code == 200
    data = response.json()
    assert "media" in data
    assert len(data["media"]) == 1
    media = data["media"][0]
    assert media["id"] == "media-1"
    assert media["name"] == "dsl-4.4.10.iso"
    assert media["kind"] == "iso"
    assert media["status"] == "Downloaded"
    assert media["user"] == "local-default-admin-admin"
    assert media["category"] == "default"
    assert media["group"] == "default-default"
    assert media["editable"] is True
    # Progress must include the percent fields the engine writes — Vue 2's
    # progress bar reads `total_percent` directly. The schema previously
    # dropped this field during serialization; regression-guard it here.
    assert media["progress"]["received"] == "415M"
    assert media["progress"]["received_percent"] == 97
    assert media["progress"]["total"] == "415M"
    assert media["progress"]["total_percent"] == 100
    assert media["progress"]["speed_current"] == "19.2M"
    assert media["progress"]["speed_download_average"] == "25.9M"


def test_get_user_media_partial_progress(test_client, media_db_factory):
    """A media row with a sparse `progress` dict (newly inserted, before the
    engine populates it) must not 500 the entire list endpoint — every
    `MediaProgress` field has a sensible default."""
    jwt = MockJWT()

    db_data = media_db_factory(jwt)
    # Strip every progress field except `received`; the schema defaults
    # must fill in the rest without error.
    db_data["media"][0]["progress"] = {"received": "0"}

    response = test_client(
        db_tables_data=db_data,
        method="GET",
        url="/items/media",
        jwt=jwt,
    )

    assert response.status_code == 200
    media = response.json()["media"][0]
    assert media["progress"] == {
        "received": "0",
        "received_percent": 0,
        "total": "",
        "total_percent": 0,
        "speed_current": "",
        "speed_download_average": "",
    }


def test_get_media_allowed(test_client, media_db_factory):
    response = test_client(
        db_tables_data=media_db_factory(MockJWT()),
        method="GET",
        url="/items/media/get-shared",
        jwt=MockJWT(user_id="another-user"),
    )

    assert response.status_code == 200
    data = response.json()
    assert "media" in data
    assert len(data["media"]) == 1
    media = data["media"][0]
    assert media["id"] == "media-1"
    assert media["name"] == "dsl-4.4.10.iso"
    assert media["status"] == "Downloaded"
    assert media["kind"] == "iso"
    assert media["category_name"] == "Default Category"
    assert media["group_name"] == "Default Group"


def test_get_media_allowed_none(test_client, media_db_factory):
    """Test when no media is shared with the user."""
    response = test_client(
        db_tables_data=media_db_factory(MockJWT()),
        method="GET",
        url="/items/media/get-shared",
        jwt=MockJWT(user_id="another-user-2"),
    )

    assert response.status_code == 200
    assert response.json() == {"media": []}


# TODO: r.args(v) does not work correctly with rethinkdb_mock
# def test_get_media_allowed_table(test_client, media_db_factory):
#     jwt = MockJWT()
#
#     db_data = media_db_factory(jwt)
#
#     expected_response = {
#         "categories": False,
#         "groups": False,
#         "roles": False,
#         "users": [
#             {
#                 "category_name": "Default",
#                 "group_name": "Default",
#                 "id": "another-user",
#                 "name": "Another User",
#                 "uid": "another-user",
#             }
#         ],
#     }
#
#     response = test_client(
#         db_tables_data=db_data,
#         method="GET",
#         url="/item/media/{media_id}/get-allowed".format(
#             media_id="media-1",
#         ),
#         jwt=jwt,
#     )
#
#     assert response.status_code == 200
#     assert response.json() == expected_response


# TODO: r.args(v) does not work correctly with rethinkdb_mock
# def test_get_media_allowed_table_all_fields(test_client, media_db_factory):
#     jwt = MockJWT()
#
#     db_data = media_db_factory(jwt)
#
#     db_data["media"][0]["allowed"] = {
#         "categories": [jwt.payload["category_id"]],
#         "groups": [jwt.payload["group_id"]],
#         "roles": [],
#         "users": ["another-user"],
#     }
#
#     expected_response = {
#         "categories": [
#             {
#                 "id": jwt.payload["category_id"],
#                 "name": "Default Category",
#                 "uid": jwt.payload["category_id"],
#             }
#         ],
#         "groups": [
#             {
#                 "category_name": "Default Category",
#                 "id": jwt.payload["group_id"],
#                 "name": "Default Group",
#                 "parent_category": jwt.payload["category_id"],
#                 "uid": jwt.payload["group_id"],
#             }
#         ],
#         "roles": [],
#         "users": [
#             {
#                 "category_name": "Default Category",
#                 "group_name": "Default Group",
#                 "id": "another-user",
#                 "name": "Another User",
#                 "uid": "another-user",
#             }
#         ],
#     }
#
#     response = test_client(
#         db_tables_data=db_data,
#         method="GET",
#         url="/item/media/{media_id}/get-allowed".format(
#             media_id="media-1",
#         ),
#         jwt=jwt,
#     )
#
#     assert response.status_code == 200
#     assert response.json() == expected_response


def test_get_media_desktops(test_client, media_db_factory):
    jwt = MockJWT()

    db_data = media_db_factory(jwt)

    expected_response = [
        {
            "create_dict": {
                "hardware": {
                    "isos": [
                        {
                            "description": "lorem ipsum dolor sit amet, consectetur adipiscing elit",
                            "id": "media-1",
                            "name": "dsl-4.4.10.iso",
                        }
                    ]
                }
            },
            "id": "desktop-1",
            "kind": "desktop",
            "name": "Desktop 1",
            "status": "Stopped",
            "user": "local-default-admin-admin",
            "user_name": "Administrator",
        },
        {
            "create_dict": {
                "hardware": {
                    "isos": [
                        {
                            "description": "lorem ipsum dolor sit amet, consectetur adipiscing elit",
                            "id": "media-1",
                            "name": "dsl-4.4.10.iso",
                        }
                    ]
                }
            },
            "id": "desktop-3",
            "kind": "desktop",
            "name": "Desktop 3",
            "status": "Stopped",
            "user": "another-user",
            "user_name": "Another User",
        },
    ]

    response = test_client(
        db_tables_data=db_data,
        method="GET",
        url="/item/media/{media_id}/get-desktops".format(
            media_id="media-1",
        ),
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == expected_response


# ─── Routes added when replacing /desktops/media_list, /media/installs
# and /media/check/{id} shims ─────────────────────────────────────────────


def test_list_media_installs(monkeypatch, test_client):
    """GET /items/media/installs returns the virt_install table plucked
    to the v3 wire shape (id, name, description, vers) and sorted by
    name. Replaces v3_compat /media/installs. The list_virt_installs
    helper in _common does the pluck + sort server-side via the
    rethink query; the route wraps it in the VirtInstallListResponse
    envelope."""
    jwt = MockJWT()
    # Helper returns rows already plucked + sorted by name. Rows may or
    # may not carry ``vers``; the schema's default fills "" when absent.
    stub = [
        {"id": "vi-2", "name": "debian-12", "description": "Debian bookworm"},
        {"id": "vi-1", "name": "ubuntu-24.04", "description": "Ubuntu LTS"},
    ]

    monkeypatch.setattr(
        "isardvdi_common.lib.domains.xml_sections.XmlSectionsProcessed.list_virt_installs",
        staticmethod(lambda: stub),
    )

    response = test_client(url="/items/media/installs", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"installs"}
    installs = body["installs"]
    assert [row["name"] for row in installs] == ["debian-12", "ubuntu-24.04"]
    assert all(row["vers"] == "" for row in installs)


def test_list_desktop_attached_media(monkeypatch, test_client):
    """GET /item/desktop/{id}/media-list returns the media hotplug list
    (replaces v3_compat POST /desktops/media_list)."""
    jwt = MockJWT()
    stub = [
        {"id": "iso-1", "name": "dsl-4.4.10.iso", "kind": "iso", "size": "500MiB"},
        {"id": "fdd-1", "name": "dos622.img", "kind": "floppy", "size": "1.4MiB"},
    ]

    monkeypatch.setattr(
        "api.services.media.MediaService.list_desktop_attached_media",
        staticmethod(lambda desktop_id: stub),
    )
    # Neutralise the owns_domain_id("desktop_id") factory checker.
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_domain_id",
        staticmethod(lambda payload, domain_id: domain_id),
    )

    response = test_client(
        url="/admin/item/desktop/desktop-1/media-list",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == stub


def test_create_media(monkeypatch, test_client):
    """POST /item/media wraps MediaService.create_media with a request
    body validated by CreateMediaRequest — tests stub the service so the
    URL validation / download doesn't run."""
    jwt = MockJWT(role_id="advanced")
    captured = {}

    def fake_create_media(data, payload):
        captured["name"] = data.name
        captured["kind"] = data.kind.value
        captured["url"] = str(data.url)
        captured["user_id"] = payload["user_id"]
        return "media-new"

    monkeypatch.setattr(
        "api.services.media.MediaService.create_media",
        staticmethod(fake_create_media),
    )

    response = test_client(
        url="/item/media",
        method="POST",
        body={
            "name": "Ubuntu 24.04 ISO",
            "description": "Ubuntu LTS",
            "allowed": {
                "users": False,
                "groups": False,
                "categories": False,
                "roles": False,
            },
            "kind": "iso",
            "url": "https://releases.example.org/ubuntu.iso",
            "hypervisors_pools": ["default"],
        },
        jwt=jwt,
    )

    assert response.status_code == 201
    assert response.json() == {"id": "media-new"}
    assert captured["name"] == "Ubuntu 24.04 ISO"
    assert captured["kind"] == "iso"
    assert captured["user_id"] == jwt.payload["user_id"]


def test_delete_media(monkeypatch, test_client):
    """DELETE /item/media/{id} returns 200 item.deleted when the service
    returns None (soft delete). This route is on ``open_router`` so the
    owns_media_id checker is the only thing that runs the has_token
    chain and populates ``request.token_payload`` — we can't override
    it via ``app.dependency_overrides`` (that would skip has_token and
    the route would crash accessing ``request.token_payload``). Instead
    we monkeypatch ``Helpers.owns_media_id`` at the common-lib layer so
    the full chain runs and only the ownership check is neutralised."""
    jwt = MockJWT(role_id="advanced")
    captured = {}

    def fake_delete(media_id, payload):
        captured["media_id"] = media_id
        captured["user_id"] = payload["user_id"]
        return None

    monkeypatch.setattr(
        "api.services.media.MediaService.delete_media",
        staticmethod(fake_delete),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_media_id",
        staticmethod(lambda payload, media_id: media_id),
    )

    response = test_client(
        url="/item/media/media-1",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json()["message_code"] == "item.deleted"
    assert captured == {"media_id": "media-1", "user_id": jwt.payload["user_id"]}


def test_check_media(monkeypatch, test_client):
    """PUT /item/media/{id}/check schedules the check_media_existence
    background task (replaces v3_compat /media/check/{id}). The route
    is on manager_router (matching v3 ``@is_admin_or_manager``)."""
    from api import app
    from api.dependencies.alloweds import owns_media_id

    jwt = MockJWT()  # default admin satisfies manager_router
    stub = {"task_id": "task-1"}
    captured = {}

    def fake_check(media_id, user_id):
        captured["media_id"] = media_id
        captured["user_id"] = user_id
        return stub

    monkeypatch.setattr(
        "api.services.media.MediaService.check_media_existence",
        staticmethod(fake_check),
    )

    async def mock_owns_media_id():
        return "media-1"

    app.dependency_overrides[owns_media_id] = mock_owns_media_id

    try:
        response = test_client(
            url="/admin/item/media/media-1/check",
            method="PUT",
            jwt=jwt,
        )
    finally:
        app.dependency_overrides.pop(owns_media_id, None)

    assert response.status_code == 200
    assert response.json() == stub
    assert captured == {
        "media_id": "media-1",
        "user_id": jwt.payload["user_id"],
    }


def test_change_media_owner(monkeypatch, test_client):
    """PUT /item/media/{id}/change-owner/{user_id} — mirrors v3
    ``api_v3_media_change_owner`` (``CommonView.py:214``).
    Manager-tier route; service enforces ``ownsUserId`` +
    ``ownsMediaId`` before delegating to
    ``Helpers.change_owner_media``."""
    jwt = MockJWT()
    captured = {}

    def fake_change_owner(payload, media_id, new_user_id):
        captured["media_id"] = media_id
        captured["new_user_id"] = new_user_id

    monkeypatch.setattr(
        "api.services.media.MediaService.change_owner",
        staticmethod(fake_change_owner),
    )

    response = test_client(
        url="/admin/item/media/media-1/change-owner/user-new",
        method="PUT",
        jwt=jwt,
    )
    assert response.status_code == 200
    assert response.json() == {"id": "media-1"}
    assert captured == {"media_id": "media-1", "new_user_id": "user-new"}
