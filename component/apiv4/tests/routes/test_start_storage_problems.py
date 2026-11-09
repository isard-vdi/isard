# SPDX-License-Identifier: AGPL-3.0-or-later

"""A start refused because its disks are not ready queues their quick fixes first."""

import asyncio

import pytest
from api.dependencies import storage_pools
from api.services.error import Error


@pytest.fixture
def handled(monkeypatch):
    calls = []
    monkeypatch.setattr(
        storage_pools.StorageProblemsService,
        "handle_quietly",
        staticmethod(lambda payload, desktop_id: calls.append(desktop_id)),
    )
    return calls


def _refuse(code):
    def check(domain_id):
        raise Error("precondition_required", "refused", description_code=code)

    return check


def _check(payload=None):
    return asyncio.run(
        storage_pools.check_virt_storage_pool_availability(
            payload=payload or {"user_id": "u1", "role_id": "user"}, desktop_id="d1"
        )
    )


def test_a_disk_not_ready_is_handled_and_the_start_error_kept(monkeypatch, handled):
    monkeypatch.setattr(
        storage_pools.HypervisorsProcessed,
        "check_virt_storage_pool_availability",
        staticmethod(_refuse("desktop_storage_not_ready")),
    )
    with pytest.raises(Error) as raised:
        _check()
    assert raised.value.error["description_code"] == "desktop_storage_not_ready"
    assert handled == ["d1"]


def test_other_refusals_leave_the_disks_alone(monkeypatch, handled):
    monkeypatch.setattr(
        storage_pools.HypervisorsProcessed,
        "check_virt_storage_pool_availability",
        staticmethod(_refuse("no_storage_pool_available")),
    )
    with pytest.raises(Error):
        _check()
    assert handled == []


def test_an_available_pool_passes(monkeypatch, handled):
    monkeypatch.setattr(
        storage_pools.HypervisorsProcessed,
        "check_virt_storage_pool_availability",
        staticmethod(lambda domain_id: "pool1"),
    )
    assert _check() == "pool1"
    assert handled == []
