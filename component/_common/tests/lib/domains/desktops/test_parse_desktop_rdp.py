# SPDX-License-Identifier: AGPL-3.0-or-later
"""A running desktop with an RDP viewer carries how far its RDP service has been verified."""

from isardvdi_common.lib.domains.desktops.desktops import DesktopsProcessed


def _desktop(viewer, viewers=None):
    return {
        "id": "d1",
        "name": "d1",
        "status": "Started",
        "icon": "linux",
        "description": "",
        "user": "u1",
        "viewer": viewer,
        "guest_properties": {
            "viewers": (
                viewers if viewers is not None else {"browser_rdp": {"options": None}}
            )
        },
        "create_dict": {"hardware": {"interfaces": [{"id": "wireguard"}], "disks": []}},
    }


def test_rdp_is_pending_until_the_vpn_reports_it():
    parsed = DesktopsProcessed._parse_desktop(
        _desktop({"guest_ip": "192.0.2.5", "passwd": "x"})
    )
    assert parsed["rdp"] == {"state": "pending"}


def test_the_reported_state_and_last_outcome_are_passed_through():
    viewer = {
        "guest_ip": "192.0.2.5",
        "passwd": "x",
        "rdp": {"state": "ready", "protocol": "nla", "at": 1},
        "rdp_last": {
            "via": "browser",
            "connected": False,
            "code": 519,
            "message": "refused",
            "at": 2,
        },
    }
    parsed = DesktopsProcessed._parse_desktop(_desktop(viewer))
    assert parsed["rdp"]["state"] == "ready"
    assert parsed["rdp"]["last"]["code"] == 519


def test_no_rdp_state_without_an_rdp_viewer_or_an_ip():
    no_rdp = _desktop(
        {"guest_ip": "192.0.2.5", "passwd": "x"},
        viewers={"browser_vnc": {"options": None}},
    )
    assert DesktopsProcessed._parse_desktop(no_rdp)["rdp"] is None
    assert DesktopsProcessed._parse_desktop(_desktop({"passwd": "x"}))["rdp"] is None


def test_a_guest_refusing_tls_is_shown_as_standard_rdp_security(monkeypatch):
    from isardvdi_common.lib.domains.desktops import desktops as mod

    monkeypatch.setattr(
        mod, "current_allowed_rdp_security", lambda: ("rdp", "tls", "nla")
    )
    viewer = {
        "guest_ip": "192.0.2.5",
        "passwd": "x",
        "rdp": {"state": "refused", "reason": "tls_not_allowed", "at": 1},
    }
    rdp = DesktopsProcessed._parse_desktop(_desktop(viewer))["rdp"]
    assert (rdp["state"], rdp["protocol"], rdp["reason"]) == ("unverified", "rdp", None)


def test_a_level_the_policy_does_not_allow_is_shown_as_refused(monkeypatch):
    from isardvdi_common.lib.domains.desktops import desktops as mod

    monkeypatch.setattr(mod, "current_allowed_rdp_security", lambda: ("nla",))
    viewer = {
        "guest_ip": "192.0.2.5",
        "passwd": "x",
        "rdp": {"state": "unverified", "protocol": "tls", "at": 1},
    }
    rdp = DesktopsProcessed._parse_desktop(_desktop(viewer))["rdp"]
    assert (rdp["state"], rdp["reason"]) == ("refused", "security_not_allowed")
