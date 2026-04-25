# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for Pydantic model field types in isardvdi_common.

These models are constructed by apiv4 + change-handler + engine. The
field types must accept every value the codebase actually writes to
the corresponding DB columns, otherwise loading any pre-existing row
through the model raises pydantic.ValidationError.

The cases covered here are the ones fixed in the "fix(common): correct
pydantic types for hyp lists and category quota" commit:

- DomainModel.forced_hyp / favourite_hyp accept ``False | list[str] |
  None`` (the DB convention set by ``engine/initdb/upgrade.py:144,201``
  is False or a list of hypervisor IDs).
- CategoryModel.quota accepts ``False | dict | None`` (set by
  ``isardvdi_common.lib.users.categories.update_category_quota`` and
  ``isardvdi_common.helpers.user_storage`` to either False or a
  role-keyed dict).
- CategoryModel.limits accepts ``False | dict | None`` (set by
  ``isardvdi_common.lib.users.categories.update_category_limits`` to
  either False or a limits dict; readers iterate ``limits.items()``).
"""

import pytest
from isardvdi_common.models.category import CategoryModel
from isardvdi_common.models.domain import DomainModel
from isardvdi_common.schemas.domains import DesktopStatusEnum, DomainKindEnum
from pydantic import ValidationError


def _make_domain(**overrides):
    base = {
        "category": "default",
        "group": "default-default",
        "kind": DomainKindEnum.desktop,
        "name": "test-desktop",
        "persistent": True,
        "status": DesktopStatusEnum.stopped,
    }
    base.update(overrides)
    return DomainModel(**base)


def _make_category(**overrides):
    base = {
        "custom_url_name": "default",
        "frontend": True,
        "name": "Default",
        "uid": "default",
    }
    base.update(overrides)
    return CategoryModel(**base)


class TestDomainModelHypFields:
    """forced_hyp / favourite_hyp must accept the same shapes the DB stores."""

    @pytest.mark.parametrize(
        "value",
        [
            False,
            None,
            [],
            ["hyp-1"],
            ["hyp-1", "hyp-2", "hyp-3"],
        ],
    )
    def test_forced_hyp_accepts_supported_shapes(self, value):
        domain = _make_domain(forced_hyp=value)
        assert domain.forced_hyp == value

    @pytest.mark.parametrize(
        "value",
        [
            False,
            None,
            [],
            ["hyp-1"],
            ["hyp-1", "hyp-2"],
        ],
    )
    def test_favourite_hyp_accepts_supported_shapes(self, value):
        domain = _make_domain(favourite_hyp=value)
        assert domain.favourite_hyp == value

    def test_forced_hyp_rejects_dict(self):
        with pytest.raises(ValidationError):
            _make_domain(forced_hyp={"hyp-1": True})

    def test_favourite_hyp_rejects_dict(self):
        with pytest.raises(ValidationError):
            _make_domain(favourite_hyp={"hyp-1": True})


class TestCategoryModelQuota:
    """quota must accept False or a dict (role-keyed quota config)."""

    def test_quota_default_is_false(self):
        category = _make_category()
        assert category.quota is False

    def test_quota_accepts_false(self):
        category = _make_category(quota=False)
        assert category.quota is False

    def test_quota_accepts_none(self):
        category = _make_category(quota=None)
        assert category.quota is None

    def test_quota_accepts_dict(self):
        quota_value = {
            "user": {"desktops": 5, "running": 2},
            "manager": {"desktops": 50, "running": 20},
        }
        category = _make_category(quota=quota_value)
        assert category.quota == quota_value

    def test_quota_rejects_string(self):
        with pytest.raises(ValidationError):
            _make_category(quota="unlimited")

    def test_quota_rejects_int(self):
        with pytest.raises(ValidationError):
            _make_category(quota=42)


class TestCategoryModelLimits:
    """limits must accept False or a dict (limits config)."""

    def test_limits_default_is_false(self):
        category = _make_category()
        assert category.limits is False

    def test_limits_accepts_false(self):
        category = _make_category(limits=False)
        assert category.limits is False

    def test_limits_accepts_none(self):
        category = _make_category(limits=None)
        assert category.limits is None

    def test_limits_accepts_dict(self):
        limits_value = {
            "desktops": 10,
            "running": 5,
            "total_size": 9999,
            "total_soft_size": 9000,
        }
        category = _make_category(limits=limits_value)
        assert category.limits == limits_value

    def test_limits_rejects_string(self):
        with pytest.raises(ValidationError):
            _make_category(limits="unlimited")

    def test_limits_rejects_int(self):
        with pytest.raises(ValidationError):
            _make_category(limits=42)
