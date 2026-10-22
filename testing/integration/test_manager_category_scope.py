# SPDX-License-Identifier: AGPL-3.0-or-later

"""A manager reads the applied quota and template tree of its own category only."""

from __future__ import annotations

import os

import pytest

from .helpers.client import IsardClient

pytestmark = pytest.mark.real

MANAGER01 = (
    "manager01",
    os.environ.get("E2E_MANAGER01_PASSWORD", "LB`*F9Uw"),
    "default",
)
MANAGER02 = (
    "manager02",
    os.environ.get("E2E_MANAGER02_PASSWORD", "LxlE5sp`"),
    "07962917-9649-436e-b103-559c36c04afd",
)
USER01_ID = "4dffb235-8293-4e40-b661-25ab33cf1781"
DEFAULT_TEMPLATE_ID = "template-parity-own"


def _login(creds) -> IsardClient:
    client = IsardClient()
    client.login(creds[0], creds[1], category_id=creds[2])
    return client


@pytest.fixture(scope="module")
def foreign_manager() -> IsardClient:
    return _login(MANAGER02)


@pytest.fixture(scope="module")
def own_manager() -> IsardClient:
    return _login(MANAGER01)


def test_a_manager_cannot_read_the_applied_quota_of_another_categorys_user(
    foreign_manager,
):
    resp = foreign_manager.raw(
        "GET", f"/api/v4/admin/item/user/appliedquota/{USER01_ID}"
    )
    assert resp.status_code == 403, resp.text


def test_a_manager_cannot_read_the_tree_of_another_categorys_template(
    foreign_manager,
):
    resp = foreign_manager.raw(
        "GET", f"/api/v4/admin/items/desktops/tree_list/{DEFAULT_TEMPLATE_ID}"
    )
    assert resp.status_code == 403, resp.text


def test_a_manager_still_reads_both_in_its_own_category(own_manager):
    quota = own_manager.raw("GET", f"/api/v4/admin/item/user/appliedquota/{USER01_ID}")
    tree = own_manager.raw(
        "GET", f"/api/v4/admin/items/desktops/tree_list/{DEFAULT_TEMPLATE_ID}"
    )
    assert quota.status_code == 200, quota.text
    assert tree.status_code == 200, tree.text
