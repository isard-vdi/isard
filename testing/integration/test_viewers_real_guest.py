# SPDX-License-Identifier: AGPL-3.0-or-later

"""Viewers driven against a real guest downloaded from the registry: SPICE
(channel + first image), RDP over the VPN (a FreeRDP login verified in the
guest's xrdp log) and RDP through rdpgw, each with its negative control.
"""

from __future__ import annotations

import os
import re
import subprocess
import time

import pytest
from isardvdi_apiv4_client.api.role_admin import (
    admin_downloads_action_id,
    admin_downloads_kind,
)
from isardvdi_apiv4_client.api.role_manager import admin_list_domains
from isardvdi_apiv4_client.api.role_user import (
    delete_desktop,
    edit_desktop,
    force_stop_desktop,
    start_desktop,
)
from isardvdi_apiv4_client.models.admin_downloads_kind_kind import (
    AdminDownloadsKindKind,
)
from isardvdi_apiv4_client.models.admin_list_domains_data import AdminListDomainsData
from isardvdi_apiv4_client.models.admin_list_domains_data_kind import (
    AdminListDomainsDataKind,
)
from isardvdi_apiv4_client.models.desktop_edit_request import DesktopEditRequest
from isardvdi_apiv4_client.models.download_item import DownloadItem

from .helpers import freerdp, guest_agent
from .helpers.client import IsardClient
from .helpers.rdp import (
    CLIENT_OFFER,
    PROTOCOL_SSL,
    RdGateway,
    x224_answer,
    x224_request,
)
from .helpers.responses import expect
from .helpers.spice import SpiceError, first_display_image

rethinkdb = pytest.importorskip("rethinkdb")
from rethinkdb import r  # noqa: E402

pytestmark = pytest.mark.real

IMAGE_NAME = os.environ.get("E2E_TEST_IMAGE_NAME", "IsardVDI test desktop")
EXPECTED_DISK_BYTES = int(os.environ.get("E2E_TEST_IMAGE_BYTES", "29697024"))
STORAGE_CONTAINER = os.environ.get("E2E_STORAGE_CONTAINER", "isard-storage")
RDPGW_HOST = os.environ.get("E2E_RDPGW_HOST", "isard-vpn")
RDPGW_PORT = int(os.environ.get("E2E_RDPGW_PORT", "1313"))
# Public test credentials baked into the image (configure.sh); not secrets.
RDP_USER = os.environ.get("E2E_GUEST_USER", "isard")
RDP_PASSWORD = os.environ.get("E2E_GUEST_PASSWORD", "pirineus")

DOWNLOAD_TIMEOUT = 300
NEW_ROW_TIMEOUT = 120
BOOT_TIMEOUT = 180
STOP_TIMEOUT = 180
# Grace before the fixture restarts the desktop to re-publish its guest IP.
GUEST_IP_GRACE = 90
GUEST_IP_TIMEOUT = 150
RDP_READY_TIMEOUT = 180


def _db():
    return r.connect(
        host=os.environ.get("RETHINKDB_HOST", "isard-db"),
        port=int(os.environ.get("RETHINKDB_PORT", "28015")),
        db=os.environ.get("RETHINKDB_DB", "isard"),
    )


def _desktop_ids_named(admin_client: IsardClient, name: str) -> set[str]:
    rows = expect(
        admin_list_domains.sync_detailed(
            client=admin_client.apiv4(),
            body=AdminListDomainsData(kind=AdminListDomainsDataKind.DESKTOP),
        )
    )
    assert isinstance(rows, list)
    return {row.id for row in rows if (row.name or "") == name}


def _registry_entry(admin_client: IsardClient, name: str):
    entries = expect(
        admin_downloads_kind.sync_detailed(
            kind=AdminDownloadsKindKind.DOMAINS, client=admin_client.apiv4()
        )
    )
    assert isinstance(entries, list)
    for entry in entries:
        if (entry.name or "").lower() == name.lower():
            return entry
    return None


