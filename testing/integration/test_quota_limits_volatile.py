# SPDX-License-Identifier: AGPL-3.0-or-later

"""Category limits keep ``volatile``, and the temporary desktop gate tolerates its absence."""

from __future__ import annotations

import time
from typing import Callable, Iterator

import pytest

from .helpers.client import IsardClient

CATEGORY = "default"
VOLATILE_GATE = "/api/v4/quota/desktop/new-volatile"

# every field Limits requires, generous enough that no other check blocks
LIMITS_WITHOUT_VOLATILE = {
    "desktops": 999,
    "desktops_disk_size": 999999,
    "isos": 999,
    "vcpus": 999,
    "memory": 999999,
    "running": 999,
    "templates": 999,
    "users": 999,
    "total_size": 999999,
    "total_soft_size": 999999,
    "deployments_total": 999,
}


def _set_category_limits(admin_client: IsardClient, limits) -> None:
    resp = admin_client.raw(
        "PUT",
        f"/api/v4/admin/item/limits/category/{CATEGORY}",
        json={"limits": limits},
    )
    assert resp.status_code in (
        200,
        204,
    ), f"set category limits -> {resp.status_code}: {resp.text[:200]}"


def _eventually(probe: Callable[[], object], expected, timeout: float = 20.0):
    # the quota helpers sit behind short TTL caches, so a write is not visible at once
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = probe()
        if last == expected:
            return last
        time.sleep(1)
    return last


@pytest.fixture
def restore_limits_after(admin_client: IsardClient) -> Iterator[None]:
    try:
        yield
    finally:
        try:
            _set_category_limits(admin_client, False)
        except Exception:  # pragma: no cover
            pass


@pytest.mark.real
def test_category_limits_keep_volatile(admin_client: IsardClient, restore_limits_after):
    _set_category_limits(admin_client, {**LIMITS_WITHOUT_VOLATILE, "volatile": 7})

    def stored():
        limits = admin_client.get(f"/api/v4/admin/quota/category/{CATEGORY}")["limits"]
        return (limits or {}).get("volatile")

    assert _eventually(stored, 7) == 7


@pytest.mark.real
def test_volatile_gate_allows_when_limits_lack_volatile(
    admin_client: IsardClient, restore_limits_after
):
    _set_category_limits(admin_client, LIMITS_WITHOUT_VOLATILE)

    status = _eventually(
        lambda: admin_client.raw("GET", VOLATILE_GATE).status_code, 204
    )
    assert status == 204, f"temporary desktop gate -> {status}"


@pytest.mark.real
def test_volatile_gate_blocks_when_the_limit_is_reached(
    admin_client: IsardClient, restore_limits_after
):
    _set_category_limits(admin_client, {**LIMITS_WITHOUT_VOLATILE, "volatile": 0})

    def blocked():
        return admin_client.raw("GET", VOLATILE_GATE).status_code in (412, 428)

    assert _eventually(blocked, True), "temporary desktop gate did not block"
