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
def templates_db_factory():
    """Fixture to create a mock database for templates."""

    def templates_db_tables_data(jwt):
        p = jwt.payload
        return {
            "domains": [
                {
                    "id": "template-1",
                    "kind": "template",
                    "user": p["user_id"],
                    "group": p["group_id"],
                    "category": p["category_id"],
                    "create_dict": {"hardware": {"isos": []}},
                    "name": "Template 1",
                    "description": "Test template 1",
                    "image": {"id": "img-test", "type": "stock"},
                    "enabled": True,
                },
                {
                    "id": "desktop-1",
                    "kind": "desktop",
                    "user": p["user_id"],
                    "group": p["group_id"],
                    "category": p["category_id"],
                    "create_dict": {"hardware": {"isos": []}},
                    "name": "Desktop 1",
                    "description": "Test desktop 1",
                    "image": "aW1hZ2U=",
                },
            ],
            "users": [
                make_user(jwt=jwt, role_id=p["role_id"]),
                make_user(
                    id="another-user",
                    name="Another User",
                    username="another-user",
                    role_id="advanced",
                    role="advanced",
                    provider="local",
                    group=p["group_id"],
                    category=p["category_id"],
                ),
            ],
            "groups": [make_group(id=p["group_id"])],
            "categories": [make_category(id=p["category_id"])],
        }

    return templates_db_tables_data


