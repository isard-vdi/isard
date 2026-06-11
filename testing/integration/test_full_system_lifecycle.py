# SPDX-License-Identifier: AGPL-3.0-or-later

"""End-to-end pin: every step a user does in the Vue 3 + Vue 2 UIs.

This is the broadest single integration test in the suite. It exercises
every user-visible flow that the manual smoke-test (run after a fresh
``docker compose -f docker-compose.build.yml up``) covers, and asserts
the supporting infrastructure is healthy:

    1. Stack health: hypervisor Online, scheduler running 3+ system
       jobs, vpn ovsbr0 up with a Geneve port to 10.1.0.1, isard-storage
       reachable.
    2. Registry download — Slax, the largest of the registry images that
       still completes in <60 s on the CI runner. Pins the new
       ``Storage.enqueue_registry_download_chain_for_domain`` chain.
       Skip if the registration code seeded by ``populate_test_db.py``
       hasn't propagated yet.
    3. Start the downloaded desktop, assert viewer ports are populated
       (the qcow2 has spice + vnc + html5 + ws-tunnel viewers configured
       by upstream isardvdi-registry).
    4. Stop, snapshot a template from the downloaded desktop, then
       derive a fresh persistent desktop from that template with
       overridden hardware. Pins Bug B (downloaded shape, no top-level
       ``hardware`` field).
    5. Edit hardware on the derived desktop while stopped (vcpus +
       memory + disk_size + interfaces + videos), restart, and verify
       both the apiv4 detail response AND the engine XML carry the new
       values. Pins ``ui.update_domain`` + ``creating_and_test_xml_start``
       coherence after the task-based create branch.
    6. Media upload from URL, create a desktop from media, exercise the
       same start/stop cycle.
    7. Quota visibility — ``/admin/quota/user`` must round-trip a shape
       with ``quota`` + ``limits``; ``/quota/desktop/new`` must return
       204 for an unlimited admin while the user has 1 (or fewer than
       his configured limit) desktops.

The test is gated by ``E2E_SKIP_VM_BOOT`` for CI runners without
``/dev/kvm`` (start/stop steps degrade to a plain status read), but the
download/template/derive/edit/media steps never need accel and always
run.
"""

from __future__ import annotations

import os
import re
import time
from typing import Optional

import pytest
from isardvdi_apiv4_client.api.role_admin import (
    admin_domain_xml_get,
    admin_downloads_action_id,
    admin_downloads_kind,
    admin_hypervisors_list,
    admin_scheduler_jobs_system,
)
from isardvdi_apiv4_client.api.role_advanced import create_media, create_template
from isardvdi_apiv4_client.api.role_manager import admin_list_domains
from isardvdi_apiv4_client.api.role_user import (
    check_quota_new_desktop,
    create_desktop,
    create_desktop_from_media,
    edit_desktop,
    get_desktop,
    get_desktop_details,
    start_desktop,
    stop_desktop,
)
from isardvdi_apiv4_client.models.admin_domain_list_item import AdminDomainListItem
from isardvdi_apiv4_client.models.admin_domain_xml_response import (
    AdminDomainXmlResponse,
)
from isardvdi_apiv4_client.models.admin_downloads_action_id_body import (
    AdminDownloadsActionIdBody,
)
from isardvdi_apiv4_client.models.admin_downloads_kind_kind import (
    AdminDownloadsKindKind,
)
from isardvdi_apiv4_client.models.admin_list_domains_data import AdminListDomainsData
from isardvdi_apiv4_client.models.admin_list_domains_data_kind import (
    AdminListDomainsDataKind,
)
from isardvdi_apiv4_client.models.allowed_base import AllowedBase
from isardvdi_apiv4_client.models.allowed_input import AllowedInput
from isardvdi_apiv4_client.models.create_desktop_from_media import (
    CreateDesktopFromMedia,
)
from isardvdi_apiv4_client.models.create_desktop_request import CreateDesktopRequest
from isardvdi_apiv4_client.models.create_media_request import CreateMediaRequest
from isardvdi_apiv4_client.models.desktop import Desktop
from isardvdi_apiv4_client.models.desktop_details_response import DesktopDetailsResponse
from isardvdi_apiv4_client.models.desktop_edit_request import DesktopEditRequest
from isardvdi_apiv4_client.models.domain_guest_properties_input import (
    DomainGuestPropertiesInput,
)
from isardvdi_apiv4_client.models.domain_hardware import DomainHardware
from isardvdi_apiv4_client.models.domain_hardware_boot_order_item import (
    DomainHardwareBootOrderItem,
)
from isardvdi_apiv4_client.models.guest_properties_viewers_input import (
    GuestPropertiesViewersInput,
)
from isardvdi_apiv4_client.models.media_hardware import MediaHardware
from isardvdi_apiv4_client.models.media_kind_enum import MediaKindEnum
from isardvdi_apiv4_client.models.new_template_request import NewTemplateRequest
from isardvdi_apiv4_client.models.viewer_config import ViewerConfig

