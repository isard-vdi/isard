# SPDX-License-Identifier: AGPL-3.0-or-later
"""The RDP security policy: every level is allowed unless an admin narrows it, and the state follows."""

import pytest
from isardvdi_common.helpers import rdp_security as mod


@pytest.mark.parametrize(
    "config",
    [None, {}, {"rdp_security": {}}, {"rdp_security": {"allowed_protocols": []}}],
)
def test_without_a_policy_every_level_is_allowed(config):
    assert mod.allowed_rdp_security(config) == ("rdp", "tls", "nla")


def test_the_policy_keeps_only_known_levels_in_a_fixed_order():
    config = {"rdp_security": {"allowed_protocols": ["nla", "bogus", "tls"]}}
    assert mod.allowed_rdp_security(config) == ("tls", "nla")


def test_an_unreadable_policy_allows_everything(monkeypatch):
    from isardvdi_common.models.config import Config

    def boom():
        raise RuntimeError("no db")

    monkeypatch.setattr(Config, "get_config", staticmethod(boom))
    assert mod.current_allowed_rdp_security() == ("rdp", "tls", "nla")


def test_a_guest_refusing_tls_reads_as_standard_rdp_security():
    rdp = {"state": "refused", "protocol": None, "reason": "tls_not_allowed", "at": 1}
    assert mod.rdp_effective(rdp) == {
        "state": "unverified",
        "protocol": "rdp",
        "reason": None,
        "at": 1,
    }


@pytest.mark.parametrize(
    "rdp",
    [
        {"state": "unverified", "protocol": "rdp", "reason": None},
        {"state": "unverified", "protocol": "tls", "reason": None},
        {"state": "ready", "protocol": "nla", "reason": None},
    ],
)
def test_by_default_no_security_level_blocks(rdp):
    assert mod.rdp_effective(rdp) == rdp


def test_a_level_outside_the_policy_is_refused_by_policy():
    rdp = {"state": "unverified", "protocol": "rdp", "reason": None}
    assert mod.rdp_effective(rdp, ("tls", "nla")) == {
        "state": "refused",
        "protocol": "rdp",
        "reason": "security_not_allowed",
    }


def test_the_old_tls_refusal_is_refused_by_a_policy_without_standard_security():
    rdp = {"state": "refused", "protocol": None, "reason": "tls_not_allowed"}
    assert mod.rdp_effective(rdp, ("nla",))["reason"] == "security_not_allowed"


@pytest.mark.parametrize(
    "rdp",
    [
        None,
        {"state": "waiting", "protocol": None, "reason": "port_closed"},
        {"state": "auth_failed", "protocol": "nla", "reason": "auth_failed"},
        {"state": "refused", "protocol": None, "reason": "nla_required"},
        {"state": "unverified", "protocol": None, "reason": "unreachable"},
    ],
)
def test_states_that_are_not_open_or_have_no_protocol_are_left_alone(rdp):
    assert mod.rdp_effective(rdp, ("nla",)) == rdp


RDP_FILE = "audiomode:i:0\nauthentication level:i:2\nnegotiate security layer:i:1"


def test_the_certificate_check_is_read_from_the_rdp_file():
    assert mod.certificate_check(RDP_FILE) == 2
    assert mod.certificate_check("audiomode:i:0") is None
    assert mod.certificate_check(None) is None


def test_setting_the_certificate_check_rewrites_only_that_line():
    assert mod.with_certificate_check(RDP_FILE, 0) == (
        "audiomode:i:0\nauthentication level:i:0\nnegotiate security layer:i:1"
    )


def test_setting_the_certificate_check_adds_the_line_when_missing():
    assert mod.with_certificate_check("audiomode:i:0", 1) == (
        "audiomode:i:0\nauthentication level:i:1"
    )


def test_an_unknown_certificate_check_is_refused():
    with pytest.raises(ValueError):
        mod.with_certificate_check(RDP_FILE, 3)
