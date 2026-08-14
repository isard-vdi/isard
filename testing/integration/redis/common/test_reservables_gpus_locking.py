# SPDX-License-Identifier: AGPL-3.0-or-later

"""``ResourceItemsGpus.enable_subitem`` under the per-resource lock.

Everything from the card lookup onwards runs inside
``resource_lock("gpus:card:<id>", "bookings:reservable:<id>")``, so a test that
reaches it exercises the real lease rather than our use of one. The two guards
that fire before the lock -- the variant-name validation and the cross-profile
clash -- stay unit tests beside the mocked cases.

``test_failed_update_raises_internal_server`` belongs here for a second reason:
an unreachable lock service also raises 500, so without a server the assertion
held for the wrong cause.

Only the rdb surface and the sibling collaborators are stubbed; the lock is the
real one.
"""

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.contract


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
# enable_subitem guards reached through the lock
# --------------------------------------------------------------------------- #
class TestEnableSubitemGuards:
    def test_variant_clash_same_base_passes_guard(self, gpu_stub):
        # The SAME "~lab" on the SAME base profile is allowed (join the profile
        # across cards): the clash guard must NOT fire. Prove we got past it by
        # letting the next step (missing card) raise not_found (404), not the
        # clash bad_request (400).
        rv = gpu_stub["router"]("reservables_vgpus")
        rv.filter.return_value.pluck.return_value.run.return_value = [
            {"id": "NVIDIA-A40-1Q~lab"}
        ]
        gpus = gpu_stub["router"]("gpus")
        gpus.get.return_value.run.return_value = None
        with pytest.raises(Exception) as exc:
            gpu_stub["Cls"].enable_subitem("gpu-1", "NVIDIA-A40-1Q~lab", True)
        assert _status(exc) == 404

    def test_missing_card_raises_not_found(self, gpu_stub):
        gpus = gpu_stub["router"]("gpus")
        gpus.get.return_value.run.return_value = None
        with pytest.raises(Exception) as exc:
            gpu_stub["Cls"].enable_subitem("nope", "NVIDIA-A40-1Q", True)
        assert _status(exc) == 404

    def test_failed_update_raises_internal_server(self, gpu_stub):
        gpus = gpu_stub["router"]("gpus")
        gpus.get.return_value.run.return_value = {
            "brand": "NVIDIA",
            "model": "A40",
            "profiles_enabled": [],
        }
        # The profiles_enabled update reports nothing replaced + an error ->
        # Helpers._check False -> internal_server.
        gpus.get.return_value.update.return_value.run.return_value = {
            "replaced": 0,
            "unchanged": 0,
            "errors": 1,
        }
        with pytest.raises(Exception) as exc:
            gpu_stub["Cls"].enable_subitem("gpu-1", "NVIDIA-A40-1Q", True)
        # Specifically 500 (not some downstream error), so a mutation that
        # drops the guard and falls through is still caught.
        assert _status(exc) == 500