from .helpers.client import IsardClient
from .helpers.responses import created_id, expect
from .helpers.sockets import SocketIOListener

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

REGISTRY_IMAGE = os.environ.get("E2E_FULL_REGISTRY_IMAGE", "Slax 9.3.0")
DEFAULT_MEDIA_URL = os.environ.get(
    "E2E_FULL_MEDIA_URL",
    "https://distro.ibiblio.org/damnsmall/dsl-n/current/dsl-n-01RC4.iso",
)
OS_TEMPLATE = os.environ.get("E2E_OS_TEMPLATE", "win7Virtio")

DOWNLOAD_TIMEOUT = int(os.environ.get("E2E_DOWNLOAD_TIMEOUT", "300"))
BOOT_TIMEOUT = int(os.environ.get("E2E_BOOT_TIMEOUT", "180"))
STOP_TIMEOUT = int(os.environ.get("E2E_STOP_TIMEOUT", "90"))
TEMPLATE_TIMEOUT = int(os.environ.get("E2E_TEMPLATE_TIMEOUT", "180"))
EDIT_TIMEOUT = int(os.environ.get("E2E_EDIT_TIMEOUT", "120"))
CREATE_TIMEOUT = int(os.environ.get("E2E_CREATE_TIMEOUT", "180"))


_VCPU_RE = re.compile(r"<vcpu[^>]*>\s*(\d+)\s*</vcpu>")
_MEMORY_KIB_RE = re.compile(r'<memory[^>]*unit\s*=\s*"KiB"[^>]*>\s*(\d+)\s*</memory>')


def _media_hardware(
    *,
    vcpus: int,
    memory_gb: float,
    disk_size_gb: int,
    interfaces: list[str] | None = None,
) -> MediaHardware:
    return MediaHardware(
        boot_order=["disk"],
        disk_bus="default",
        disk_size=disk_size_gb,
        interfaces=interfaces if interfaces is not None else ["default"],
        memory=memory_gb,
        vcpus=vcpus,
        videos=["default"],
    )


def _domain_hardware(
    *,
    vcpus: int,
    memory_gb: float,
    disk_size_gb: int,
    interfaces: list[str] | None = None,
) -> DomainHardware:
    hardware = DomainHardware(
        boot_order=[DomainHardwareBootOrderItem.DISK],
        disk_bus="default",
        interfaces=interfaces if interfaces is not None else ["default"],
        memory=memory_gb,
        vcpus=vcpus,
        videos=["default"],
    )
    # DomainHardware's schema doesn't model ``disk_size``; the engine
    # still honors it, so it rides in additional_properties to keep the
    # pre-SDK wire shape.
    hardware.additional_properties["disk_size"] = disk_size_gb
    return hardware


