# SPDX-License-Identifier: AGPL-3.0-or-later

"""Limits keep ``volatile``, and limits stored without it do not break the gate."""

import pytest
from isardvdi_common.helpers import quotas as mod
from isardvdi_common.helpers.error_base import ErrorBase
from isardvdi_common.schemas.shared.quotas import Limits

ERROR = {
    "error_description": "limits exceeded",
    "error_description_code": "limit_exceeded",
}

LIMITS_WITHOUT_VOLATILE = {
    "desktops": 5,
    "desktops_disk_size": 10,
    "isos": 5,
    "vcpus": 10,
    "memory": 20,
    "running": 5,
    "templates": 5,
    "users": 10,
    "total_size": 100,
    "total_soft_size": 90,
    "deployments_total": 5,
}


def test_limits_without_volatile_do_not_fail():
    mod.Quotas.check_limits({"limits": LIMITS_WITHOUT_VOLATILE}, "volatile", 3, ERROR)


def test_volatile_limit_blocks_when_exceeded():
    limits = {**LIMITS_WITHOUT_VOLATILE, "volatile": 2}
    with pytest.raises(ErrorBase):
        mod.Quotas.check_limits({"limits": limits}, "volatile", 3, ERROR)


def test_volatile_limit_at_zero_blocks():
    limits = {**LIMITS_WITHOUT_VOLATILE, "volatile": 0}
    with pytest.raises(ErrorBase):
        mod.Quotas.check_limits({"limits": limits}, "volatile", 1, ERROR)


def test_volatile_limit_allows_within_the_limit():
    limits = {**LIMITS_WITHOUT_VOLATILE, "volatile": 3}
    mod.Quotas.check_limits({"limits": limits}, "volatile", 3, ERROR)


def test_present_keys_are_still_enforced():
    with pytest.raises(ErrorBase):
        mod.Quotas.check_limits(
            {"limits": LIMITS_WITHOUT_VOLATILE}, "desktops", 6, ERROR
        )


def test_no_limits_do_not_fail():
    mod.Quotas.check_limits({"limits": False}, "volatile", 3, ERROR)


def test_limits_model_keeps_volatile_when_sent():
    dumped = Limits(**LIMITS_WITHOUT_VOLATILE, volatile=7).model_dump(exclude_none=True)
    assert dumped["volatile"] == 7


def test_limits_model_accepts_a_payload_without_volatile():
    dumped = Limits(**LIMITS_WITHOUT_VOLATILE).model_dump(exclude_none=True)
    assert "volatile" not in dumped


def test_limits_model_rejects_a_negative_volatile():
    with pytest.raises(ValueError):
        Limits(**LIMITS_WITHOUT_VOLATILE, volatile=-1)
