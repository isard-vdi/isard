#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``DesktopsProcessed.check_viewers``.

Validates the viewer selection a desktop is created/updated with against
its hardware. The decisions pinned:

* viewers omitted (None) -> inherit the domain's stored viewers (L1746);
* viewers present but all-null -> reject, at least one required (L1749)
  ``one_viewer_minimum``;
* an RDP viewer with no wireguard interface -> reject (L1783) bad_request;
* an RDP viewer that has wireguard -> passes;
* "Only GPU" video (``none``) with a non-RDP viewer -> reject (L1797)
  ``only_works_rdp``;
* "Only GPU" video with an RDP viewer over wireguard -> passes.

``check_viewers`` and its only collaborator ``strip_unavailable_viewers``
(pure, no I/O) both run unmocked — the accept/reject decision is entirely
the real code.
"""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktops as mod

DP = mod.DesktopsProcessed


def _domain(viewers=None, videos=None, interfaces=None):
    return {
        "guest_properties": {"viewers": viewers or {"browser_vnc": True}},
        "create_dict": {
            "hardware": {
                "videos": videos or ["default"],
                "interfaces": interfaces or [{"id": "default", "mac": "aa"}],
            }
        },
    }


def _data(viewers, videos=None, interfaces=None):
    return {
        "hardware": {
            "videos": videos if videos is not None else ["default"],
            "interfaces": interfaces if interfaces is not None else ["default"],
        },
        "guest_properties": {"viewers": viewers},
    }


class TestCheckViewersGuards:
    def test_none_viewers_inherit_domain(self):
        data = _data(viewers=None)
        domain = _domain(viewers={"browser_vnc": True})
        result = DP.check_viewers(data, domain)
        # the domain's stored viewers were adopted
        assert result["guest_properties"]["viewers"] == {"browser_vnc": True}

    def test_all_null_viewers_rejected(self):
        data = _data(viewers={"file_spice": None, "browser_vnc": None})
        with pytest.raises(Error) as exc:
            DP.check_viewers(data, _domain())
        assert exc.value.error["description_code"] == "one_viewer_minimum"

    def test_rdp_viewer_without_wireguard_rejected(self):
        data = _data(viewers={"browser_rdp": True}, interfaces=["default"])
        with pytest.raises(Error) as exc:
            DP.check_viewers(data, _domain())
        assert exc.value.error["error"] == "bad_request"

    def test_rdp_viewer_with_wireguard_passes(self):
        data = _data(viewers={"browser_rdp": True}, interfaces=["wireguard"])
        result = DP.check_viewers(data, _domain())
        assert result is data

    def test_only_gpu_video_with_non_rdp_viewer_rejected(self):
        data = _data(
            viewers={"browser_vnc": True}, videos=["none"], interfaces=["wireguard"]
        )
        with pytest.raises(Error) as exc:
            DP.check_viewers(data, _domain())
        assert exc.value.error["description_code"] == "only_works_rdp"

    def test_only_gpu_video_with_rdp_over_wireguard_passes(self):
        data = _data(
            viewers={"file_rdpgw": True}, videos=["none"], interfaces=["wireguard"]
        )
        result = DP.check_viewers(data, _domain())
        assert result is data