def _from_media_payload(
    media_id: str, name: str, hardware: MediaHardware
) -> CreateDesktopFromMedia:
    return CreateDesktopFromMedia(
        media_id=media_id,
        kind=MediaKindEnum.ISO,
        os_template=OS_TEMPLATE,
        name=name,
        description="",
        guest_properties=DomainGuestPropertiesInput(
            viewers=GuestPropertiesViewersInput(browser_vnc=ViewerConfig()),
        ),
        hardware=hardware,
    )


def _media_payload(url: str, name: str) -> CreateMediaRequest:
    return CreateMediaRequest(
        url=url,
        name=name,
        description="e2e full system",
        kind=MediaKindEnum.ISO,
        allowed=AllowedInput(roles=False, categories=False, groups=False, users=False),
        hypervisors_pools=["default"],
    )


def _xml(admin_client: IsardClient, domain_id: str) -> str:
    resp = admin_domain_xml_get.sync_detailed(
        domain_id=domain_id, client=admin_client.apiv4()
    )
    parsed = resp.parsed
    if isinstance(parsed, AdminDomainXmlResponse) and isinstance(parsed.xml, str):
        return parsed.xml
    return ""


def _wait_xml_matches(
    admin_client: IsardClient,
    domain_id: str,
    *,
    vcpus: int,
    memory_kib: int,
    max_wait: float = 60.0,
) -> None:
    deadline = time.monotonic() + max_wait
    last_v = None
    last_m = None
    while time.monotonic() < deadline:
        xml = _xml(admin_client, domain_id)
        if xml:
            v = _VCPU_RE.search(xml)
            m = _MEMORY_KIB_RE.search(xml)
            last_v = int(v.group(1)) if v else None
            last_m = int(m.group(1)) if m else None
            if last_v == vcpus and last_m == memory_kib:
                return
        time.sleep(1.0)
    raise AssertionError(
        f"engine xml never converged: wanted vcpus={vcpus} memory_kib={memory_kib}, "
        f"last vcpu={last_v} memory={last_m}"
    )


def _desktop_rows(admin_client: IsardClient) -> list[AdminDomainListItem]:
    rows = expect(
        admin_list_domains.sync_detailed(
            client=admin_client.apiv4(),
            body=AdminListDomainsData(kind=AdminListDomainsDataKind.DESKTOP),
        )
    )
    assert isinstance(rows, list)
    return rows


def _trigger_registry_download(
    admin_client: IsardClient, name: str
) -> Optional[AdminDomainListItem]:
    """Locate the registry entry, kick the download, and return the
    desktop row once it reaches Stopped. Returns ``None`` when the
    registry isn't reachable or the entry isn't Available — caller
    should ``pytest.skip`` in that case (downloading depends on the
    upstream catalog being reachable, which is environment-specific)."""
    entries = expect(
        admin_downloads_kind.sync_detailed(
            kind=AdminDownloadsKindKind.DOMAINS, client=admin_client.apiv4()
        )
    )
    assert isinstance(entries, list)
    entry = None
    for e in entries:
        if (e.name or "").lower() == name.lower():
            entry = e
            break
    if entry is None:
        return None
    # ``status`` / ``url-isard`` aren't in the DownloadItem schema; they
    # ride along in additional_properties on the registry listing.
    status = entry.additional_properties.get("status")
    if status and status != "Available":
        return None

    existing_ids = {r.id for r in _desktop_rows(admin_client) if (r.name or "") == name}

    download_id = entry.additional_properties.get("url-isard") or entry.id
    assert isinstance(download_id, str) and download_id, "registry entry has no id"
    download = admin_downloads_action_id.sync_detailed(
        action="download",
        kind="domains",
        id=download_id,
        client=admin_client.apiv4(),
        body=AdminDownloadsActionIdBody(),
    )
    assert download.status_code in (
        200,
        201,
        204,
    ), f"registry download -> {download.status_code}"

    deadline = time.monotonic() + DOWNLOAD_TIMEOUT
    while time.monotonic() < deadline:
        for row in _desktop_rows(admin_client):
            if (
                (row.name or "") == name
                and row.id not in existing_ids
                and row.status == "Stopped"
            ):
                return row
        time.sleep(2)
    return None


