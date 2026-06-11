# SPDX-License-Identifier: AGPL-3.0-or-later

"""Quota lifecycle: tighten → exhaust → 412 → release → 204.

The contract tests in ``test_quota_contract.py`` only check that the
quota endpoints return shaped JSON / 204 for an unconstrained admin.
That covers the wire shape but not the actual gating behavior the
frontends and webapp rely on.

This file exercises the end-to-end gate by tightening quota on the
default user-category, creating a user-owned desktop until the
``/quota/desktop/new`` gate flips from 204 (allowed) to 412
(precondition_required) for the seeded ``user01``, then releases the
quota and re-asserts 204. The same pattern applies to ``deployment``
and ``template`` kinds.

The test restores the default category quota at teardown so it stays
idempotent across runs — including when the previous run aborted
before the restore step.
"""

from __future__ import annotations

import os
import time
from typing import Iterator, Optional

import pytest
from isardvdi_apiv4_client.api.role_admin import admin_update_category_quota
from isardvdi_apiv4_client.api.role_manager import admin_get_templates
from isardvdi_apiv4_client.api.role_user import (
    admin_allowed_update,
    check_quota_new_desktop,
    create_desktop,
    get_user_allowed_templates_flat,
)
from isardvdi_apiv4_client.models.admin_allowed_update_table import (
    AdminAllowedUpdateTable,
)
from isardvdi_apiv4_client.models.admin_quota_update_data import AdminQuotaUpdateData
from isardvdi_apiv4_client.models.allowed_update_request import AllowedUpdateRequest
from isardvdi_apiv4_client.models.allowed_update_request_allowed import (
    AllowedUpdateRequestAllowed,
)
from isardvdi_apiv4_client.models.create_desktop_request import CreateDesktopRequest
from isardvdi_apiv4_client.models.get_user_allowed_templates_flat_kind import (
    GetUserAllowedTemplatesFlatKind,
)
from isardvdi_apiv4_client.models.quota import Quota

from .helpers.client import IsardClient
from .helpers.responses import created_id, expect

USER01_USERNAME = os.environ.get("E2E_USER01_USERNAME", "user01")
USER01_PASSWORD = os.environ.get("E2E_USER01_PASSWORD", "a?)49hgT")
USER01_CATEGORY = os.environ.get("E2E_USER01_CATEGORY", "default")


def _user_client() -> IsardClient:
    """Return a fresh authenticated client for the seeded ``user01``.

    Each call logs in (separate session, separate JWT), so the user
    client and admin client never share a token. Required for quota
    tests because role+limits are read from the JWT on every request.
    """
    client = IsardClient()
    client.login(USER01_USERNAME, USER01_PASSWORD, category_id=USER01_CATEGORY)
    return client


_FULL_QUOTA = {
    "desktops": 999,
    "volatile": 999,
    "running": 999,
    "memory": 999999999,
    "vcpus": 999,
    "isos": 999,
    "templates": 999,
    "users": 999,
    "media_size": 999999,
    "total_size": 999999,
    "total_soft_size": 999999,
    "desktops_disk_size": 999999,
    "deployments_total": 999,
    "deployment_desktops": 999,
    "deployment_users": 999,
    "started_deployment_desktops": 999,
}


def _set_category_quota(
    admin_client: IsardClient, category_id: str, quota: dict, propagate: bool
) -> None:
    # apiv4 models the quota object as the typed Quota model; building it
    # from the raw dict keeps any unknown keys in additional_properties.
    resp = admin_update_category_quota.sync_detailed(
        category_id=category_id,
        client=admin_client.apiv4(),
        body=AdminQuotaUpdateData(
            quota=Quota.from_dict(quota),
            propagate=propagate,
        ),
    )
    assert resp.status_code in (
        200,
        204,
    ), f"set category quota -> {resp.status_code}: {resp.content[:200]!r}"


def _quota_gate_new_desktop(client: IsardClient) -> int:
    """Status of the ``/quota/desktop/new`` gate (204 allowed, 412/428 full)."""
    return check_quota_new_desktop.sync_detailed(client=client.apiv4()).status_code


