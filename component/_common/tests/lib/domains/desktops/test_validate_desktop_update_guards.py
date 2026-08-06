#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``DesktopsProcessed.validate_desktop_update``.

The precondition wall for editing a desktop. Each gate rejects a different
illegal edit:

* editing a non-stopped/failed desktop (L1925);
* editing an autostart server (L1931);
* setting autostart on a non-server (L1942);
* giving a server a bookable vGPU (L1952);
* referencing a vGPU profile that does not exist (L1960) not_found.

The first four all raise ``precondition_required`` with distinct messages
(no per-guard ``description_code`` in the source — see PROGRESS), so they
are told apart by their ``description`` text; the vGPU one is a typed
``not_found``.

``validate_desktop_update`` runs unmocked; the document lookup, the
duplicate-name / viewer collaborators and the rethink profile lookup are
stubbed, so each reject decision is the real code.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktops as mod

DP = mod.DesktopsProcessed


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def env(monkeypatch):
    """Stub lookups/collaborators; ``state['desktop']`` is the stored row."""
    state = {"desktop": {"user": "u-1", "status": "Stopped"}, "vgpu_ids": ["p-ok"]}
    monkeypatch.setattr(
        mod.Caches,
        "get_document",
        classmethod(lambda cls, t, d, invalidate=False: state["desktop"]),
    )
    monkeypatch.setattr(
        mod.Helpers,
        "check_user_duplicated_domain_name",
        classmethod(lambda cls, *a, **k: None),
    )
    monkeypatch.setattr(
        DP, "check_viewers", classmethod(lambda cls, data, domain: data)
    )
    monkeypatch.setattr(DP, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(DP), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    tbl = MagicMock(name="r.table(reservables_vgpus)")
    tbl.__getitem__.return_value.run.return_value = state["vgpu_ids"]
    monkeypatch.setattr(mod.r, "table", lambda name: tbl)
    return state


class TestValidateDesktopUpdateGuards:
    def test_edit_only_when_stopped_or_failed(self, env):
        env["desktop"] = {"user": "u-1", "status": "Started"}
        with pytest.raises(Error) as exc:
            DP.validate_desktop_update({}, "d-1")
        assert exc.value.error["error"] == "precondition_required"
        assert "stopped or failed" in exc.value.error["description"]

    def test_stopped_desktop_passes(self, env):
        env["desktop"] = {"user": "u-1", "status": "Stopped"}
        assert DP.validate_desktop_update({}, "d-1") is None

    def test_autostart_server_cannot_be_edited(self, env):
        env["desktop"] = {"user": "u-1", "status": "Stopped", "server_autostart": True}
        with pytest.raises(Error) as exc:
            DP.validate_desktop_update({}, "d-1")
        assert "Autostart servers" in exc.value.error["description"]

    def test_non_server_cannot_autostart(self, env):
        env["desktop"] = {"user": "u-1", "status": "Stopped"}
        with pytest.raises(Error) as exc:
            DP.validate_desktop_update(
                {"server_autostart": True, "server": False}, "d-1"
            )
        assert "Non-server" in exc.value.error["description"]

    def test_server_cannot_have_vgpu(self, env):
        env["desktop"] = {
            "user": "u-1",
            "status": "Stopped",
            "create_dict": {"reservables": {"vgpus": ["p-ok"]}},
        }
        with pytest.raises(Error) as exc:
            DP.validate_desktop_update({"server": True}, "d-1")
        assert "bookable item" in exc.value.error["description"]

    def test_unknown_vgpu_profile_rejected(self, env):
        env["desktop"] = {
            "user": "u-1",
            "status": "Stopped",
            "create_dict": {"reservables": {"vgpus": ["p-old"]}},
        }
        env["vgpu_ids"] = ["p-ok"]  # the DB knows p-ok, not p-bad
        with pytest.raises(Error) as exc:
            DP.validate_desktop_update({"reservables": {"vgpus": ["p-bad"]}}, "d-1")
        assert exc.value.error["error"] == "not_found"

    def test_known_vgpu_profile_passes(self, env):
        env["desktop"] = {
            "user": "u-1",
            "status": "Stopped",
            "create_dict": {"reservables": {"vgpus": ["p-old"]}},
        }
        env["vgpu_ids"] = ["p-ok"]
        assert (
            DP.validate_desktop_update({"reservables": {"vgpus": ["p-ok"]}}, "d-1")
            is None
        )
