#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Validation guards of ``desktops.py``.

* ``validate_reservables_vgpus`` -- rejects too many / duplicate / unknown vGPU
  profiles and profiles that can't share a hypervisor.
* ``validate_desktop_update`` -- rejects editing a running desktop, editing an
  autostart server, setting a non-server to autostart, giving a server a
  bookable, and an unknown vGPU id.

The real validators decide; only rethink / ``Caches`` / ``get_vgpus_hypervisors``
are stubbed. Errors assert ``description_code`` / type.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_base import ErrorBase


@pytest.fixture
def stub(monkeypatch):
    from isardvdi_common.lib.domains.desktops import desktops as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.DesktopsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.DesktopsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    tables = {}

    def router(name):
        return tables.setdefault(name, MagicMock(name=f"table-{name}"))

    monkeypatch.setattr(mod.r, "table", MagicMock(side_effect=router))
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", tuple(x)))
    return {
        "mod": mod,
        "Cls": mod.DesktopsProcessed,
        "router": router,
        "mp": monkeypatch,
    }


class TestValidateReservablesVgpus:
    def test_too_many_profiles(self, stub):
        vgpus = [f"p{i}" for i in range(stub["mod"].MAX_VGPU_PROFILES_PER_DESKTOP + 1)]
        with pytest.raises(ErrorBase) as exc:
            stub["mod"].validate_reservables_vgpus(vgpus)
        assert exc.value.error["description_code"] == "too_many_vgpu_profiles"

    def test_duplicate_profiles(self, stub):
        with pytest.raises(ErrorBase) as exc:
            stub["mod"].validate_reservables_vgpus(["p1", "p1"])
        assert exc.value.error["description_code"] == "duplicate_vgpu_profiles"

    def test_unknown_profile(self, stub):
        # one real id requested but the reservables_vgpus lookup returns nothing.
        stub["router"](
            "reservables_vgpus"
        ).get_all.return_value.pluck.return_value.run.return_value = []
        with pytest.raises(ErrorBase) as exc:
            stub["mod"].validate_reservables_vgpus(["NVIDIA-A40-1Q"])
        assert exc.value.error["description_code"] == "vgpu_profile_not_found"

    def test_profiles_on_different_hypervisors(self, stub):
        rv = stub["router"]("reservables_vgpus")
        rv.get_all.return_value.pluck.return_value.run.return_value = [
            {"id": "A", "model": "A40"},
            {"id": "B", "model": "A40"},
        ]
        # get_vgpus_hypervisors is lazily imported from the reservables module.
        from isardvdi_common.lib.bookings import reservables as res_mod

        stub["mp"].setattr(
            res_mod,
            "get_vgpus_hypervisors",
            lambda: {"A": ["h1"], "B": ["h2"]},  # disjoint -> no common host
        )
        with pytest.raises(ErrorBase) as exc:
            stub["mod"].validate_reservables_vgpus(["A", "B"])
        assert (
            exc.value.error["description_code"] == "vgpu_profiles_different_hypervisors"
        )

    def test_none_sentinel_passes(self, stub):
        assert stub["mod"].validate_reservables_vgpus(["None"]) == ["None"]


class TestValidateDesktopUpdate:
    def _desktop(self, stub, desktop):
        stub["mp"].setattr(
            stub["mod"].Caches,
            "get_document",
            classmethod(lambda cls, *a, **k: desktop),
        )

    def test_running_desktop_cannot_be_edited(self, stub):
        self._desktop(stub, {"status": "Started", "user": "u"})
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].validate_desktop_update({}, "d1")
        assert exc.value.status_code == 428  # precondition_required

    def test_non_server_cannot_autostart(self, stub):
        self._desktop(stub, {"status": "Stopped", "user": "u", "server": False})
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].validate_desktop_update(
                {"server_autostart": True, "server": False}, "d1"
            )
        assert exc.value.status_code == 428

    def test_server_cannot_have_bookable(self, stub):
        self._desktop(
            stub,
            {
                "status": "Stopped",
                "user": "u",
                "create_dict": {"reservables": {"vgpus": ["x"]}},
            },
        )
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].validate_desktop_update({"server": True}, "d1")
        assert exc.value.status_code == 428

    def test_unknown_vgpu_rejected(self, stub):
        self._desktop(
            stub,
            {"status": "Stopped", "user": "u", "create_dict": {"reservables": {}}},
        )
        stub["router"](
            "reservables_vgpus"
        ).__getitem__.return_value.run.return_value = ["real-1"]
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].validate_desktop_update(
                {"reservables": {"vgpus": ["ghost"]}}, "d1"
            )
        assert exc.value.error["error"] == "not_found"