def _restore_default_quota(admin_client: IsardClient) -> None:
    """Reset default category quota to "no limits" — the populate.py
    seed shape — so the next test run starts from a clean slate.

    Must include every field the apiv4 ``UserQuota`` schema enforces;
    otherwise propagated user quotas come back malformed and break
    ``GET /item/user/get-quotas``.
    """
    _set_category_quota(admin_client, "default", _FULL_QUOTA, True)


@pytest.fixture
def restore_quota_after(admin_client: IsardClient) -> Iterator[None]:
    """Always restore the default category quota at teardown — even
    when the test aborts mid-way — so re-runs are idempotent."""
    try:
        yield
    finally:
        try:
            _restore_default_quota(admin_client)
        except Exception:  # pragma: no cover
            # Teardown must never mask a real test failure.
            pass


def _count_user_desktops(user_client: IsardClient) -> int:
    rows = user_client.get("/api/v4/items/desktops")
    if isinstance(rows, dict):
        rows = rows.get("desktops") or []
    return len(rows or [])


def _assert_quota_check(
    client: IsardClient, path: str, expect_status: int, msg_suffix: str = ""
) -> None:
    status = _quota_gate_new_desktop(client)
    assert (
        status == expect_status
    ), f"{path} {msg_suffix}: expected {expect_status}, got {status}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.real
@pytest.mark.slow
def test_desktop_quota_gate_flips_when_exhausted(
    admin_client: IsardClient,
    test_namespace: str,
    restore_quota_after,
):
    """Tighten the default category quota to ``desktops=N`` (where
    N == current user01 desktop count + 1) and verify the
    ``/quota/desktop/new`` gate goes:

        * 204 (allowed) — user01 has fewer than N desktops
        * after creating one to reach the limit, 412
          (precondition_required) — the next create would exceed the
          quota.

    Pins the canCreate gate the Vue 2 + Vue 3 + webapp UIs all check
    before enabling the "New desktop" button.
    """
    user_client = _user_client()
    pre_count = _count_user_desktops(user_client)
    target = pre_count + 1

    # --- 1: confirm the user is currently under the (default) quota ---
    _assert_quota_check(
        user_client, "/api/v4/quota/desktop/new", 204, "before tightening"
    )

    # --- 2: tighten the category quota. propagate=True flows down to
    # all groups in the category so every user is gated, not just newly
    # created ones. We keep all other fields at the comfortable
    # ceiling and only constrain ``desktops``.
    _set_category_quota(
        admin_client, "default", {**_FULL_QUOTA, "desktops": target}, True
    )
    # Bust the per-process Caches (Quotas reads from the same TTLCache
    # the categories pluck does); even a small wait gives the apiv4
    # cache a chance to settle.
    time.sleep(2)

    # --- 3: still allowed (we set target = current + 1) ---
    _assert_quota_check(
        user_client, "/api/v4/quota/desktop/new", 204, "with one slot left"
    )

    # --- 4: create one more desktop on user01's behalf (admin uses
    # /admin/domains/<user_id> to enumerate; the user_client side does
    # the create). Use the from-template fast-path to avoid an ISO
    # download — any seeded template suffices.
    # Basic-role users use ``/items/templates/allowed/all`` — the
    # advanced-role-only ``/items/templates`` endpoint 403s for them.
    templates = expect(
        get_user_allowed_templates_flat.sync_detailed(
            kind=GetUserAllowedTemplatesFlatKind.ALL, client=user_client.apiv4()
        )
    )
    assert isinstance(templates, list)
    if not templates:
        # Make the seeded admin template allowed-for-all temporarily so
        # user01 can derive a desktop. ``/admin/items/templates`` is
        # the admin-scoped listing — ``/items/templates`` filters by
        # the caller's allowed-list (so admin_e2e_01 sees nothing if
        # no template has them in ``allowed``).
        admin_templates = expect(
            admin_get_templates.sync_detailed(client=admin_client.apiv4())
        )
        assert isinstance(admin_templates, list)
        if not admin_templates:
            pytest.skip("no admin templates seeded; cannot exhaust quota")
        seed_template = admin_templates[0]
        # ``allowed.users == False`` means "not configured" (not "any
        # user"). Use ``/item/allowed/update/domains`` to set
        # ``categories: ["default"]`` — the only encoding that resolves
        # to "every member of the default category" through
        # ``Alloweds.is_allowed``.
        admin_allowed_update.sync_detailed(
            table=AdminAllowedUpdateTable.DOMAINS,
            client=admin_client.apiv4(),
            body=AllowedUpdateRequest(
                id=seed_template.id,
                allowed=AllowedUpdateRequestAllowed.from_dict(
                    {
                        "users": False,
                        "groups": False,
                        "categories": ["default"],
                        "roles": False,
                    }
                ),
            ),
        )
        templates = expect(
            get_user_allowed_templates_flat.sync_detailed(
                kind=GetUserAllowedTemplatesFlatKind.ALL, client=user_client.apiv4()
            )
        )
        assert isinstance(templates, list)
        assert (
            templates
        ), "after relaxing template allowed, user01 still sees no templates"
    template_id = templates[0].id
    new_desktop_name = f"{test_namespace}quota_user01_desk"
    created_id(
        create_desktop.sync_detailed(
            client=user_client.apiv4(),
            body=CreateDesktopRequest(
                template_id=template_id,
                name=new_desktop_name,
                description="quota lifecycle",
            ),
        )
    )
    # Pollution-free: don't wait for Stopped here, the quota check
    # lives on the row-count, not the row-status.

    # --- 5: now AT the limit — gate must reject ---
    # Allow a brief settle for the Quotas TTLCache invalidation.
    deadline = time.monotonic() + 15.0
    last_status: Optional[int] = None
    while time.monotonic() < deadline:
        last_status = _quota_gate_new_desktop(user_client)
        if last_status in (412, 428):
            break
        time.sleep(1)
    assert last_status in (412, 428), (
        f"expected /quota/desktop/new to flip to 412/428 after exhaustion; "
        f"got {last_status}"
    )

    # --- 6: release quota, gate flips back to 204 ---
    _restore_default_quota(admin_client)
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if _quota_gate_new_desktop(user_client) == 204:
            break
        time.sleep(1)
    _assert_quota_check(user_client, "/api/v4/quota/desktop/new", 204, "after release")


