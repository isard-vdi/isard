# SPDX-License-Identifier: AGPL-3.0-or-later
"""An RDP viewer is only handed out once the guest RDP is verified, unless an admin or the desktop's manager asks."""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_base import ErrorBase
from isardvdi_common.lib.domains.desktops import desktop_direct_viewer as mod

DDV = mod.DesktopDirectViewer


def _desktop(state=None, category="cat-a"):
    viewer = {"guest_ip": "192.0.2.5"}
    if state:
        viewer["rdp"] = {"state": state}
    return {
        "id": "d1",
        "user": "owner",
        "category": category,
        "status": "Started",
        "viewer": viewer,
    }


@pytest.mark.parametrize("state", ["ready", "unverified"])
def test_a_verified_desktop_is_open_to_everyone_who_owns_it(state):
    DDV.check_rdp_open(_desktop(state), "user", "cat-a")
    DDV.check_rdp_open(_desktop(state))


@pytest.mark.parametrize(
    "state", [None, "pending", "waiting", "refused", "auth_failed"]
)
def test_a_user_cannot_open_an_unverified_desktop(state):
    with pytest.raises(ErrorBase):
        DDV.check_rdp_open(_desktop(state), "user", "cat-a")


def test_a_shared_link_cannot_open_an_unverified_desktop():
    with pytest.raises(ErrorBase):
        DDV.check_rdp_open(_desktop("waiting"))


def test_a_manager_of_another_category_cannot_force_it():
    with pytest.raises(ErrorBase):
        DDV.check_rdp_open(_desktop("waiting"), "manager", "cat-b")


def test_the_desktops_manager_and_an_admin_can_force_it():
    DDV.check_rdp_open(_desktop("waiting"), "manager", "cat-a")
    DDV.check_rdp_open(_desktop("waiting"), "admin", "cat-b")


def test_advanced_users_are_not_managers():
    with pytest.raises(ErrorBase):
        DDV.check_rdp_open(_desktop("waiting"), "advanced", "cat-a")


@pytest.fixture
def no_db(monkeypatch):
    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(DDV, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(DDV), "_rdb_connection", property(lambda self: MagicMock()), raising=False
    )
    monkeypatch.setattr(mod.r, "table", MagicMock())
    viewer_data = MagicMock(return_value={"kind": "file", "content": "creds inside"})
    monkeypatch.setattr(mod.isard_viewer, "viewer_data", viewer_data)
    return viewer_data


@pytest.mark.parametrize("protocol", ["browser-rdp", "file-rdpgw", "file-rdpvpn"])
def test_no_rdp_viewer_and_no_credentials_leave_before_the_check(no_db, protocol):
    with pytest.raises(ErrorBase):
        DDV.desktop_viewer("d1", protocol, desktop=_desktop("waiting"))
    no_db.assert_not_called()


def test_the_bypass_decided_by_the_server_lets_the_viewer_through(no_db):
    DDV.desktop_viewer("d1", "file-rdpgw", desktop=_desktop("waiting"), rdp_bypass=True)
    no_db.assert_called_once()


def test_other_viewers_are_not_gated(no_db):
    DDV.desktop_viewer("d1", "browser-vnc", desktop=_desktop("waiting"))
    no_db.assert_called_once()


def test_a_stopped_desktop_is_answered_as_not_started_not_as_rdp_pending(no_db):
    no_db.side_effect = ErrorBase(
        "precondition_required",
        "Desktop is not started",
        description_code="unable_to_get_viewer",
    )
    stopped = {**_desktop(None), "status": "Stopped"}
    with pytest.raises(ErrorBase) as err:
        DDV.desktop_viewer("d1", "browser-rdp", desktop=stopped)
    assert err.value.error["description_code"] == "unable_to_get_viewer"