@pytest.fixture(scope="module")
def test_image(admin_client: IsardClient, test_namespace: str):
    """Download the test image from the registry; yield its desktop id."""
    # A pre-provisioned desktop (e.g. a pool-imported build not yet on the
    # registry) is driven as-is, skipping the download and the teardown.
    existing = os.environ.get("E2E_TEST_DESKTOP_ID")
    if existing:
        yield existing
        return
    entry = _registry_entry(admin_client, IMAGE_NAME)
    if entry is None:
        pytest.skip(f"{IMAGE_NAME!r} not listed at the downloads registry")
    status = entry.additional_properties.get("status")
    if status and status != "Available":
        pytest.skip(f"{IMAGE_NAME!r} not Available (status={status!r})")

    before = _desktop_ids_named(admin_client, IMAGE_NAME)
    download_id = entry.additional_properties.get("url-isard") or entry.id
    resp = admin_downloads_action_id.sync_detailed(
        action="download",
        kind="domains",
        id=download_id,
        client=admin_client.apiv4(),
        body=DownloadItem(),
    )
    assert resp.status_code in (200, 201, 204), f"download -> {resp.status_code}"

    deadline = time.monotonic() + NEW_ROW_TIMEOUT
    desktop_id = None
    while time.monotonic() < deadline:
        new = _desktop_ids_named(admin_client, IMAGE_NAME) - before
        if new:
            desktop_id = new.pop()
            break
        time.sleep(2)
    assert desktop_id, f"no new {IMAGE_NAME!r} desktop appeared after download"

    edit_desktop.sync_detailed(
        desktop_id=desktop_id,
        client=admin_client.apiv4(),
        body=DesktopEditRequest(
            name=f"{test_namespace}isard_test_v2", description="viewers real-guest"
        ),
    )
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped"}, max_wait=DOWNLOAD_TIMEOUT
    )
    yield desktop_id

    try:
        force_stop_desktop.sync_detailed(
            desktop_id=desktop_id, client=admin_client.apiv4()
        )
        delete_desktop.sync_detailed(desktop_id=desktop_id, client=admin_client.apiv4())
    except Exception:
        pass


