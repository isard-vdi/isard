#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Viewer ownership lookups must not reveal other users' running desktops.

Regression guard for ``DesktopDirectViewer.owns_desktop_viewer_by_ip`` and
``owns_desktop_viewer_by_proxies`` (served by
``POST /item/user/owns-desktop``). Any logged-in user can call them with an
arbitrary IP or proxy tuple, so a lookup that finds no running desktop and
one that finds someone else's must fail identically. Otherwise the
endpoint enumerates running desktops, and it used to also echo the owner's
user, category and deployment in the error description.

Pins:
* no running desktop and someone else's running desktop raise the same
  status code and description,
* the description never contains the other desktop's owner details,
* duplicate matches fail the same way,
* the owner and an admin are still allowed.
"""

from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktop_direct_viewer as mod

DDV = mod.DesktopDirectViewer

OTHER = {"user": "u-other", "category": "c-other", "tag": None}
OWN = {
    "user": "u-1",
    "category": "c-1",
    "tag": None,
    "viewer": {"rdp": {"state": "ready"}},
}


@pytest.fixture
def lookup(monkeypatch):
    """Make every rethink lookup return the list set on ``lookup.domains``."""
    state = MagicMock(domains=[])
    rdb = MagicMock()
    rdb.table.return_value.get_all.return_value.filter.return_value.pluck.return_value.run.side_effect = (
        lambda *_: state.domains
    )
    rdb.table.return_value.get_all.return_value.filter.return_value.filter.return_value.pluck.return_value.run.side_effect = (
        lambda *_: state.domains
    )
    monkeypatch.setattr(mod, "r", rdb)
    monkeypatch.setattr(DDV, "_rdb_context", classmethod(lambda cls: nullcontext()))
    return state


def by_ip(role_id="user"):
    return DDV.owns_desktop_viewer_by_ip(
        user_id="u-1", category_id="c-1", role_id=role_id, guess_ip="10.2.0.5"
    )


def by_proxies(role_id="user"):
    return DDV.owns_desktop_viewer_by_proxies(
        user_id="u-1",
        category_id="c-1",
        role_id=role_id,
        proxy_video="isard.example",
        proxy_hyper_host="isard-hypervisor",
        port=5900,
    )


def _denial(lookup, domains, check):
    lookup.domains = domains
    with pytest.raises(Error) as exc:
        check()
    return exc.value.status_code, exc.value.error["description"]


@pytest.mark.parametrize("check", [by_ip, by_proxies])
def test_missing_and_foreign_desktop_are_indistinguishable(lookup, check):
    missing = _denial(lookup, [], check)
    foreign = _denial(lookup, [OTHER], check)
    duplicated = _denial(lookup, [OTHER, OWN], check)

    assert missing == foreign == duplicated
    assert missing[0] == 403


@pytest.mark.parametrize("check", [by_ip, by_proxies])
def test_denial_does_not_leak_the_owner(lookup, check):
    _, description = _denial(lookup, [OTHER], check)

    for value in ("u-other", "c-other", "10.2.0.5", "isard-hypervisor"):
        assert value not in description


@pytest.mark.parametrize("check", [by_ip, by_proxies])
def test_owner_is_allowed(lookup, check):
    lookup.domains = [OWN]

    assert check() is True


@pytest.mark.parametrize("check", [by_ip, by_proxies])
def test_admin_is_allowed_on_any_desktop(lookup, check):
    lookup.domains = [OTHER]

    assert check(role_id="admin") is True


def test_the_owner_cannot_reach_an_rdp_service_not_verified_yet(lookup):
    lookup.domains = [{**OWN, "viewer": {"rdp": {"state": "waiting"}}}]

    with pytest.raises(Error) as exc:
        by_ip()
    assert exc.value.status_code == 409


def test_reporting_an_outcome_does_not_need_a_verified_rdp(lookup):
    lookup.domains = [{**OWN, "viewer": {"rdp": {"state": "waiting"}}}]

    assert (
        DDV.owns_desktop_viewer_by_ip(
            user_id="u-1",
            category_id="c-1",
            role_id="user",
            guess_ip="192.0.2.5",
            require_rdp_ready=False,
        )
        is True
    )


# rdpgw asks ``owns-desktop`` by IP with the viewer token before every channel:
# whatever closes this check closes native RDP through the gateway.
@pytest.mark.parametrize(
    "rdp",
    [
        {"state": "unverified", "protocol": "rdp", "reason": None},
        {"state": "unverified", "protocol": "tls", "reason": None},
        {"state": "unverified", "protocol": "nla", "reason": "no_credentials"},
        {"state": "ready", "protocol": "nla", "reason": None},
        # what the vpn of older versions stored for a standard-security guest
        {"state": "refused", "protocol": None, "reason": "tls_not_allowed"},
    ],
)
def test_rdpgw_reaches_a_guest_at_every_security_level(lookup, rdp):
    lookup.domains = [{**OWN, "viewer": {"rdp": rdp}}]

    assert by_ip() is True