@pytest.mark.real
def test_admin_quota_endpoints_round_trip(admin_client: IsardClient):
    """Pin the admin quota CRUD path. PUT a full quota dict on the
    default category, then GET the category back and verify the new
    numbers are echoed. Restores the seed quota afterwards.

    Frontends rely on the round-trip — they POST the fully-populated
    form back, then refresh the listing to pick up the canonical shape.
    """
    fresh_quota = {
        "desktops": 7,
        "volatile": 7,
        "running": 7,
        "memory": 7000000,
        "vcpus": 7,
        "isos": 7,
        "templates": 7,
        "users": 7,
        "media_size": 70,
        "total_size": 70,
        "total_soft_size": 70,
        "desktops_disk_size": 70,
        "deployments_total": 7,
        "deployment_desktops": 7,
        "deployment_users": 7,
        "started_deployment_desktops": 7,
    }
    try:
        _set_category_quota(admin_client, "default", fresh_quota, False)
        time.sleep(1)
        body = admin_client.get("/api/v4/admin/quota/category/default")
        # Quota readback can be either ``False`` (no quota) or a dict;
        # after a PUT we expect a dict carrying our values.
        assert isinstance(
            body.get("quota"), dict
        ), f"after PUT category quota dict, GET must return dict; got {body.get('quota')!r}"
        for key, want in fresh_quota.items():
            got = body["quota"].get(key)
            assert got == want, (
                f"quota field {key!r} round-trip mismatch: " f"PUT {want}, GET {got}"
            )
    finally:
        _restore_default_quota(admin_client)
