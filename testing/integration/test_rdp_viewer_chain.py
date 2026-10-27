# SPDX-License-Identifier: AGPL-3.0-or-later

"""RDP viewers end to end: vpn check, viewer gate, rdpgw and the security policy.

The desktop is a Started copy of a seeded row with a fake guest inside
isard-vpn; the engine is paused meanwhile so its broom does not stop it. The
chain tests run with no policy set, as on a fresh install.
"""

from __future__ import annotations

import os
import re
import subprocess
import time

import pytest

from .helpers.client import IsardClient
from .helpers.rdp import (
    CLIENT_OFFER,
    PROTOCOL_HYBRID_EX,
    PROTOCOL_RDP,
    PROTOCOL_SSL,
    GatewayError,
    RdGateway,
    start_fake_guest,
    x224_answer,
    x224_request,
)

rethinkdb = pytest.importorskip("rethinkdb")
from rethinkdb import r  # noqa: E402

VPN_CONTAINER = os.environ.get("E2E_VPN_CONTAINER", "isard-vpn")
ENGINE_CONTAINER = os.environ.get("E2E_ENGINE_CONTAINER", "isard-engine")
RDPGW_HOST = os.environ.get("E2E_RDPGW_HOST", "isard-vpn")
RDPGW_PORT = int(os.environ.get("E2E_RDPGW_PORT", "1313"))
USER01_USERNAME = os.environ.get("E2E_USER01_USERNAME", "user01")
USER01_PASSWORD = os.environ.get("E2E_USER01_PASSWORD", "a?)49hgT")
USER01_CATEGORY = os.environ.get("E2E_USER01_CATEGORY", "default")

FIXTURE_ID = "ws-ip-arrival-fixture-0001"
DESKTOP_ID = "integration-rdp-viewer-chain"
RDP_VIEWERS = ("file-rdpgw", "browser-rdp", "file-rdpvpn")
# one loopback address per guest flavour: the vpn checks key a desktop by its
# address, so moving the desktop to another flavour's address re-checks it
GUESTS = {"rdp": "127.0.0.31", "tls": "127.0.0.32", "nla": "127.0.0.33"}
EXPECTED = {
    "rdp": ("unverified", "rdp"),
    "tls": ("unverified", "tls"),
    # the copy has no stored credentials, so NLA cannot be verified either
    "nla": ("unverified", "nla"),
}


def _db():
    return r.connect(
        host=os.environ.get("RETHINKDB_HOST", "isard-db"),
        port=int(os.environ.get("RETHINKDB_PORT", "28015")),
        db=os.environ.get("RETHINKDB_DB", "isard"),
    )


@pytest.fixture(scope="module")
def user_client() -> IsardClient:
    client = IsardClient()
    client.login(USER01_USERNAME, USER01_PASSWORD, category_id=USER01_CATEGORY)
    return client


@pytest.fixture(scope="module")
def guests():
    for flavour, ip in GUESTS.items():
        start_fake_guest(VPN_CONTAINER, ip, flavour)
    time.sleep(2)
    return GUESTS


def _docker(*argv):
    subprocess.run(["docker", *argv], check=True, capture_output=True, timeout=60)


def _placeable_hypervisors():
    with _db() as conn:
        return set(
            r.table("hypervisors")
            .filter(
                lambda hyper: (hyper["status"] == "Online")
                & ~hyper["degraded"]["is_degraded"].default(False)
            )
            .get_field("id")
            .run(conn)
        )


