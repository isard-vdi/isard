# SPDX-License-Identifier: AGPL-3.0-or-later

"""The start/create availability gate must not count a ``degraded`` or an
``only_forced`` hypervisor as available.

Both keep ``status == "Online"`` (degradation is "still connected, just slow";
only_forced means "takes forced placements only"), but the engine balancer
drops both, so a gate that only looks at ``status``/``enabled`` says "available"
and lets a start/create through that the balancer can then place nowhere.
"""

import isardvdi_common.lib.hypervisors.hypervisors as mod
import pytest
from isardvdi_common.helpers.error_base import ErrorBase
from isardvdi_common.lib.hypervisors.hypervisors import HypervisorsProcessed

POOL = "pool-x"


def _hyper(**over):
    h = {
        "id": "h1",
        "status": "Online",
        "enabled": True,
        "enabled_virt_pools": [POOL],
        "enabled_storage_pools": [POOL],
    }
    h.update(over)
    return h


def _set_online(monkeypatch, hypers):
    monkeypatch.setattr(
        mod.Caches,
        "get_cached_hypervisors_online",
        classmethod(lambda cls: list(hypers)),
    )
    HypervisorsProcessed.clear_check_virt_storage_pool_availability_cache()
    HypervisorsProcessed.clear_check_create_storage_pool_availability_cache()


@pytest.fixture(autouse=True)
def _pools(monkeypatch):
    monkeypatch.setattr(
        mod.Domain,
        "get_cached_available_domain_storage_pool_id",
        classmethod(lambda cls, domain_id: POOL),
    )
    monkeypatch.setattr(
        mod.Caches,
        "get_cached_available_category_storage_pool_id",
        classmethod(lambda cls, category_id: POOL),
    )
    yield
    HypervisorsProcessed.clear_check_virt_storage_pool_availability_cache()
    HypervisorsProcessed.clear_check_create_storage_pool_availability_cache()


def test_a_healthy_online_hypervisor_is_available(monkeypatch):
    _set_online(monkeypatch, [_hyper()])
    assert HypervisorsProcessed.check_virt_storage_pool_availability("d1") is True
    assert HypervisorsProcessed.check_create_storage_pool_availability("c1") is True


def test_the_only_hypervisor_being_only_forced_is_not_available(monkeypatch):
    _set_online(monkeypatch, [_hyper(only_forced=True)])
    with pytest.raises(ErrorBase) as exc:
        HypervisorsProcessed.check_virt_storage_pool_availability("d1")
    assert exc.value.error["description_code"] == "no_storage_pool_available"
    HypervisorsProcessed.clear_check_create_storage_pool_availability_cache()
    with pytest.raises(ErrorBase):
        HypervisorsProcessed.check_create_storage_pool_availability("c1")


def test_the_only_hypervisor_being_degraded_is_not_available(monkeypatch):
    _set_online(monkeypatch, [_hyper(degraded={"is_degraded": True, "reason": "slow"})])
    with pytest.raises(ErrorBase) as exc:
        HypervisorsProcessed.check_virt_storage_pool_availability("d1")
    assert exc.value.error["description_code"] == "no_storage_pool_available"
    HypervisorsProcessed.clear_check_create_storage_pool_availability_cache()
    with pytest.raises(ErrorBase):
        HypervisorsProcessed.check_create_storage_pool_availability("c1")


def test_a_healthy_hypervisor_still_counts_past_a_degraded_or_forced_one(monkeypatch):
    """One bad hypervisor must not hide a good one: availability still holds."""
    _set_online(
        monkeypatch,
        [
            _hyper(id="bad1", only_forced=True),
            _hyper(id="bad2", degraded={"is_degraded": True, "reason": "slow"}),
            _hyper(id="good"),
        ],
    )
    assert HypervisorsProcessed.check_virt_storage_pool_availability("d1") is True
    assert HypervisorsProcessed.check_create_storage_pool_availability("c1") is True
