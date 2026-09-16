#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards / decisions on ``DesktopsProcessed.parse_domain_update``.

Builds the partial update dict for a domain edit. The decisions pinned are
the ones that change *what a user is allowed to alter* or *whether a field
is written at all* — not every field-copy branch:

* unknown domain -> reject (L864) not_found;
* privileged fields (``forced_hyp`` …) are applied only when
  ``admin_or_manager`` (L873) — a normal user editing must not change them;
* a field is written only when actually changed (``name``, L911);
* the ``Updating`` status flip fires only for rebuild-needing states
  (Stopped/Failed/Downloaded), never for running-side states (L1016);
* the ``["None"]`` vGPU sentinel is normalized to ``None`` (L998).

``parse_domain_update`` runs unmocked; only ``Caches.get_document`` (the
domain lookup) is stubbed, so every include/exclude decision is real code.
"""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktops as mod

DP = mod.DesktopsProcessed
UPDATING = mod.DesktopStatusEnum.updating.value


def _domain(**over):
    base = {
        "name": "old-name",
        "description": "old-desc",
        "forced_hyp": "hyp-1",
        "status": "Started",
    }
    base.update(over)
    return base


def _use_domain(monkeypatch, domain):
    monkeypatch.setattr(
        mod.Caches, "get_document", classmethod(lambda cls, table, did: domain)
    )


class TestParseDomainUpdateGuards:
    def test_unknown_domain_rejected(self, monkeypatch):
        # Editing a missing / just-deleted desktop must 404, not 500. (The
        # guard used to raise TypeError because Error() got ``description``
        # both positionally and by keyword; fixed to ``description_code``.)
        monkeypatch.setattr(
            mod.Caches, "get_document", classmethod(lambda cls, t, d: None)
        )
        with pytest.raises(Error) as exc:
            DP.parse_domain_update("missing", {"name": "x"})
        assert exc.value.error["error"] == "not_found"
        assert exc.value.error["description_code"] == "not_found"

    def test_forced_hyp_applied_for_admin(self, monkeypatch):
        _use_domain(monkeypatch, _domain(forced_hyp="hyp-1"))
        result = DP.parse_domain_update(
            "d-1", {"forced_hyp": "hyp-2"}, admin_or_manager=True
        )
        assert result["forced_hyp"] == "hyp-2"

    def test_forced_hyp_ignored_for_non_admin(self, monkeypatch):
        # A non-admin editor must not be able to move the desktop's forced_hyp.
        _use_domain(monkeypatch, _domain(forced_hyp="hyp-1"))
        result = DP.parse_domain_update(
            "d-1", {"forced_hyp": "hyp-2"}, admin_or_manager=False
        )
        assert "forced_hyp" not in result

    def test_name_written_only_when_changed(self, monkeypatch):
        _use_domain(monkeypatch, _domain(name="old-name"))
        assert DP.parse_domain_update("d-1", {"name": "new-name"})["name"] == "new-name"

    def test_unchanged_name_not_written(self, monkeypatch):
        _use_domain(monkeypatch, _domain(name="same"))
        assert "name" not in DP.parse_domain_update("d-1", {"name": "same"})

    def test_status_flips_to_updating_for_stopped(self, monkeypatch):
        _use_domain(monkeypatch, _domain(status="Stopped", name="old-name"))
        result = DP.parse_domain_update("d-1", {"name": "new-name"})
        assert result["status"] == UPDATING

    def test_status_not_flipped_for_running_state(self, monkeypatch):
        # Started is running-side: persist the change but do NOT flip to Updating.
        _use_domain(monkeypatch, _domain(status="Started", name="old-name"))
        result = DP.parse_domain_update("d-1", {"name": "new-name"})
        assert "status" not in result

    def test_vgpu_none_sentinel_normalized(self, monkeypatch):
        _use_domain(monkeypatch, _domain(status="Started"))
        result = DP.parse_domain_update("d-1", {"reservables": {"vgpus": ["None"]}})
        assert result["create_dict"]["reservables"]["vgpus"] is None


class TestParseDomainUpdateGuestCredentials:
    """Only the RDP viewers and the bastion SSH inner hop log in with
    ``guest_properties.credentials``. An edit that leaves neither in place has
    to take the stored pair with it — and because the update deep-merges
    ``guest_properties``, that means writing an explicit empty pair, not
    omitting the key."""

    STORED = {"username": "alice", "password": "s3cret"}
    EMPTY = {"username": "", "password": ""}

    def _domain_with_credentials(self, monkeypatch, viewers):
        _use_domain(
            monkeypatch,
            _domain(
                status="Stopped",
                guest_properties={
                    "credentials": dict(self.STORED),
                    "fullscreen": False,
                    "viewers": viewers,
                },
            ),
        )

    def _no_bastion(self, monkeypatch):
        monkeypatch.setattr(mod, "domain_bastion_enabled", lambda domain_id: False)

    def test_dropping_the_last_rdp_viewer_blanks_them(self, monkeypatch):
        self._domain_with_credentials(monkeypatch, {"file_rdpgw": {"options": None}})
        self._no_bastion(monkeypatch)
        result = DP.parse_domain_update(
            "d-1",
            {"guest_properties": {"viewers": {"file_spice": {"options": None}}}},
        )
        assert result["guest_properties"]["credentials"] == self.EMPTY

    def test_keeping_an_rdp_viewer_leaves_them_alone(self, monkeypatch):
        self._domain_with_credentials(monkeypatch, {"file_rdpgw": {"options": None}})
        self._no_bastion(monkeypatch)
        result = DP.parse_domain_update(
            "d-1",
            {
                "guest_properties": {
                    "credentials": dict(self.STORED),
                    "viewers": {"browser_rdp": {"options": None}},
                }
            },
        )
        assert result["guest_properties"]["credentials"] == self.STORED

    def test_a_bastion_desktop_keeps_them(self, monkeypatch):
        # The bastion authenticates the inner hop with the same pair, so a
        # desktop reachable through it keeps them with no RDP viewer at all.
        self._domain_with_credentials(monkeypatch, {"file_rdpgw": {"options": None}})
        monkeypatch.setattr(mod, "domain_bastion_enabled", lambda domain_id: True)
        result = DP.parse_domain_update(
            "d-1",
            {
                "guest_properties": {
                    "credentials": dict(self.STORED),
                    "viewers": {"file_spice": {"options": None}},
                }
            },
        )
        assert result["guest_properties"]["credentials"] == self.STORED

    def test_the_caller_can_override_the_stored_target(self, monkeypatch):
        # apiv4 writes the bastion target *after* the domain, so it passes the
        # pending state down: a bastion being turned on in the same request
        # must not have its credentials blanked by the pre-edit target.
        self._domain_with_credentials(monkeypatch, {"file_rdpgw": {"options": None}})
        monkeypatch.setattr(
            mod,
            "domain_bastion_enabled",
            lambda domain_id: pytest.fail("the caller's answer must win"),
        )
        result = DP.parse_domain_update(
            "d-1",
            {
                "guest_properties": {
                    "credentials": dict(self.STORED),
                    "viewers": {"file_spice": {"options": None}},
                }
            },
            bastion_enabled=True,
        )
        assert result["guest_properties"]["credentials"] == self.STORED

    def test_an_edit_that_does_not_submit_viewers_is_left_alone(self, monkeypatch):
        # A rename says nothing about the viewers: never blank on a payload
        # that did not carry them.
        self._domain_with_credentials(monkeypatch, {"file_spice": {"options": None}})
        monkeypatch.setattr(
            mod,
            "domain_bastion_enabled",
            lambda domain_id: pytest.fail("no target lookup on a viewer-less edit"),
        )
        result = DP.parse_domain_update("d-1", {"name": "new-name"})
        assert "guest_properties" not in result

    def test_a_deselected_rdp_viewer_does_not_save_them(self, monkeypatch):
        # Legacy rows persist a deselected viewer as an explicit null.
        self._domain_with_credentials(monkeypatch, {"browser_rdp": {"options": None}})
        self._no_bastion(monkeypatch)
        result = DP.parse_domain_update(
            "d-1",
            {
                "guest_properties": {
                    "viewers": {
                        "browser_rdp": None,
                        "browser_vnc": {"options": None},
                    }
                }
            },
        )
        assert result["guest_properties"]["credentials"] == self.EMPTY
