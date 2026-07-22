# SPDX-License-Identifier: AGPL-3.0-or-later

"""Quota endpoint contract tests against a live stack.

Pins the wire shape of the six quota endpoints that the webapp + both
Vue frontends read. These are pure GETs with no mutation, so they
don't need ``@pytest.mark.slow`` and don't write into the namespace.

Endpoints under test:
    GET  /api/v4/admin/quota/{kind}                 (manager_router)
    GET  /api/v4/admin/quota/{kind}/{item_id}       (manager_router)
    GET  /api/v4/quota/desktop/new                  (token_router, 204|428)
    GET  /api/v4/quota/media/new                    (advanced_router, 204|428)
    GET  /api/v4/quota/template/new                 (advanced_router, 204|428)
    GET  /api/v4/quota/deployment/new               (advanced_router, 204|428)

The purpose is to catch regressions where:
- a service transform drops the ``quota`` or ``limits`` key,
- ``grouplimits`` disappears from group lookups,
- the quota-check endpoints start returning 200 with a body instead
  of a bare 204, which the Vue ``canCreate*`` gates treat as an error.
"""

from __future__ import annotations

import pytest

from .helpers.client import IsardClient

QUOTA_CHECK_ENDPOINTS = (
    "/api/v4/quota/desktop/new",
    "/api/v4/quota/media/new",
    "/api/v4/quota/template/new",
    "/api/v4/quota/deployment/new",
)


def _assert_quota_shape(body: dict) -> None:
    """Every admin-quota response must have ``quota`` and ``limits``.

    Both can be ``dict`` or ``False`` (the common ``Quotas`` helper uses
    ``False`` as the "not configured" sentinel). ``grouplimits`` is
    optional and only appears on group lookups.
    """
    assert isinstance(body, dict), f"expected dict, got {type(body).__name__}"
    assert "quota" in body, f"missing 'quota' key; got {sorted(body)}"
    assert "limits" in body, f"missing 'limits' key; got {sorted(body)}"
    assert isinstance(
        body["quota"], (dict, bool)
    ), f"quota must be dict or bool, got {type(body['quota']).__name__}"
    assert isinstance(
        body["limits"], (dict, bool)
    ), f"limits must be dict or bool, got {type(body['limits']).__name__}"


@pytest.mark.real
def test_admin_quota_user_returns_shape(admin_client: IsardClient):
    """GET /admin/quota/user — own-entity lookup. Must return the
    admin's quota/limits pair without needing an item_id."""
    body = admin_client.get("/api/v4/admin/quota/user")
    _assert_quota_shape(body)


@pytest.mark.real
def test_admin_quota_user_by_id_returns_shape(admin_client: IsardClient):
    """GET /admin/quota/user/{id} — explicit-entity lookup.

    Uses the logged-in admin's own user_id so the test doesn't depend
    on any seed beyond the admin itself.
    """
    assert admin_client.user_id, "admin_client.login() must populate user_id"
    body = admin_client.get(f"/api/v4/admin/quota/user/{admin_client.user_id}")
    _assert_quota_shape(body)


@pytest.mark.real
def test_admin_quota_category_default_returns_shape(admin_client: IsardClient):
    """GET /admin/quota/category/default — default category is always
    seeded by populate.py, so this is a stable fixture."""
    body = admin_client.get("/api/v4/admin/quota/category/default")
    _assert_quota_shape(body)


@pytest.mark.real
def test_admin_quota_group_default_returns_shape(admin_client: IsardClient):
    """GET /admin/quota/group/default-default — default-default is the
    auto-created group under the default category. Pins the ``grouplimits``
    field presence (key MUST exist on group lookups; may be False)."""
    body = admin_client.get("/api/v4/admin/quota/group/default-default")
    _assert_quota_shape(body)
    # grouplimits is the marker that distinguishes group from category/user.
    # It MUST be in the dict; its value may be False or a dict.
    assert (
        "grouplimits" in body
    ), f"group lookup must include 'grouplimits' key; got {sorted(body)}"
    assert isinstance(body["grouplimits"], (dict, bool)) or body["grouplimits"] is None


@pytest.mark.real
@pytest.mark.parametrize("path", QUOTA_CHECK_ENDPOINTS)
def test_quota_check_new_returns_204_for_admin(admin_client: IsardClient, path: str):
    """``/quota/{kind}/new`` returns 204 when the caller is under quota.

    The default admin has no quota configured and is well under any
    limit the test stack could seed. A 204 with empty body is the
    success contract; frontends treat a non-204 response as "quota
    exceeded" and disable the create buttons.
    """
    resp = admin_client.raw("GET", path)
    assert (
        resp.status_code == 204
    ), f"expected 204 from {path}, got {resp.status_code}; body={resp.text[:200]}"
    assert (
        not resp.content
    ), f"{path} must return an empty body on 204; got {resp.text[:200]}"
