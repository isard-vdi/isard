#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``ResourceItemsGpus.list_subitems`` / ``list_subitems_enabled`` guards +
behaviour.

* ``list_subitems`` -- missing card (``not_found``), missing profile catalog
  (``not_found``), and attaching the per-base ``variants`` list to each profile.
* ``list_subitems_enabled`` -- missing card / catalog (``not_found``) and
  returning only the profiles whose id is in ``profiles_enabled``.

Only rethink and ``_variants_by_base`` are stubbed; the real method decides.
Errors assert ``description_code``.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_base import ErrorBase


@pytest.fixture
def stub(monkeypatch):
    from isardvdi_common.lib.bookings import reservables as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.ResourceItemsGpus, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.ResourceItemsGpus),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    tables = {}

    def router(name):
        return tables.setdefault(name, MagicMock(name=f"table-{name}"))

    monkeypatch.setattr(mod.r, "table", MagicMock(side_effect=router))
    return {
        "mod": mod,
        "Cls": mod.ResourceItemsGpus,
        "router": router,
        "mp": monkeypatch,
    }


def _card(stub, item):
    stub["router"]("gpus").get.return_value.run.return_value = item


def _catalog(stub, profiles):
    gp = stub["router"]("gpu_profiles")
    gp.get_all.return_value.run.return_value = (
        [{"profiles": profiles}] if profiles is not None else []
    )


class TestListSubitems:
    def test_missing_card_not_found(self, stub):
        _card(stub, None)
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].list_subitems("nope")
        assert exc.value.error["description_code"] == "not_found"

    def test_missing_catalog_not_found(self, stub):
        _card(stub, {"brand": "NVIDIA", "model": "A40"})
        _catalog(stub, None)  # empty get_all -> [0] IndexError
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].list_subitems("g1")
        assert exc.value.error["error"] == "not_found"

    def test_attaches_variants_per_base(self, stub):
        _card(stub, {"brand": "NVIDIA", "model": "A40"})
        _catalog(stub, [{"id": "NVIDIA-A40-1Q"}, {"id": "NVIDIA-A40-2Q"}])
        stub["mp"].setattr(
            stub["Cls"],
            "_variants_by_base",
            classmethod(lambda cls: {"NVIDIA-A40-1Q": {"prod", "lab"}}),
        )
        result = stub["Cls"].list_subitems("g1")
        # Sorted variants attached to the matching base; empty list otherwise.
        assert result[0]["variants"] == ["lab", "prod"]
        assert result[1]["variants"] == []


class TestListSubitemsEnabled:
    def test_missing_card_not_found(self, stub):
        _card(stub, None)
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].list_subitems_enabled("nope")
        assert exc.value.error["description_code"] == "not_found"

    def test_missing_catalog_not_found(self, stub):
        _card(stub, {"brand": "NVIDIA", "model": "A40"})
        _catalog(stub, None)
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].list_subitems_enabled("g1")
        assert exc.value.error["description_code"] == "not_found"

    def test_returns_only_enabled(self, stub):
        _card(
            stub,
            {"brand": "NVIDIA", "model": "A40", "profiles_enabled": ["1Q", "4Q"]},
        )
        _catalog(stub, [{"id": "1Q"}, {"id": "2Q"}, {"id": "4Q"}])
        result = stub["Cls"].list_subitems_enabled("g1")
        assert [s["id"] for s in result] == ["1Q", "4Q"]
