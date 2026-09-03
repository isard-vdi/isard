#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Destructive GPU-catalog / media removal paths of ``HypervisorsProcessed``.

These irreversibly drop rows the fleet derives from hardware:

* ``_remove_catalog_profile_entry`` -- removes ONE nested profile from a
  ``gpu_profiles`` model row, keeping every other profile AND the passthrough
  entry; a no-op when the catalog is missing or the profile is not present.
* ``_prune_card_reservable`` -- disables an unrealizable profile on a card and,
  only when it was the last card, drops the dead catalog entry.
* ``delete_media`` -- deletes media rows by ``path_downloaded``.

The real function is exercised; only rethink and the injected collaborators are
stubbed. Per the destructive rules we also assert what is NOT removed.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub(monkeypatch):
    from isardvdi_common.lib.hypervisors import hypervisors as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.HypervisorsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.HypervisorsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    tables = {}

    def router(name):
        return tables.setdefault(name, MagicMock(name=f"table-{name}"))

    monkeypatch.setattr(mod.r, "table", MagicMock(side_effect=router))
    return {
        "mod": mod,
        "Cls": mod.HypervisorsProcessed,
        "router": router,
        "mp": monkeypatch,
    }


class TestRemoveCatalogProfileEntry:
    def test_drops_target_profile_but_keeps_others_and_passthrough(self, stub):
        gp = stub["router"]("gpu_profiles")
        catalog = {
            "id": "NVIDIA-A40",
            "profiles": [
                {"id": "NVIDIA-A40-1Q", "profile": "1Q"},
                {"id": "NVIDIA-A40-2Q", "profile": "2Q"},
                # A passthrough entry that shares the id must be PRESERVED.
                {"id": "NVIDIA-A40-1Q", "profile": "passthrough"},
            ],
        }
        gp.get.return_value.run.return_value = catalog

        stub["Cls"]._remove_catalog_profile_entry("A40", "NVIDIA-A40-1Q")

        gp.get.return_value.update.assert_called_once_with(
            {
                "profiles": [
                    {"id": "NVIDIA-A40-2Q", "profile": "2Q"},
                    {"id": "NVIDIA-A40-1Q", "profile": "passthrough"},
                ]
            }
        )

    def test_missing_catalog_is_noop(self, stub):
        gp = stub["router"]("gpu_profiles")
        gp.get.return_value.run.return_value = None
        stub["Cls"]._remove_catalog_profile_entry("A40", "NVIDIA-A40-1Q")
        gp.get.return_value.update.assert_not_called()

    def test_absent_profile_writes_nothing(self, stub):
        gp = stub["router"]("gpu_profiles")
        gp.get.return_value.run.return_value = {
            "id": "NVIDIA-A40",
            "profiles": [{"id": "NVIDIA-A40-2Q", "profile": "2Q"}],
        }
        # profile_id not present -> kept == profiles -> must not rewrite the row.
        stub["Cls"]._remove_catalog_profile_entry("A40", "NVIDIA-A40-1Q")
        gp.get.return_value.update.assert_not_called()


class TestPruneCardReservable:
    def test_last_card_drops_catalog_entry(self, stub):
        api_ri = MagicMock(name="api_ri")
        api_rp = MagicMock(name="api_rp")
        rv = stub["router"]("reservables_vgpus")
        rv.get.return_value.run.return_value = None  # last card: reservable gone
        removed = MagicMock(name="_remove_catalog_profile_entry")
        stub["mp"].setattr(
            stub["Cls"],
            "_remove_catalog_profile_entry",
            classmethod(lambda cls, model, pid: removed(model, pid)),
        )

        stub["Cls"]._prune_card_reservable(
            api_ri, api_rp, "A40", "card-1", "NVIDIA-A40-1Q"
        )

        api_rp.delete_subitem.assert_called_once_with("gpus", "card-1", "NVIDIA-A40-1Q")
        api_ri.enable_subitems.assert_called_once_with(
            "gpus", "card-1", "NVIDIA-A40-1Q", False
        )
        removed.assert_called_once_with("A40", "NVIDIA-A40-1Q")

    def test_surviving_reservable_keeps_catalog_entry(self, stub):
        api_ri = MagicMock(name="api_ri")
        api_rp = MagicMock(name="api_rp")
        rv = stub["router"]("reservables_vgpus")
        rv.get.return_value.run.return_value = {"id": "NVIDIA-A40-1Q"}  # still used
        removed = MagicMock(name="_remove_catalog_profile_entry")
        stub["mp"].setattr(
            stub["Cls"],
            "_remove_catalog_profile_entry",
            classmethod(lambda cls, model, pid: removed(model, pid)),
        )

        stub["Cls"]._prune_card_reservable(
            api_ri, api_rp, "A40", "card-1", "NVIDIA-A40-1Q"
        )
        # A reservable still realized on another card must NOT be dropped.
        removed.assert_not_called()

    def test_disable_failure_returns_before_touching_catalog(self, stub):
        api_ri = MagicMock(name="api_ri")
        api_ri.enable_subitems.side_effect = RuntimeError("disable boom")
        api_rp = MagicMock(name="api_rp")
        rv = stub["router"]("reservables_vgpus")
        removed = MagicMock(name="_remove_catalog_profile_entry")
        stub["mp"].setattr(
            stub["Cls"],
            "_remove_catalog_profile_entry",
            classmethod(lambda cls, model, pid: removed(model, pid)),
        )

        stub["Cls"]._prune_card_reservable(
            api_ri, api_rp, "A40", "card-1", "NVIDIA-A40-1Q"
        )
        # Early return on a failed disable: never read survives, never prune.
        rv.get.assert_not_called()
        removed.assert_not_called()


class TestDeleteMedia:
    def test_deletes_only_the_given_paths(self, stub):
        media = stub["router"]("media")
        media.filter.return_value.delete.return_value.run.return_value = {"deleted": 1}

        stub["Cls"].delete_media(["/isard/media/a.iso", "/isard/media/b.iso"])

        assert media.filter.call_args_list == [
            (({"path_downloaded": "/isard/media/a.iso"},),),
            (({"path_downloaded": "/isard/media/b.iso"},),),
        ]
        assert media.filter.return_value.delete.call_count == 2