def _wait_guest_ip(desktop_id: str, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    with _db() as conn:
        while time.monotonic() < deadline:
            viewer = r.table("domains").get(desktop_id)["viewer"].run(conn)
            if viewer and viewer.get("guest_ip"):
                return viewer["guest_ip"]
            time.sleep(2)
    raise TimeoutError(f"desktop {desktop_id} never reported a guest ip")


# states in which apiv4's check_rdp_open lets the rdpgw open a channel
RDP_OPEN_STATES = ("ready", "unverified")


def _wait_rdp_open(desktop_id: str, timeout: float) -> None:
    """Wait until the engine's VPN check marks the guest's RDP reachable.

    The rdpgw owns-desktop gate refuses a channel until ``viewer.rdp.state``
    is open, so the gateway test needs this, not just a listening port."""
    deadline = time.monotonic() + timeout
    with _db() as conn:
        while time.monotonic() < deadline:
            viewer = r.table("domains").get(desktop_id)["viewer"].default({}).run(conn)
            if (viewer.get("rdp") or {}).get("state") in RDP_OPEN_STATES:
                return
            time.sleep(3)
    raise TimeoutError(f"guest {desktop_id} RDP never became reachable")


def _start_until_guest_ip(admin_client: IsardClient, desktop_id: str) -> str:
    # A desktop started right after another was deleted can have its wireguard
    # guest-IP report rejected by apiv4 and never land; one restart re-publishes it.
    for attempt in range(2):
        start_desktop.sync_detailed(desktop_id=desktop_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            desktop_id, want={"Started", "WaitingIP"}, max_wait=BOOT_TIMEOUT
        )
        try:
            grace = GUEST_IP_GRACE if attempt == 0 else GUEST_IP_TIMEOUT
            return _wait_guest_ip(desktop_id, grace)
        except TimeoutError:
            if attempt:
                raise
            force_stop_desktop.sync_detailed(
                desktop_id=desktop_id, client=admin_client.apiv4()
            )
            admin_client.poll_desktop_status(
                desktop_id, want={"Stopped"}, max_wait=STOP_TIMEOUT
            )
    raise TimeoutError(f"desktop {desktop_id} never reported a guest ip")


@pytest.fixture(scope="module")
def started(admin_client: IsardClient, test_image: str):
    """Start the downloaded desktop and wait until it serves its viewers."""
    guest_ip = _start_until_guest_ip(admin_client, test_image)
    _wait_rdp_open(test_image, RDP_READY_TIMEOUT)
    with _db() as conn:
        viewer = r.table("domains").get(test_image)["viewer"].run(conn)
    yield {"id": test_image, "guest_ip": guest_ip, "viewer": viewer}
    try:
        guest_agent.run(test_image, f"pkill -u {RDP_USER} 2>/dev/null || true")
    except Exception:
        pass
    force_stop_desktop.sync_detailed(desktop_id=test_image, client=admin_client.apiv4())


@pytest.fixture(scope="module")
def freerdp_image():
    freerdp.ensure_image()


def _spice_target(started) -> tuple[str, int]:
    viewer = started["viewer"]
    return viewer["proxy_hyper_host"], int(viewer["base_port"])


def _current_ticket(desktop_id: str) -> str:
    with _db() as conn:
        return r.table("domains").get(desktop_id)["viewer"]["passwd"].run(conn)


@pytest.mark.slow
def test_downloaded_disk_has_the_expected_size(test_image: str):
    with _db() as conn:
        disks = (
            r.table("domains")
            .get(test_image)["create_dict"]["hardware"]["disks"]
            .run(conn)
        )
        storage_id = disks[0]["storage_id"]
        directory = r.table("storage").get(storage_id)["directory_path"].run(conn)
    path = f"{directory.rstrip('/')}/{storage_id}.qcow2"
    out = subprocess.run(
        ["docker", "exec", STORAGE_CONTAINER, "stat", "-c", "%s", path],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.returncode == 0, f"stat {path} -> {out.stderr.strip()}"
    assert int(out.stdout.strip()) == EXPECTED_DISK_BYTES


@pytest.mark.slow
def test_spice_channel_opens_and_shows_the_first_image(started):
    host, port = _spice_target(started)
    message = first_display_image(host, port, _current_ticket(started["id"]))
    assert message, "no first display image message returned"


@pytest.mark.slow
def test_spice_rejects_a_wrong_ticket(started):
    host, port = _spice_target(started)
    with pytest.raises(SpiceError):
        first_display_image(host, port, "not-the-ticket")


@pytest.mark.slow
def test_rdp_through_the_gateway_reaches_the_guest(admin_client, started):
    resp = admin_client.raw(
        "GET", f"/api/v4/item/desktop/{started['id']}/get-viewer/file-rdpgw"
    )
    assert resp.status_code == 200, resp.text[:300]
    token = re.search(r"^gatewayaccesstoken:s:(.+)$", resp.json()["content"], re.M)
    assert token, "no gateway token in the .rdp file"
    gateway = RdGateway(RDPGW_HOST, RDPGW_PORT)
    try:
        gateway.open_channel(token.group(1).strip(), started["guest_ip"])
        answer = gateway.rdp_exchange(x224_request(CLIENT_OFFER))
    finally:
        gateway.close()
    assert x224_answer(answer) == ("selected", PROTOCOL_SSL)


@pytest.mark.slow
def test_rdp_over_the_vpn_logs_in_and_starts_a_session(started, freerdp_image):
    _, before, _ = guest_agent.run(started["id"], "wc -l < /var/log/xrdp-sesman.log")
    freerdp.attempt_login(started["guest_ip"], RDP_USER, RDP_PASSWORD, hold=15)
    _, new_lines, _ = guest_agent.run(
        started["id"], f"tail -n +{int(before) + 1} /var/log/xrdp-sesman.log"
    )
    assert f"Access permitted for user: {RDP_USER}" in new_lines, new_lines
    assert "Starting X server on display" in new_lines, new_lines


@pytest.mark.slow
def test_rdp_over_the_vpn_rejects_a_wrong_password(started, freerdp_image):
    _, before, _ = guest_agent.run(started["id"], "wc -l < /var/log/xrdp-sesman.log")
    freerdp.attempt_login(
        started["guest_ip"], RDP_USER, f"wrong-{os.urandom(4).hex()}", hold=10
    )
    _, new_lines, _ = guest_agent.run(
        started["id"], f"tail -n +{int(before) + 1} /var/log/xrdp-sesman.log"
    )
    assert "AUTHFAIL" in new_lines, new_lines
    assert f"Access permitted for user: {RDP_USER}" not in new_lines, new_lines