# --------------------------------------------------------------------------- #
# enable_subitem documented behaviour (idempotency + tail dispatch)
# --------------------------------------------------------------------------- #
class TestEnableSubitemBehaviour:
    def _card(self, profiles_enabled):
        return {"brand": "NVIDIA", "model": "A40", "profiles_enabled": profiles_enabled}

    def _wire_ok_update(self, gpus):
        gpus.get.return_value.update.return_value.run.return_value = {
            "replaced": 1,
            "unchanged": 0,
            "errors": 0,
        }

    def test_enable_is_idempotent_no_duplicate(self, gpu_stub):
        gpus = gpu_stub["router"]("gpus")
        gpus.get.return_value.run.return_value = self._card(["NVIDIA-A40-1Q"])
        self._wire_ok_update(gpus)
        # last query (gpus enabled subitem) — value irrelevant for enable
        gpus.filter.return_value.run.return_value = [object()]
        gpu_stub["monkeypatch"].setattr(
            gpu_stub["Cls"], "add_reservable_vgpu", classmethod(lambda cls, *a: None)
        )
        gpu_stub["Cls"].enable_subitem("gpu-1", "NVIDIA-A40-1Q", True)
        written = gpus.get.return_value.update.call_args.args[0]["profiles_enabled"]
        # Already present -> must NOT be appended a second time.
        assert written == ["NVIDIA-A40-1Q"]

    def test_disable_strips_all_occurrences(self, gpu_stub):
        gpus = gpu_stub["router"]("gpus")
        gpus.get.return_value.run.return_value = self._card(
            ["NVIDIA-A40-1Q", "NVIDIA-A40-1Q", "OTHER"]
        )
        self._wire_ok_update(gpus)
        gpus.filter.return_value.run.return_value = []  # last card -> delete
        gpu_stub["monkeypatch"].setattr(
            gpu_stub["Cls"],
            "delete_reservable_vgpu",
            classmethod(lambda cls, *a: None),
        )
        gpu_stub["Cls"].enable_subitem("gpu-1", "NVIDIA-A40-1Q", False)
        written = gpus.get.return_value.update.call_args.args[0]["profiles_enabled"]
        # Every occurrence removed, unrelated ids kept.
        assert written == ["OTHER"]

    def test_disable_last_card_deletes_reservable(self, gpu_stub):
        gpus = gpu_stub["router"]("gpus")
        gpus.get.return_value.run.return_value = self._card(["NVIDIA-A40-1Q"])
        self._wire_ok_update(gpus)
        gpus.filter.return_value.run.return_value = []  # no card still enables it
        deleted = MagicMock(name="delete")
        recomputed = MagicMock(name="recompute")
        gpu_stub["monkeypatch"].setattr(
            gpu_stub["Cls"],
            "delete_reservable_vgpu",
            classmethod(lambda cls, s: deleted(s)),
        )
        gpu_stub["monkeypatch"].setattr(
            gpu_stub["Cls"],
            "recompute_total_units",
            classmethod(lambda cls, s: recomputed(s)),
        )
        gpu_stub["Cls"].enable_subitem("gpu-1", "NVIDIA-A40-1Q", False)
        deleted.assert_called_once_with("NVIDIA-A40-1Q")
        recomputed.assert_not_called()

    def test_disable_nonlast_card_recomputes_units(self, gpu_stub):
        gpus = gpu_stub["router"]("gpus")
        gpus.get.return_value.run.return_value = self._card(["NVIDIA-A40-1Q"])
        self._wire_ok_update(gpus)
        # another card still enables it -> reservable survives, recompute only
        gpus.filter.return_value.run.return_value = [{"id": "gpu-2"}]
        deleted = MagicMock(name="delete")
        recomputed = MagicMock(name="recompute")
        gpu_stub["monkeypatch"].setattr(
            gpu_stub["Cls"],
            "delete_reservable_vgpu",
            classmethod(lambda cls, s: deleted(s)),
        )
        gpu_stub["monkeypatch"].setattr(
            gpu_stub["Cls"],
            "recompute_total_units",
            classmethod(lambda cls, s: recomputed(s)),
        )
        gpu_stub["Cls"].enable_subitem("gpu-1", "NVIDIA-A40-1Q", False)
        recomputed.assert_called_once_with("NVIDIA-A40-1Q")
        deleted.assert_not_called()

    def test_enable_base_passthrough_adopts_card_variant(self, gpu_stub):
        # Enabling the bare "passthrough" profile with no explicit variant must
        # adopt the card's auto-assigned passthrough_variant so each physical
        # card stays a distinct reservable.
        gpus = gpu_stub["router"]("gpus")
        gpus.get.return_value.pluck.return_value.run.return_value = {
            "passthrough_variant": "host1n0b41"
        }
        gpus.get.return_value.run.return_value = self._card([])
        self._wire_ok_update(gpus)
        gpus.filter.return_value.run.return_value = [object()]
        rv = gpu_stub["router"]("reservables_vgpus")
        rv.filter.return_value.pluck.return_value.run.return_value = []
        added = MagicMock(name="add")
        gpu_stub["monkeypatch"].setattr(
            gpu_stub["Cls"],
            "add_reservable_vgpu",
            classmethod(lambda cls, item_id, subitem_id: added(item_id, subitem_id)),
        )
        gpu_stub["Cls"].enable_subitem("gpu-1", "NVIDIA-A40-passthrough", True)
        # The subitem id handed to add_reservable_vgpu carries the adopted variant.
        assert added.call_args.args[1] == "NVIDIA-A40-passthrough~host1n0b41"