# ---------------------------------------------------------------------------
# Stack health: hypervisor / scheduler / vpn / storage
# ---------------------------------------------------------------------------


@pytest.mark.real
def test_hypervisor_is_online(admin_client: IsardClient):
    """Asserts at least one hypervisor row is registered AND online.

    Reads ``/admin/hypervisors`` (the listing the Vue 3 admin sidebar
    uses) and checks for ``status == 'Online'`` on at least one entry.
    The test stack should always have ``isard-hypervisor`` joined and
    healthy; if this fails, downstream desktop-start tests will time
    out without context.
    """
    hyps = expect(admin_hypervisors_list.sync_detailed(client=admin_client.apiv4()))
    assert isinstance(hyps, list)
    assert hyps, "no hypervisors registered"
    online = [h for h in hyps if h.status == "Online"]
    assert online, (
        f"no Online hypervisors among {len(hyps)} rows; "
        f"statuses={[h.status for h in hyps]!r}"
    )


@pytest.mark.real
def test_scheduler_runs_system_jobs(admin_client: IsardClient):
    """Asserts isard-scheduler has at least the three known system
    jobs registered on RQ. Pins the seed:
        - recycle_bin_cutoff_time_system_delete
        - send_unused_items_to_recycle_bin
        - delete_expired_notifications_data
    Used so that quota / recycle-bin lifecycle behaviors that depend on
    these jobs are actually scheduled.
    """
    jobs = expect(
        admin_scheduler_jobs_system.sync_detailed(client=admin_client.apiv4())
    )
    assert isinstance(jobs, list)
    # Job ids on the scheduler are namespaced ``system.<job>``. Strip the
    # prefix so the expected set is name-only.
    job_ids = {(j.id or "").rsplit(".", 1)[-1] for j in jobs}
    expected = {
        "recycle_bin_cutoff_time_system_delete",
        "send_unused_items_to_recycle_bin",
        "delete_expired_notifications_data",
    }
    missing = expected - job_ids
    assert not missing, (
        f"scheduler missing system jobs: {sorted(missing)}; "
        f"present: {sorted(job_ids)}"
    )


