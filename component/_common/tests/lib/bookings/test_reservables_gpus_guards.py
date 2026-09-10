#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guard-path tests for ``ResourceItemsGpus`` in
``isardvdi_common.lib.bookings.reservables``.

Covers the validation / not-found / failure guards of:

* ``enable_subitem``        -- variant validation and cross-profile variant
                               clash, the two guards that fire before the
                               per-resource lock,
* ``add_reservable_vgpu``   -- missing profile, failed insert,
* ``list_subitems_enabled`` -- missing card, missing profile catalog, and the
                               enabled-only filtering the method promises.

Everything ``enable_subitem`` does from the card lookup onwards runs inside a
real Redis lease, so those cases live in
``testing/integration/redis/common/test_reservables_gpus_locking.py``.

The function under test is always the real one; only the rdb surface and the
sibling collaborators it delegates to at the tail are controlled.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def gpu_stub(monkeypatch):
    """Stub the rdb surface with a per-table-name router.

    ``tables[name]`` returns a stable MagicMock for ``r.table(name)`` so a test
    can set return values on ``r.table("gpus")`` independently of
    ``r.table("reservables_vgpus")``.
    """
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
    clear_cache = MagicMock(name="clear_admin_table_list_cache")
    monkeypatch.setattr(mod.ApiAdmin, "clear_admin_table_list_cache", clear_cache)
    return {
        "mod": mod,
        "Cls": mod.ResourceItemsGpus,
        "tables": tables,
        "router": router,
        "monkeypatch": monkeypatch,
        "clear_cache": clear_cache,
    }


def _status(exc):
    return getattr(exc.value, "status_code", None)


# --------------------------------------------------------------------------- #
# enable_subitem guards
# --------------------------------------------------------------------------- #
class TestEnableSubitemGuards:
    def test_invalid_variant_name_rejected(self, gpu_stub):
        # "BAD!" is not 1-20 lowercase alphanumerics -> bad_request, and the
        # malformed label never reaches any id/suffix parsing (no table read).
        with pytest.raises(Exception) as exc:
            gpu_stub["Cls"].enable_subitem("gpu-1", "NVIDIA-A40-1Q~BAD!", True)
        assert _status(exc) == 400
        assert "gpus" not in gpu_stub["tables"]

    def test_variant_clash_with_different_base_rejected(self, gpu_stub):
        # A "~lab" already attached to a DIFFERENT base profile must block
        # re-using "lab" for this one.
        rv = gpu_stub["router"]("reservables_vgpus")
        rv.filter.return_value.pluck.return_value.run.return_value = [
            {"id": "NVIDIA-L40-2Q~lab"}
        ]
        with pytest.raises(Exception) as exc:
            gpu_stub["Cls"].enable_subitem("gpu-1", "NVIDIA-A40-1Q~lab", True)
        assert _status(exc) == 400


# --------------------------------------------------------------------------- #
# add_reservable_vgpu guards
# --------------------------------------------------------------------------- #
class TestAddReservableVgpuGuards:
    def test_missing_profile_raises_not_found(self, gpu_stub):
        gpus = gpu_stub["router"]("gpus")
        gpus.get.return_value.run.return_value = {"brand": "NVIDIA", "model": "A40"}
        # get_subitem resolves the profile; None -> not_found.
        gpu_stub["monkeypatch"].setattr(
            gpu_stub["Cls"], "get_subitem", classmethod(lambda cls, i, s: None)
        )
        with pytest.raises(Exception) as exc:
            gpu_stub["Cls"].add_reservable_vgpu("gpu-1", "NVIDIA-A40-1Q")
        assert _status(exc) == 404

    def test_failed_insert_raises_internal_server(self, gpu_stub):
        gpus = gpu_stub["router"]("gpus")
        gpus.get.return_value.run.return_value = {"brand": "NVIDIA", "model": "A40"}
        gpu_stub["monkeypatch"].setattr(
            gpu_stub["Cls"],
            "get_subitem",
            classmethod(
                lambda cls, i, s: {"profile": "1Q", "memory": "1G", "units": 8}
            ),
        )
        rv = gpu_stub["router"]("reservables_vgpus")
        # insert reports nothing replaced + an error -> internal_server.
        rv.insert.return_value.run.return_value = {
            "replaced": 0,
            "unchanged": 0,
            "errors": 1,
        }
        with pytest.raises(Exception) as exc:
            gpu_stub["Cls"].add_reservable_vgpu("gpu-1", "NVIDIA-A40-1Q")
        assert _status(exc) == 500


# --------------------------------------------------------------------------- #
# list_subitems_enabled guards + filtering
# --------------------------------------------------------------------------- #
class TestListSubitemsEnabledGuards:
    def test_missing_card_raises_not_found(self, gpu_stub):
        gpus = gpu_stub["router"]("gpus")
        gpus.get.return_value.run.return_value = None
        with pytest.raises(Exception) as exc:
            gpu_stub["Cls"].list_subitems_enabled("nope")
        assert _status(exc) == 404

    def test_missing_profile_catalog_raises_not_found(self, gpu_stub):
        gpus = gpu_stub["router"]("gpus")
        gpus.get.return_value.run.return_value = {"brand": "NVIDIA", "model": "A40"}
        gp = gpu_stub["router"]("gpu_profiles")
        # empty catalog -> [0] IndexError -> not_found (definitions)
        gp.get_all.return_value.run.return_value = []
        with pytest.raises(Exception) as exc:
            gpu_stub["Cls"].list_subitems_enabled("gpu-1")
        assert _status(exc) == 404

    def test_returns_only_enabled_subitems(self, gpu_stub):
        gpus = gpu_stub["router"]("gpus")
        gpus.get.return_value.run.return_value = {
            "brand": "NVIDIA",
            "model": "A40",
            "profiles_enabled": ["1Q", "4Q"],
        }
        gp = gpu_stub["router"]("gpu_profiles")
        gp.get_all.return_value.run.return_value = [
            {
                "profiles": [
                    {"id": "1Q"},
                    {"id": "2Q"},
                    {"id": "4Q"},
                ]
            }
        ]
        result = gpu_stub["Cls"].list_subitems_enabled("gpu-1")
        # Only the profiles whose id is in profiles_enabled survive, order kept.
        assert [s["id"] for s in result] == ["1Q", "4Q"]