def _wait_for_the_engine_to_settle(since, placeable, timeout=180):
    # a libvirt check frozen by the pause times out on unpause and marks its
    # hypervisor degraded until the next clean broom pass
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        logs = subprocess.run(
            ["docker", "logs", "--since", str(int(since)), ENGINE_CONTAINER],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if "overrun=no" in logs.stdout + logs.stderr and placeable <= (
            _placeable_hypervisors()
        ):
            # apiv4 caches the online hypervisors for 10 s
            time.sleep(11)
            return
        time.sleep(2)
    raise AssertionError(f"the engine did not settle after unpausing: {placeable}")


@pytest.fixture(scope="module")
def engine_paused():
    placeable = _placeable_hypervisors()
    _docker("pause", ENGINE_CONTAINER)
    try:
        yield
    finally:
        since = time.time()
        _docker("unpause", ENGINE_CONTAINER)
        _wait_for_the_engine_to_settle(since, placeable)


@pytest.fixture(scope="module")
def desktop(user_client, guests, engine_paused):
    with _db() as conn:
        row = r.table("domains").get(FIXTURE_ID).run(conn)
        if not row:
            pytest.skip(f"seed desktop {FIXTURE_ID} missing")
        user = r.table("users").get(user_client.user_id).run(conn)
        row = dict(row)
        row.update(
            {
                "id": DESKTOP_ID,
                "name": "integration rdp viewer chain",
                "user": user["id"],
                "username": user["username"],
                "category": user["category"],
                "group": user["group"],
                "status": "Started",
                "viewer": {"guest_ip": None},
            }
        )
        gp = dict(row.get("guest_properties") or {})
        gp["credentials"] = {"username": "", "password": ""}
        row["guest_properties"] = gp
        r.table("domains").insert(row, conflict="replace").run(conn)
    yield DESKTOP_ID
    with _db() as conn:
        r.table("domains").get(DESKTOP_ID).delete().run(conn)


def _set_policy(admin_client: IsardClient, **policy):
    admin_client.put("/api/v4/admin/item/rdp-security", policy)
    # apiv4 keeps a built viewer for 2 s
    time.sleep(3)


@pytest.fixture
def default_policy(admin_client):
    """Every RDP security level allowed; restores the certificate check after."""
    before = admin_client.get("/api/v4/admin/item/rdp-security")
    _set_policy(admin_client, allowed_protocols=["rdp", "tls", "nla"])
    yield
    _set_policy(
        admin_client,
        allowed_protocols=before["allowed_protocols"],
        certificate_check=before["certificate_check"],
    )


# what the engine writes in ``viewer`` when it starts a desktop, enough for
# apiv4 to build the viewers (no hypervisor serves them here)
STARTED_VIEWER = {
    "base_port": 5900,
    "ports": [5900, 5901, 5902],
    "passwd": "integration",
    "static": "isard-portal",
    "proxy_video": "isard-portal",
    "proxy_hyper_host": "isard-hypervisor",
}


def _move_to(desktop_id: str, ip: str, timeout: float = 60) -> dict:
    """Give the desktop the guest address ``ip``; wait for the vpn check to report it."""
    with _db() as conn:
        viewer = r.table("domains").get(desktop_id)["viewer"].run(conn)
        if viewer.get("guest_ip") == ip and (viewer.get("rdp") or {}).get("state"):
            # already there: the vpn does not check the same address twice
            return viewer["rdp"]
        r.table("domains").get(desktop_id).update(
            {
                "status": "Started",
                "viewer": r.literal({**STARTED_VIEWER, "guest_ip": ip}),
            }
        ).run(conn)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            viewer = r.table("domains").get(desktop_id)["viewer"].run(conn)
            rdp = viewer.get("rdp") or {}
            if viewer.get("guest_ip") == ip and rdp.get("state") not in (
                None,
                "pending",
                "waiting",
                "verifying",
            ):
                return rdp
            time.sleep(1)
    pytest.fail(f"no RDP state reported by the vpn for {ip}: {viewer!r}")


def _viewer(client: IsardClient, desktop_id: str, viewer: str):
    return client.raw("GET", f"/api/v4/item/desktop/{desktop_id}/get-viewer/{viewer}")


def _gateway_token(client: IsardClient, desktop_id: str) -> tuple[str, str]:
    """The viewer token and the ``.rdp`` text of the RD Gateway file."""
    resp = _viewer(client, desktop_id, "file-rdpgw")
    assert resp.status_code == 200, resp.text[:300]
    content = resp.json()["content"]
    token = re.search(r"^gatewayaccesstoken:s:(.+)$", content, re.M)
    assert token, f"no gateway token in the .rdp file:\n{content}"
    return token.group(1).strip(), content


def _rdpgw_owns(token: str, ip: str):
    """The call rdpgw makes before opening a channel to ``ip``."""
    client = IsardClient()
    client.token = token
    client._token_exp = time.time() + 3600
    return client.raw("POST", "/api/v4/item/user/owns-desktop", json={"ip": ip})


@pytest.mark.real
@pytest.mark.parametrize("flavour", ["rdp", "tls", "nla"])
def test_every_guest_security_level_opens_every_rdp_viewer(
    flavour, desktop, user_client
):
    rdp = _move_to(desktop, GUESTS[flavour])
    assert (rdp["state"], rdp.get("protocol")) == EXPECTED[flavour]
    for viewer in RDP_VIEWERS:
        resp = _viewer(user_client, desktop, viewer)
        assert resp.status_code == 200, f"{viewer}: {resp.status_code} {resp.text}"
    token, _ = _gateway_token(user_client, desktop)
    resp = _rdpgw_owns(token, GUESTS[flavour])
    assert resp.status_code == 200, f"owns-desktop: {resp.status_code} {resp.text}"


@pytest.mark.real
@pytest.mark.parametrize(
    "flavour, offer, expected",
    [
        # mstsc offers TLS and NLA first; a standard-security guest refuses
        # and mstsc reconnects offering plain RDP
        ("rdp", CLIENT_OFFER, ("failure", 2)),
        ("rdp", PROTOCOL_RDP, ("selected", PROTOCOL_RDP)),
        ("tls", CLIENT_OFFER, ("selected", PROTOCOL_SSL)),
        ("nla", CLIENT_OFFER, ("selected", PROTOCOL_HYBRID_EX)),
    ],
)
def test_rdpgw_carries_the_rdp_negotiation_to_the_guest_and_back(
    flavour, offer, expected, desktop, user_client
):
    _move_to(desktop, GUESTS[flavour])
    token, _ = _gateway_token(user_client, desktop)
    gateway = RdGateway(RDPGW_HOST, RDPGW_PORT)
    try:
        gateway.open_channel(token, GUESTS[flavour])
        answer = gateway.rdp_exchange(x224_request(offer))
    finally:
        gateway.close()
    assert x224_answer(answer) == expected


@pytest.mark.real
def test_rdpgw_refuses_a_channel_to_an_address_the_user_does_not_own(
    desktop, user_client
):
    _move_to(desktop, GUESTS["tls"])
    token, _ = _gateway_token(user_client, desktop)
    gateway = RdGateway(RDPGW_HOST, RDPGW_PORT)
    try:
        with pytest.raises((GatewayError, EOFError)):
            gateway.open_channel(token, GUESTS["nla"])
    finally:
        gateway.close()


@pytest.mark.real
def test_a_level_the_admin_does_not_allow_closes_the_rdp_viewers_and_rdpgw(
    desktop, user_client, admin_client, default_policy
):
    _move_to(desktop, GUESTS["rdp"])
    token, _ = _gateway_token(user_client, desktop)
    _set_policy(admin_client, allowed_protocols=["tls", "nla"])
    for viewer in RDP_VIEWERS:
        resp = _viewer(user_client, desktop, viewer)
        assert resp.status_code == 409, f"{viewer}: {resp.status_code} {resp.text}"
        assert "rdp_security_not_allowed" in resp.text
    assert _rdpgw_owns(token, GUESTS["rdp"]).status_code != 200
    desktops = user_client.get("/api/v4/item/user/desktops")
    desktops = desktops if isinstance(desktops, list) else desktops.get("desktops", [])
    shown = next(d for d in desktops if d["id"] == desktop)
    assert shown["rdp"]["state"] == "refused"
    assert shown["rdp"]["reason"] == "security_not_allowed"

    # a level the policy still allows is not affected
    _move_to(desktop, GUESTS["tls"])
    assert _viewer(user_client, desktop, "file-rdpgw").status_code == 200

    # and allowing it again opens it, with no new check needed
    _set_policy(admin_client, allowed_protocols=["rdp", "tls", "nla"])
    _move_to(desktop, GUESTS["rdp"])
    assert _viewer(user_client, desktop, "file-rdpgw").status_code == 200


@pytest.mark.real
@pytest.mark.parametrize("level", [0, 1, 2])
def test_the_certificate_check_reaches_the_rdp_files(
    level, desktop, user_client, admin_client, default_policy
):
    _set_policy(
        admin_client,
        allowed_protocols=["rdp", "tls", "nla"],
        certificate_check=level,
    )
    assert (
        admin_client.get("/api/v4/admin/item/rdp-security")["certificate_check"]
        == level
    )
    _move_to(desktop, GUESTS["tls"])
    _, content = _gateway_token(user_client, desktop)
    assert re.findall(r"^authentication level:i:(\d)", content, re.M) == [str(level)]
