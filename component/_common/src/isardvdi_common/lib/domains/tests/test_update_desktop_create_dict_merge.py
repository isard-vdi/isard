#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression tests for ``DesktopsProcessed.update_desktop`` payload
construction — ``create_dict.hardware`` must be merged into any
``create_dict`` keys that ``parse_domain_update`` already populated
(e.g. ``create_dict.reservables`` when the user changed vgpus).

The previous code did a bare ``update_payload["create_dict"] =
{"hardware": ...}`` whenever the edit carried a hardware change,
which clobbered the ``create_dict.reservables`` entry that
``parse_domain_update`` writes when the same edit also changes
vgpus. RethinkDB's ``.update()`` deep-merges the payload into the
row, so the missing key meant the rdb row's old vgpu value was
preserved on disk — the user saw their vgpu change silently dropped.
"""

import copy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mod_with_stubs(monkeypatch):
    from isardvdi_common.lib.domains.desktops import desktops as mod

    # ``parse_domain_update`` returns a dict — stub it so we exercise
    # only ``update_desktop``'s payload construction. Captures the
    # last update payload sent to ``r.table().update(...)``.
    captured = {"updates": []}

    def fake_parse_domain_update(cls, domain_id, new_data, admin_or_manager=False):
        # Mirror parse_domain_update's actual output shape for the
        # hardware+reservables case: top-level ``hardware`` plus a
        # ``create_dict`` that carries ``reservables``.
        result = {}
        if new_data.get("hardware"):
            result["hardware"] = new_data["hardware"]
        if new_data.get("reservables"):
            result["create_dict"] = {"reservables": new_data["reservables"]}
        if new_data.get("name") is not None:
            result["name"] = new_data["name"]
        return result

    monkeypatch.setattr(
        mod.DesktopsProcessed,
        "parse_domain_update",
        classmethod(fake_parse_domain_update),
    )
    monkeypatch.setattr(
        mod.Caches,
        "get_document",
        staticmethod(
            lambda table, item_id, *a, **k: {
                "create_dict": {
                    "reservables": {"vgpus": ["old-vgpu"]},
                    "hardware": {"memory": 1024},
                }
            }
        ),
    )
    # ``Bookings.delete_item_bookings`` triggers on vgpu change — no-op.
    monkeypatch.setattr(
        mod.Bookings, "delete_item_bookings", staticmethod(lambda *a, **k: None)
    )
    # ``validate_reservables_vgpus`` (upstream !4521/!4527 port) hits the
    # reservables_vgpus table — stub it; this suite exercises only
    # ``update_desktop``'s payload construction.
    monkeypatch.setattr(mod, "validate_reservables_vgpus", lambda vgpus: vgpus)

    # ``with cls._rdb_context()`` short-circuit + capture the
    # ``r.table(...).update(...)`` payload via the rethinkdb table mock.
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

    class _Update:
        def __init__(self, payload):
            captured["updates"].append(payload)

        def run(self, conn):
            return {"replaced": 1}

    class _Row:
        def update(self, payload):
            return _Update(payload)

    class _Table:
        def get(self, _id):
            return _Row()

    fake_table = MagicMock(
        side_effect=lambda name: _Table() if name == "domains" else MagicMock()
    )
    monkeypatch.setattr(mod.r, "table", fake_table)

    return {"mod": mod, "captured": captured}


class TestUpdateDesktopCreateDictMerge:
    def test_hardware_and_reservables_change_both_persist(self, mod_with_stubs):
        # The Naomi #46 case: edit form sends both hardware AND
        # reservables. update_payload's create_dict must carry BOTH
        # ``hardware`` and ``reservables`` so RethinkDB's deep-merge
        # actually writes the new vgpu value.
        mod_with_stubs["mod"].DesktopsProcessed.update_desktop(
            desktop_id="dsk-1",
            desktop_data={
                "hardware": {"memory": 2048, "vcpus": 2},
                "reservables": {"vgpus": ["NVIDIA-A16-2Q"]},
            },
            admin_or_manager=False,
            bulk=False,
        )

        assert len(mod_with_stubs["captured"]["updates"]) == 1
        payload = mod_with_stubs["captured"]["updates"][0]
        # The whole point of the bug fix: create_dict carries both
        # keys, not just hardware.
        assert "create_dict" in payload
        assert "hardware" in payload["create_dict"]
        assert "reservables" in payload["create_dict"], (
            "create_dict.reservables clobbered by hardware overwrite — "
            "the new vgpu value would be silently dropped"
        )
        assert payload["create_dict"]["reservables"] == {"vgpus": ["NVIDIA-A16-2Q"]}

    def test_only_hardware_change_does_not_emit_reservables_key(self, mod_with_stubs):
        # Without a reservables change, parse_domain_update doesn't
        # populate create_dict.reservables, so the update payload only
        # carries ``create_dict.hardware``. Pre-existing
        # ``create_dict.reservables`` on the row is preserved by
        # RethinkDB's deep-merge automatically.
        mod_with_stubs["mod"].DesktopsProcessed.update_desktop(
            desktop_id="dsk-1",
            desktop_data={"hardware": {"memory": 4096}},
            admin_or_manager=False,
            bulk=False,
        )

        payload = mod_with_stubs["captured"]["updates"][0]
        assert "create_dict" in payload
        assert "hardware" in payload["create_dict"]
        assert "reservables" not in payload["create_dict"]

    def test_only_reservables_change_writes_create_dict_reservables(
        self, mod_with_stubs
    ):
        # No hardware change → no overwrite branch → create_dict
        # carries only the reservables key parse_domain_update wrote.
        mod_with_stubs["mod"].DesktopsProcessed.update_desktop(
            desktop_id="dsk-1",
            desktop_data={"reservables": {"vgpus": ["NVIDIA-A16-2Q"]}},
            admin_or_manager=False,
            bulk=False,
        )

        payload = mod_with_stubs["captured"]["updates"][0]
        assert payload["create_dict"] == {"reservables": {"vgpus": ["NVIDIA-A16-2Q"]}}

    def test_only_name_change_does_not_emit_create_dict(self, mod_with_stubs):
        # Regression guard for the original "always nest create_dict"
        # bug the comment in update_desktop already documents:
        # name-only edits must not touch create_dict at all (otherwise
        # the engine crashes on ``argument of type 'NoneType'`` when
        # resolving hardware).
        mod_with_stubs["mod"].DesktopsProcessed.update_desktop(
            desktop_id="dsk-1",
            desktop_data={"name": "rename"},
            admin_or_manager=False,
            bulk=False,
        )

        payload = mod_with_stubs["captured"]["updates"][0]
        assert "create_dict" not in payload
        assert payload.get("name") == "rename"