@pytest.mark.clear_cache
def test_get_all_templates(test_client, templates_db_factory):
    jwt = MockJWT(role_id="advanced")

    db_tables_data = templates_db_factory(jwt)

    expected_response = {
        "templates": [
            {
                "id": "template-1",
                "name": "Template 1",
                "description": "Test template 1",
                "image": {"id": "img-test", "type": "stock", "url": None},
                "enabled": True,
                # ``status`` and ``progress`` were added so the templates
                # list can render a progress bar while the apiv4 +
                # isard-storage chain is creating the template. Both are
                # absent in this fixture row, so they serialize as null.
                "status": None,
                "progress": None,
            }
        ]
    }

    response = test_client(
        db_tables_data=db_tables_data,
        method="GET",
        url="/api/v4/items/templates",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == expected_response


# ─── Flat allowed templates list (token_router) ──────────────────────────
# The /items/templates/allowed/{kind} route replaces the v3 shim
# /user/templates/allowed/{kind} and exposes a flat list backed by
# TemplateService.get_user_allowed_templates_flat. The old shim was a
# regression that called the wrong underlying method; these tests nail
# down the fix.


def test_get_user_allowed_templates_flat_all(monkeypatch, test_client):
    jwt = MockJWT(role_id="advanced")
    stub = [
        {
            "id": "template-1",
            "name": "Template 1",
            "kind": "template",
            "category": "default",
            "group": "default-default",
            "description": "",
            "status": "Stopped",
            "enabled": True,
        },
        {
            "id": "template-2",
            "name": "Template 2",
            "kind": "template",
            "category": "default",
            "group": "default-default",
            "description": "",
            "status": "Stopped",
            "enabled": True,
        },
    ]
    captured = {}

    def fake_flat(payload, kind):
        captured["payload_user"] = payload.get("user_id")
        captured["kind"] = kind
        return stub

    monkeypatch.setattr(
        "api.services.templates.TemplateService.get_user_allowed_templates_flat",
        staticmethod(fake_flat),
    )

    response = test_client(url="/items/templates/allowed/all", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    # response_model=list[UserAllowedTemplateFlatItem] fills missing
    # optional fields (allowed/category_name/group_name/icon/image/user/
    # user_name) with None; compare per-key on the stubbed fields only.
    assert len(body) == len(stub)
    for got, expected in zip(body, stub):
        for key, value in expected.items():
            assert got[key] == value
    assert captured == {
        "payload_user": jwt.payload["user_id"],
        "kind": "all",
    }


def test_get_user_allowed_templates_flat_shared(monkeypatch, test_client):
    jwt = MockJWT(role_id="advanced")
    captured = {}

    def fake_flat(payload, kind):
        captured["kind"] = kind
        return []

    monkeypatch.setattr(
        "api.services.templates.TemplateService.get_user_allowed_templates_flat",
        staticmethod(fake_flat),
    )

    response = test_client(url="/items/templates/allowed/shared", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == []
    assert captured["kind"] == "shared"


# ─── Template set-enabled (advanced_router) ──────────────────────────────
# /item/template/{id}/set-enabled replaces the v3 /template/update shim
# that accepted {id, enabled} in the body. The v4 route moves the id to
# the path and uses a TemplateSetEnabledRequest schema. Both
# owns_domain_id and check_domain_kind dependencies have to be bypassed
# for the route test to stay hermetic.


class _FakeDomainTemplate:
    """Tiny stand-in for isardvdi_common.models.domain.Domain used by
    check_domain_kind. Instantiating ``Domain(id).kind`` is enough to
    satisfy the bound dependency."""

    def __init__(self, domain_id):
        self.id = domain_id
        self.kind = "template"


def test_set_template_enabled_disable(monkeypatch, test_client):
    """PUT /item/template/{id}/set-enabled with enabled=False must
    cascade-flag non-persistent desktops as ForceDeleting (v3 parity)
    AND write the new enabled value via update_template."""
    jwt = MockJWT(role_id="advanced")
    cascade_calls = []
    update_calls = []
    quota_calls = []

    monkeypatch.setattr(
        "api.services.templates.CommonTemplates.delete_non_persistent_desktops",
        staticmethod(lambda template_id: cascade_calls.append(template_id)),
    )
    monkeypatch.setattr(
        "api.services.templates.CommonTemplates.update_template",
        staticmethod(
            lambda template_id, data: update_calls.append((template_id, data))
            or {"id": template_id, **data}
        ),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.quotas.Quotas.template_create",
        staticmethod(lambda user_id, quantity=1: quota_calls.append(user_id)),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_domain_id",
        staticmethod(lambda payload, domain_id: domain_id),
    )
    monkeypatch.setattr(
        "api.dependencies.domains.Domain",
        _FakeDomainTemplate,
    )

    response = test_client(
        url="/item/template/template-1/set-enabled",
        method="PUT",
        body={"enabled": False},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": "template-1"}
    # Disable path: cascade ran, update wrote enabled=False, quota NOT checked
    assert cascade_calls == ["template-1"]
    assert update_calls == [("template-1", {"enabled": False})]
    assert quota_calls == []


def test_set_template_enabled_enable_runs_quota_check(monkeypatch, test_client):
    """PUT /item/template/{id}/set-enabled with enabled=True must run
    Quotas.template_create (v3 parity) before writing the enabled flag."""
    jwt = MockJWT(role_id="advanced")
    cascade_calls = []
    update_calls = []
    quota_calls = []

    monkeypatch.setattr(
        "api.services.templates.CommonTemplates.delete_non_persistent_desktops",
        staticmethod(lambda template_id: cascade_calls.append(template_id)),
    )
    monkeypatch.setattr(
        "api.services.templates.CommonTemplates.update_template",
        staticmethod(
            lambda template_id, data: update_calls.append((template_id, data))
            or {"id": template_id, **data}
        ),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.quotas.Quotas.template_create",
        staticmethod(lambda user_id, quantity=1: quota_calls.append(user_id)),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_domain_id",
        staticmethod(lambda payload, domain_id: domain_id),
    )
    monkeypatch.setattr(
        "api.dependencies.domains.Domain",
        _FakeDomainTemplate,
    )

    response = test_client(
        url="/item/template/template-1/set-enabled",
        method="PUT",
        body={"enabled": True},
        jwt=jwt,
    )

    assert response.status_code == 200
    # Enable path: quota check ran, update wrote enabled=True, cascade NOT run
    assert quota_calls == [jwt.payload["user_id"]]
    assert update_calls == [("template-1", {"enabled": True})]
    assert cascade_calls == []


# ─── Template CRUD (T1 shim replacements) ────────────────────────────────
# These endpoints replace v3 shims like POST /template, POST
# /template/duplicate/{id}, DELETE /template/{id} and GET
# /template/tree/{id}. Tests stub the quota/storage-pool dependency chain
# (overridable via app.dependency_overrides) and the per-id owns/kind
# checker factories (monkeypatched via Helpers / FakeDomain).


def test_create_template(monkeypatch, test_client):
    from api import app
    from api.dependencies.quotas import can_create_template
    from api.dependencies.storage_pools import check_create_storage_pool_availability

    jwt = MockJWT(role_id="advanced")
    monkeypatch.setattr(
        "api.services.templates.TemplateService.create_template",
        staticmethod(lambda payload, data: "template-new"),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_domain_id",
        staticmethod(lambda payload, domain_id: domain_id),
    )

    async def mock_can_create_template():
        return None

    async def mock_check_storage_pool():
        return None

    app.dependency_overrides[can_create_template] = mock_can_create_template
    app.dependency_overrides[check_create_storage_pool_availability] = (
        mock_check_storage_pool
    )
    try:
        response = test_client(
            url="/item/template",
            method="POST",
            body={
                "desktop_id": "desktop-1",
                "name": "My Template",
                "description": "Test template",
                "allowed": {"users": False, "groups": False},
                "enabled": True,
            },
            jwt=jwt,
        )
    finally:
        app.dependency_overrides.pop(can_create_template, None)
        app.dependency_overrides.pop(check_create_storage_pool_availability, None)

    assert response.status_code == 200
    assert response.json() == {"id": "template-new"}


def test_duplicate_template(monkeypatch, test_client):
    from api import app
    from api.dependencies.alloweds import is_allowed_template_id
    from api.dependencies.quotas import can_create_template
    from api.dependencies.storage_pools import check_create_storage_pool_availability

    jwt = MockJWT(role_id="advanced")
    captured = {}

    def fake_duplicate(payload, template_id, data):
        captured["template_id"] = template_id
        captured["name"] = data.get("name")
        return "template-copy"

    monkeypatch.setattr(
        "api.services.templates.TemplateService.duplicate_template",
        staticmethod(fake_duplicate),
    )

    async def _noop():
        return None

    app.dependency_overrides[is_allowed_template_id] = _noop
    app.dependency_overrides[can_create_template] = _noop
    app.dependency_overrides[check_create_storage_pool_availability] = _noop
    try:
        response = test_client(
            url="/item/template/template-1/duplicate",
            method="POST",
            body={
                "name": "Copy of Template 1",
                "description": "Duplicate",
                "allowed": {"users": False, "groups": False},
                "enabled": True,
            },
            jwt=jwt,
        )
    finally:
        app.dependency_overrides.pop(is_allowed_template_id, None)
        app.dependency_overrides.pop(can_create_template, None)
        app.dependency_overrides.pop(check_create_storage_pool_availability, None)

    assert response.status_code == 200
    assert response.json() == {"id": "template-copy"}
    assert captured == {"template_id": "template-1", "name": "Copy of Template 1"}


def test_delete_template_sends_to_recycle_bin(monkeypatch, test_client):
    from api import app
    from api.dependencies.alloweds import owns_template_children

    jwt = MockJWT(role_id="advanced")
    captured = {}

    def fake_delete(payload, template_id):
        captured["template_id"] = template_id
        return None  # soft delete → 200 item.recycled

    monkeypatch.setattr(
        "api.services.templates.TemplateService.delete_template",
        staticmethod(fake_delete),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_domain_id",
        staticmethod(lambda payload, domain_id: domain_id),
    )
    monkeypatch.setattr(
        "api.dependencies.domains.Domain",
        _FakeDomainTemplate,
    )

    async def _noop():
        return None

    app.dependency_overrides[owns_template_children] = _noop
    try:
        response = test_client(
            url="/item/template/template-1",
            method="DELETE",
            jwt=jwt,
        )
    finally:
        app.dependency_overrides.pop(owns_template_children, None)

    assert response.status_code == 200
    assert response.json()["message_code"] == "item.recycled"
    assert captured == {"template_id": "template-1"}


def test_get_template_tree(monkeypatch, test_client):
    jwt = MockJWT(role_id="advanced")
    stub = {
        "domains": [
            {
                "id": "desktop-1",
                "kind": "desktop",
                "name": "Child Desktop",
                "user": "local-default-admin-admin",
            }
        ],
        "pending": False,
        "is_duplicated": False,
    }
    monkeypatch.setattr(
        "api.services.templates.TemplateService.get_template_tree",
        staticmethod(lambda template_id, payload: stub),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_domain_id",
        staticmethod(lambda payload, domain_id: domain_id),
    )
    monkeypatch.setattr(
        "api.dependencies.domains.Domain",
        _FakeDomainTemplate,
    )

    response = test_client(
        url="/item/template/template-1/get-tree",
        jwt=jwt,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["domains"][0]["id"] == "desktop-1"
    assert body["pending"] is False


def test_change_template_owner(monkeypatch, test_client):
    """PUT /item/template/{id}/change-owner/{user_id} — mirrors v3
    ``api_v3_template_change_owner`` (``CommonView.py:200``).
    Manager-tier route; service enforces ``ownsUserId`` +
    ``ownsDomainId`` before delegating to
    ``Helpers.change_owner_template``."""
    jwt = MockJWT()
    captured = {}

    def fake_change_owner(payload, template_id, new_user_id):
        captured["template_id"] = template_id
        captured["new_user_id"] = new_user_id
        captured["role_id"] = payload["role_id"]

    monkeypatch.setattr(
        "api.services.templates.TemplateService.change_owner",
        staticmethod(fake_change_owner),
    )

    response = test_client(
        url="/item/template/template-1/change-owner/user-target",
        method="PUT",
        jwt=jwt,
    )
    assert response.status_code == 200
    assert response.json() == {"id": "template-1"}
    assert captured == {
        "template_id": "template-1",
        "new_user_id": "user-target",
        "role_id": "admin",
    }
