# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from api import app
from api.dependencies.quotas import (
    can_create_deployment,
    can_create_desktop,
    can_create_media,
    can_create_template,
)
from api.routes.tests.helpers import MockJWT


def test_quota_media_ok(monkeypatch, test_client):
    jwt = MockJWT()

    async def mock_can_create_media():
        return True

    app.dependency_overrides[can_create_media] = mock_can_create_media

    try:
        response = test_client(
            url="/quota/media/new",
            jwt=jwt,
        )
        assert response.status_code == 204
    finally:
        app.dependency_overrides.pop(can_create_media, None)


def test_quota_desktop_ok(monkeypatch, test_client):
    jwt = MockJWT()

    async def mock_can_create_desktop():
        return True

    app.dependency_overrides[can_create_desktop] = mock_can_create_desktop

    try:
        response = test_client(
            url="/quota/desktop/new",
            jwt=jwt,
        )
        assert response.status_code == 204
    finally:
        app.dependency_overrides.pop(can_create_desktop, None)


def test_quota_template_ok(monkeypatch, test_client):
    jwt = MockJWT()

    async def mock_can_create_template():
        return True

    app.dependency_overrides[can_create_template] = mock_can_create_template

    try:
        response = test_client(
            url="/quota/template/new",
            jwt=jwt,
        )
        assert response.status_code == 204
    finally:
        app.dependency_overrides.pop(can_create_template, None)


def test_quota_deployment_ok(monkeypatch, test_client):
    jwt = MockJWT()

    async def mock_can_create_deployment():
        return True

    app.dependency_overrides[can_create_deployment] = mock_can_create_deployment

    try:
        response = test_client(
            url="/quota/deployment/new",
            jwt=jwt,
        )
        assert response.status_code == 204
    finally:
        app.dependency_overrides.pop(can_create_deployment, None)


# ─── Admin quota lookup (manager_router) ─────────────────────────────────
# Cover the /admin/quota/{kind}[/{item_id}] routes that replaced the
# v3_compat /quota/{kind}[/{item_id}] shim. The routes call
# Quotas.GetUserQuota / GetCategoryQuota / GetGroupQuota on the common
# helper; tests monkeypatch those classmethods so the common-lib DB
# layer is never hit.


@pytest.mark.clear_cache
def test_admin_quota_by_kind_user_defaults_to_caller(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    stub = {"quota": {"desktops": 10}, "limits": False}

    def fake_get_user_quota(target):
        calls.append(target)
        return stub

    monkeypatch.setattr(
        "isardvdi_common.helpers.quotas.Quotas.GetUserQuota",
        staticmethod(fake_get_user_quota),
    )

    response = test_client(url="/admin/quota/user", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub
    # item_id omitted → route falls back to the caller's own user_id
    assert calls == [jwt.payload["user_id"]]


@pytest.mark.clear_cache
def test_admin_quota_by_kind_item_category(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    stub = {"quota": {"desktops": 42}, "limits": {"desktops": 100}}

    def fake_get_category_quota(target):
        calls.append(target)
        return stub

    monkeypatch.setattr(
        "isardvdi_common.helpers.quotas.Quotas.GetCategoryQuota",
        staticmethod(fake_get_category_quota),
    )

    response = test_client(url="/admin/quota/category/cat-1", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub
    assert calls == ["cat-1"]


def test_admin_quota_by_kind_invalid(test_client):
    jwt = MockJWT()
    response = test_client(url="/admin/quota/banana", jwt=jwt)
    assert response.status_code == 400