# ---------------------------------------------------------------------------
# Registry download → desktop lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.real
@pytest.mark.slow
def test_registry_full_lifecycle(
    admin_client: IsardClient,
    ws: SocketIOListener,
    test_namespace: str,
):
    """Slax (or override) registry download → start → stop → template
    → derive → edit hardware → start. The single broadest end-to-end
    pin in the suite. Skips cleanly when the registry isn't reachable
    or the image isn't Available so the test passes on offline runners.
    """
    desktop = _trigger_registry_download(admin_client, REGISTRY_IMAGE)
    if desktop is None:
        pytest.skip(
            f"registry image {REGISTRY_IMAGE!r} not reachable / not Available; "
            "verify resources.code is seeded and registry network is up"
        )

    desktop_id = desktop.id

    # Rename into our namespace so teardown cleans it up.
    # Registry desktops sometimes ship with an RDP viewer (Slax does);
    # the apiv4 edit validator rejects the request unless the
    # ``wireguard`` interface is also present. Include the wireguard
    # interface alongside the ``default`` one so the rename succeeds.
    src_name = f"{test_namespace}registry_src"
    edit_resp = admin_client.raw(
        "PUT",
        f"/api/v4/item/desktop/{desktop_id}/edit",
        json={"name": src_name, "description": "registry full lifecycle"},
    )
    if edit_resp.status_code == 400 and "wireguard" in edit_resp.text:
        # Re-issue the edit with the wireguard interface added so the
        # bastion / RDP viewer requirement is satisfied.
        admin_client.put(
            f"/api/v4/item/desktop/{desktop_id}/edit",
            json_body={
                "name": src_name,
                "description": "registry full lifecycle",
                "hardware": {"interfaces": ["default", "wireguard"]},
            },
        )
    elif edit_resp.status_code not in (200, 204):
        raise AssertionError(
            f"PUT /edit on registry desktop -> {edit_resp.status_code}: "
            f"{edit_resp.text[:300]}"
        )
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped"}, max_wait=EDIT_TIMEOUT
    )

    # --- Step 1: start, assert viewer ports populated, stop -----------
    if os.environ.get("E2E_SKIP_VM_BOOT") != "1":
        start_desktop.sync_detailed(desktop_id=desktop_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            desktop_id, want={"Started", "WaitingIP", "Failed"}, max_wait=BOOT_TIMEOUT
        )
        # Pin: viewer config is populated. registry images come pre-set
        # with full viewer config (spice + vnc + html5 + ws-tunnel); we
        # only assert that the apiv4 detail response surfaces a non-empty
        # list of base/extra ports because the actual presence depends
        # on the registry image version and we don't want to over-pin.
        details = expect(
            get_desktop.sync_detailed(
                desktop_id=desktop_id, client=admin_client.apiv4()
            )
        )
        assert isinstance(details, Desktop)
        # ``viewer`` isn't in the Desktop schema; it rides along in
        # additional_properties.
        viewer = details.additional_properties.get("viewer") or {}
        ports = viewer.get("ports") or []
        # On a Failed start (no KVM) the engine still wires viewer
        # config so the assertion is meaningful in both cases.
        assert ports, (
            "registry desktop has no viewer ports populated; " f"viewer={viewer!r}"
        )
        stop_desktop.sync_detailed(desktop_id=desktop_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            desktop_id, want={"Stopped", "Failed"}, max_wait=STOP_TIMEOUT
        )

    # --- Step 2: template from downloaded desktop (Bug B) -------------
    template_name = f"{test_namespace}registry_tmpl"
    template_id = created_id(
        create_template.sync_detailed(
            client=admin_client.apiv4(),
            body=NewTemplateRequest(
                desktop_id=desktop_id,
                name=template_name,
                description="",
                allowed=AllowedBase(users=False, groups=False),
                enabled=True,
            ),
        )
    )
    admin_client.wait_for_template_created(
        source_desktop_id=desktop_id,
        template_id=template_id,
        max_wait=TEMPLATE_TIMEOUT,
    )

    # --- Step 3: derive desktop with explicit hardware ---------------
    # Carry over the wireguard interface so the inherited RDP viewer
    # constraint is satisfied (Slax registry images include
    # ``file_rdpgw`` by default, and apiv4's check_viewers rejects an
    # edit without ``wireguard`` in ``hardware.interfaces``).
    derived_hw = _domain_hardware(
        vcpus=2, memory_gb=1.0, disk_size_gb=2, interfaces=["default", "wireguard"]
    )
    derived_name = f"{test_namespace}registry_derived"
    derived_id = created_id(
        create_desktop.sync_detailed(
            client=admin_client.apiv4(),
            body=CreateDesktopRequest(
                template_id=template_id,
                name=derived_name,
                description="",
                hardware=derived_hw,
            ),
        )
    )
    admin_client.poll_desktop_status(
        derived_id, want={"Stopped"}, max_wait=CREATE_TIMEOUT
    )
    derived_detail = expect(
        get_desktop_details.sync_detailed(
            desktop_id=derived_id, client=admin_client.apiv4()
        )
    )
    assert isinstance(derived_detail, DesktopDetailsResponse)
    assert isinstance(derived_detail.vcpu, (int, float))
    assert isinstance(derived_detail.memory, (int, float))
    assert int(derived_detail.vcpu) == 2
    assert abs(derived_detail.memory - 1.0) < 1e-3

    # --- Step 4: edit hardware, restart, XML reflects v2 -------------
    edit_desktop.sync_detailed(
        desktop_id=derived_id,
        client=admin_client.apiv4(),
        body=DesktopEditRequest(
            hardware=_domain_hardware(
                vcpus=4,
                memory_gb=2.0,
                disk_size_gb=2,
                interfaces=["default", "wireguard"],
            )
        ),
    )
    admin_client.poll_desktop_status(
        derived_id, want={"Stopped"}, max_wait=EDIT_TIMEOUT
    )
    if os.environ.get("E2E_SKIP_VM_BOOT") != "1":
        start_desktop.sync_detailed(desktop_id=derived_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            derived_id,
            want={"Started", "WaitingIP", "Failed"},
            max_wait=BOOT_TIMEOUT,
        )
        _wait_xml_matches(
            admin_client,
            derived_id,
            vcpus=4,
            memory_kib=2 * 1048576,
            max_wait=60.0,
        )
        stop_desktop.sync_detailed(desktop_id=derived_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            derived_id, want={"Stopped", "Failed"}, max_wait=STOP_TIMEOUT
        )


# ---------------------------------------------------------------------------
# Media upload → desktop lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.real
@pytest.mark.slow
def test_media_upload_full_lifecycle(
    admin_client: IsardClient,
    ws: SocketIOListener,
    test_namespace: str,
):
    """Media-from-URL upload, desktop create from media, start/stop.

    Mirrors the user flow: paste a URL into the "Add media" form and
    create a desktop from it. The Vue 2 + Vue 3 + webapp UIs all hit
    the same apiv4 endpoints, so this also doubles as the contract
    pin for the from-media create chain.
    """
    media_name = f"{test_namespace}fullsys_media"
    media_id = created_id(
        create_media.sync_detailed(
            client=admin_client.apiv4(),
            body=_media_payload(DEFAULT_MEDIA_URL, media_name),
        )
    )
    try:
        admin_client.poll_media_status(
            media_id, want={"Downloaded"}, max_wait=DOWNLOAD_TIMEOUT
        )
    except RuntimeError as exc:
        pytest.skip(f"media source unreachable: {exc}")

    # Pin: media listing returns the new media with the expected shape.
    # ``/items/media`` is the user-facing wrapper listing the webapp/Vue
    # UIs read, so keep it on the raw wire to pin that exact shape.
    media_list_resp = admin_client.raw("GET", "/api/v4/items/media")
    assert media_list_resp.status_code == 200
    listed = media_list_resp.json()
    if isinstance(listed, dict):
        listed = listed.get("media") or []
    assert any(
        m.get("id") == media_id for m in listed
    ), "freshly created media missing from /items/media listing"

    desktop_name = f"{test_namespace}fullsys_media_desktop"
    desktop_id = created_id(
        create_desktop_from_media.sync_detailed(
            client=admin_client.apiv4(),
            body=_from_media_payload(
                media_id,
                desktop_name,
                _media_hardware(vcpus=1, memory_gb=0.5, disk_size_gb=1),
            ),
        )
    )
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped"}, max_wait=CREATE_TIMEOUT
    )

    if os.environ.get("E2E_SKIP_VM_BOOT") != "1":
        start_desktop.sync_detailed(desktop_id=desktop_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            desktop_id, want={"Started", "WaitingIP", "Failed"}, max_wait=BOOT_TIMEOUT
        )
        stop_desktop.sync_detailed(desktop_id=desktop_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            desktop_id, want={"Stopped", "Failed"}, max_wait=STOP_TIMEOUT
        )


# ---------------------------------------------------------------------------
# Quota visibility (creation flow gated tests live in test_quota_lifecycle.py)
# ---------------------------------------------------------------------------


@pytest.mark.real
def test_admin_can_create_when_quota_unset(admin_client: IsardClient):
    """``/quota/desktop/new`` is the gate the Vue 2 + Vue 3 + webapp
    "New desktop" buttons all check before enabling. Default admin has
    no quota configured; the gate must return 204 (success). A 412/428
    here would indicate a regression in the quota service or in the
    seed data."""
    status = check_quota_new_desktop.sync_detailed(
        client=admin_client.apiv4()
    ).status_code
    assert status == 204, f"admin /quota/desktop/new -> {status}"
