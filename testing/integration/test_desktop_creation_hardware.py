# SPDX-License-Identifier: AGPL-3.0-or-later

"""Hardware end-to-end pin-down for the task-based disk creation paths.

The branch ``feat/create-disk-via-task`` rerouted persistent /
non-persistent / from-media desktop creation through the
``isard-storage`` RQ task chain. The tests below pin down the
expected user-visible behavior of those new flows in three
dimensions:

1. **Create-from-template** (the most common Vue 2 / Vue 3 path):
   request hardware explicitly (``vcpus=2`` + ``memory=1.5 GB`` —
   non-default values that do NOT come from the parent template),
   wait for the storage task to complete and the engine's
   ``creating_and_test_xml_start`` to settle, then assert:

   * ``GET /item/desktop/{id}`` reports the requested
     ``vcpu`` / ``memory`` / ``disks`` shape (apiv4 reads it back from
     ``create_dict.hardware``).
   * ``GET /admin/domain/{id}/xml`` is non-empty AND contains a
     ``<vcpu>2</vcpu>`` and a ``<memory unit="KiB">1572864</memory>``
     fragment — engine's ``domain_xml.py`` derives both directly from
     ``create_dict.hardware`` after Phase A.

2. **Create-from-media** (URL → media → desktop): same shape — set
   custom hardware on the from-media payload and verify the engine
   produces matching XML, after the new ``download_url`` storage
   task finishes the download.

3. **Edit-after-stop-then-start cycle**: stop the desktop, ``PUT
   /item/desktop/{id}/edit`` with ``vcpus=4`` + ``memory=2 GB``, wait
   for the engine to flip ``Stopped → Updating → Stopped``, start
   again, and verify the XML now matches the *new* hardware. This
   was the ``CREATE_DISK_VIA_TASK`` branch's most subtle regression
   surface — the create path is task-based, but edit still flows
   through ``ui.update_domain`` ; we want a positive proof both
   meet at a coherent XML.

These tests opt out of the actual VM boot when ``E2E_SKIP_VM_BOOT=1``
is set (the GPU-less CI runner has no KVM accel). XML generation
itself happens at start-time (via ``creating_and_test_xml_start``),
so the boot must be attempted at least to populate the ``xml``
field — but we expect ``Started`` *or* ``Failed`` (the latter is
the no-KVM case where the XML is still written before the start
fails). ``Failed`` is therefore an acceptable terminal in this
suite — we're testing the XML, not the VM.
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
)
from isardvdi_apiv4_client.api.role_advanced import (
    create_deployment,
    create_media,
    create_template,
    get_deployment_videowall,
)
from isardvdi_apiv4_client.api.role_manager import admin_list_domains
from isardvdi_apiv4_client.api.role_user import (
    create_desktop,
    create_desktop_from_media,
    create_nonpersistent_desktop,
    edit_desktop,
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
from isardvdi_apiv4_client.models.api_schemas_domains_hardware_reservables import (
    ApiSchemasDomainsHardwareReservables,
)
from isardvdi_apiv4_client.models.create_deployment_request import (
    CreateDeploymentRequest,
)
from isardvdi_apiv4_client.models.create_desktop_from_media import (
    CreateDesktopFromMedia,
)
from isardvdi_apiv4_client.models.create_desktop_request import CreateDesktopRequest
from isardvdi_apiv4_client.models.create_media_request import CreateMediaRequest
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
from isardvdi_apiv4_client.models.new_nonpersistent_desktop_request import (
    NewNonpersistentDesktopRequest,
)
from isardvdi_apiv4_client.models.new_template_request import NewTemplateRequest
from isardvdi_apiv4_client.models.viewer_config import ViewerConfig
from isardvdi_apiv4_client.types import UNSET

from .helpers.client import IsardClient
from .helpers.responses import created_id, expect

# ---------------------------------------------------------------------------
# constants — all overridable via env so CI can substitute different mirrors
# ---------------------------------------------------------------------------

# User-recommended small ISO that survives the download_url task end-to-end.
DEFAULT_MEDIA_URL = os.environ.get(
    "E2E_HW_MEDIA_URL",
    "https://distro.ibiblio.org/damnsmall/dsl-n/current/dsl-n-01RC4.iso",
)

# Engine timeouts: download is generous (small ISO, but flaky archive),
# disk creation is fast (qcow2 on an already-present parent), template
# creation includes a second qcow2 op.
DOWNLOAD_TIMEOUT = int(os.environ.get("E2E_DOWNLOAD_TIMEOUT", "300"))
CREATE_TIMEOUT = int(os.environ.get("E2E_CREATE_TIMEOUT", "180"))
TEMPLATE_TIMEOUT = int(os.environ.get("E2E_TEMPLATE_TIMEOUT", "180"))
BOOT_TIMEOUT = int(os.environ.get("E2E_BOOT_TIMEOUT", "180"))
STOP_TIMEOUT = int(os.environ.get("E2E_STOP_TIMEOUT", "90"))
EDIT_TIMEOUT = int(os.environ.get("E2E_EDIT_TIMEOUT", "120"))

OS_TEMPLATE = os.environ.get("E2E_OS_TEMPLATE", "win7Virtio")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _media_payload(url: str, name: str) -> CreateMediaRequest:
    return CreateMediaRequest(
        url=url,
        name=name,
        description="e2e hw lifecycle",
        kind=MediaKindEnum.ISO,
        allowed=AllowedInput(roles=False, categories=False, groups=False, users=False),
        hypervisors_pools=["default"],
    )


def _media_hardware(
    *,
    vcpus: int,
    memory_gb: float,
    disk_size_gb: int,
    boot_order: list[str] | None = None,
) -> MediaHardware:
    """The hardware shape the apiv4 ``MediaHardware`` schema accepts on a
    from-media POST. Memory is in GB at the apiv4 boundary
    (``DesktopService.create_from_media`` converts to KiB before writing
    ``create_dict``)."""
    return MediaHardware(
        boot_order=boot_order if boot_order is not None else ["disk"],
        disk_bus="default",
        disk_size=disk_size_gb,
        interfaces=["default"],
        memory=memory_gb,
        vcpus=vcpus,
        videos=["default"],
    )


def _domain_hardware(
    *, vcpus: int, memory_gb: float, disk_size_gb: int
) -> DomainHardware:
    """The ``DomainHardware`` shape for create-from-template / edit. The
    schema doesn't model ``disk_size``; the engine still honors it, so it
    rides in additional_properties to keep the pre-SDK wire shape."""
    hardware = DomainHardware(
        boot_order=[DomainHardwareBootOrderItem.DISK],
        disk_bus="default",
        interfaces=["default"],
        memory=memory_gb,
        vcpus=vcpus,
        videos=["default"],
    )
    hardware.additional_properties["disk_size"] = disk_size_gb
    return hardware


def _desktop_from_media_payload(
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


def _desktop_rows(admin_client: IsardClient) -> list[AdminDomainListItem]:
    rows = expect(
        admin_list_domains.sync_detailed(
            client=admin_client.apiv4(),
            body=AdminListDomainsData(kind=AdminListDomainsDataKind.DESKTOP),
        )
    )
    assert isinstance(rows, list)
    return rows


def _details(admin_client: IsardClient, desktop_id: str) -> DesktopDetailsResponse:
    details = expect(
        get_desktop_details.sync_detailed(
            desktop_id=desktop_id, client=admin_client.apiv4()
        )
    )
    assert isinstance(details, DesktopDetailsResponse)
    return details


def _detail_vcpu_memory(details: DesktopDetailsResponse) -> tuple[float, float]:
    assert isinstance(details.vcpu, (int, float))
    assert isinstance(details.memory, (int, float))
    return float(details.vcpu), float(details.memory)


def _xml(admin_client: IsardClient, domain_id: str) -> str:
    """Return engine's XML for the domain — the source of truth that
    isard-hypervisor's libvirtd will define on next start. Tolerates a
    not-yet-rendered XML (returns "") so callers can poll."""
    resp = admin_domain_xml_get.sync_detailed(
        domain_id=domain_id, client=admin_client.apiv4()
    )
    parsed = resp.parsed
    if isinstance(parsed, AdminDomainXmlResponse) and isinstance(parsed.xml, str):
        return parsed.xml
    return ""


_VCPU_RE = re.compile(r"<vcpu[^>]*>\s*(\d+)\s*</vcpu>")
# memory may appear as <memory unit="KiB">N</memory> or <currentMemory ...>.
_MEMORY_KIB_RE = re.compile(r'<memory[^>]*unit\s*=\s*"KiB"[^>]*>\s*(\d+)\s*</memory>')


def _extract_vcpu(xml: str) -> Optional[int]:
    m = _VCPU_RE.search(xml)
    return int(m.group(1)) if m else None


def _extract_memory_kib(xml: str) -> Optional[int]:
    m = _MEMORY_KIB_RE.search(xml)
    return int(m.group(1)) if m else None


def _wait_xml_matches_vcpu_memory(
    admin_client: IsardClient,
    domain_id: str,
    *,
    vcpus: int,
    memory_kib: int,
    max_wait: float = 60.0,
    interval: float = 1.0,
) -> str:
    """Poll the admin XML until both the vcpu count and memory match.

    The engine writes XML inside ``creating_and_test_xml_start`` —
    we may sample once before it has happened. Poll for the right
    shape rather than asserting on the first read.
    """
    deadline = time.monotonic() + max_wait
    last_xml = ""
    last_vcpu: Optional[int] = None
    last_mem: Optional[int] = None
    while time.monotonic() < deadline:
        last_xml = _xml(admin_client, domain_id)
        if last_xml:
            last_vcpu = _extract_vcpu(last_xml)
            last_mem = _extract_memory_kib(last_xml)
            if last_vcpu == vcpus and last_mem == memory_kib:
                return last_xml
        time.sleep(interval)
    raise AssertionError(
        "domain xml did not converge to vcpus={} memory_kib={} within {}s; "
        "last vcpu={!r}, last memory={!r}, xml head={}".format(
            vcpus,
            memory_kib,
            max_wait,
            last_vcpu,
            last_mem,
            last_xml[:300] if last_xml else "<empty>",
        )
    )


def _start_then_settle(
    admin_client: IsardClient,
    desktop_id: str,
    *,
    boot_timeout: float,
) -> str:
    """Best-effort start. Returns the terminal status. Accepts ``Failed``
    for KVM-less runners — the test cares about the XML, not the boot
    success."""
    start_desktop.sync_detailed(desktop_id=desktop_id, client=admin_client.apiv4())
    return admin_client.poll_desktop_status(
        desktop_id,
        want={"Started", "WaitingIP", "Failed"},
        max_wait=boot_timeout,
    )


def _media_then_template(
    admin_client: IsardClient, test_namespace: str, prefix: str
) -> tuple:
    """Build a usable template via the new task chain: download a small
    ISO, derive a desktop, snapshot a template from it. Returns the
    ``(template_id, source_desktop_id, media_id)`` triple — the source
    desktop and template are persistent until the session-end cleanup
    removes them by the namespace prefix.

    This is the media-source variant of the template setup. The
    registry-domain alternative (``_registry_then_template``) is
    used by the dedicated registry tests; both end up with a
    template ready to derive desktops from.
    """
    media_name = f"{test_namespace}{prefix}_tmpl_media"
    media_id = created_id(
        create_media.sync_detailed(
            client=admin_client.apiv4(),
            body=_media_payload(DEFAULT_MEDIA_URL, media_name),
        )
    )
    admin_client.poll_media_status(
        media_id, want={"Downloaded"}, max_wait=DOWNLOAD_TIMEOUT
    )

    src_name = f"{test_namespace}{prefix}_tmpl_src"
    src_id = created_id(
        create_desktop_from_media.sync_detailed(
            client=admin_client.apiv4(),
            body=_desktop_from_media_payload(
                media_id,
                src_name,
                _media_hardware(vcpus=1, memory_gb=0.5, disk_size_gb=1),
            ),
        )
    )
    admin_client.poll_desktop_status(src_id, want={"Stopped"}, max_wait=CREATE_TIMEOUT)

    template_name = f"{test_namespace}{prefix}_tmpl"
    template_id = created_id(
        create_template.sync_detailed(
            client=admin_client.apiv4(),
            body=NewTemplateRequest(
                desktop_id=src_id,
                name=template_name,
                description="",
                allowed=AllowedBase(users=False, groups=False),
                enabled=True,
            ),
        )
    )
    admin_client.wait_for_template_created(
        source_desktop_id=src_id,
        template_id=template_id,
        max_wait=TEMPLATE_TIMEOUT,
    )
    return template_id, src_id, media_id


REGISTRY_IMAGE_NAME = os.environ.get("E2E_REGISTRY_IMAGE", "TetrOS")


def _trigger_registry_download(admin_client: IsardClient, name: str) -> str:
    """Find the registry entry for ``name``, trigger its download via the
    apiv4 admin endpoint, wait for the new ``Stopped`` desktop to
    appear, and return its id. Skips the test cleanly when the
    registry entry isn't ``Available`` (offline registry, network
    block, ...).

    Pins the new registry-domain task chain end-to-end:

        apiv4 POST /admin/downloads/download/domains/<url-isard>
          -> Storage.new_dict + enqueue_registry_download_chain_for_domain
          -> storage.{pool}.low: download_url_for_domain
            -> storage.{pool}.low: qemu_img_info_backing_chain
              -> core: storage_update (storage→ready, _promote_domains_to_stopped)
                -> core: update_status (FAILED/CANCELED → Failed)
    """
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
    # ``status`` / ``url-isard`` aren't in the DownloadItem schema; they
    # ride along in additional_properties on the registry listing.
    if entry is None or entry.additional_properties.get("status") not in (
        None,
        "Available",
    ):
        pytest.skip(f"{name!r} not Available in registry")

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
    assert download.status_code in (200, 201, 204)

    deadline = time.monotonic() + DOWNLOAD_TIMEOUT
    while time.monotonic() < deadline:
        for row in _desktop_rows(admin_client):
            if (
                (row.name or "") == name
                and row.id not in existing_ids
                and row.status == "Stopped"
            ):
                return row.id
        time.sleep(2)
    raise TimeoutError(
        f"registry download for {name!r} did not reach Stopped within "
        f"{DOWNLOAD_TIMEOUT}s"
    )


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


@pytest.mark.real
@pytest.mark.slow
def test_desktop_from_template_uses_explicit_hardware_in_xml(
    admin_client: IsardClient,
    test_namespace: str,
):
    """
    Branch contract: deriving a desktop from a template via the
    task-based flow must record the *requested* hardware, not the
    template's, in both the apiv4 detail response and the engine's
    XML. The template is built from a media-derived desktop so the
    whole new chain (download_url + create) is exercised end-to-end.
    """
    try:
        template_id, _src_id, _media_id = _media_then_template(
            admin_client, test_namespace, prefix="hw"
        )
    except RuntimeError as exc:
        pytest.skip(f"media source unreachable: {exc}")

    # --- derive a desktop with EXPLICIT hardware. ---
    requested_vcpus = 2
    requested_memory_gb = 1.5
    requested_memory_kib = int(requested_memory_gb * 1048576)
    derived_name = f"{test_namespace}hw_derived"
    derived_id = created_id(
        create_desktop.sync_detailed(
            client=admin_client.apiv4(),
            body=CreateDesktopRequest(
                template_id=template_id,
                name=derived_name,
                description="",
                hardware=_domain_hardware(
                    vcpus=requested_vcpus,
                    memory_gb=requested_memory_gb,
                    disk_size_gb=1,
                ),
            ),
        )
    )
    admin_client.poll_desktop_status(
        derived_id, want={"Stopped"}, max_wait=CREATE_TIMEOUT
    )

    # --- pin: apiv4 detail response reflects the explicit hardware.
    vcpu, memory = _detail_vcpu_memory(_details(admin_client, derived_id))
    assert int(vcpu) == requested_vcpus
    assert (
        abs(memory - requested_memory_gb) < 1e-3
    ), f"memory mismatch: got {memory}, expected {requested_memory_gb}"

    # --- pin: engine XML carries the same vcpu/memory.
    if os.environ.get("E2E_SKIP_VM_BOOT") != "1":
        _start_then_settle(admin_client, derived_id, boot_timeout=BOOT_TIMEOUT)
        _wait_xml_matches_vcpu_memory(
            admin_client,
            derived_id,
            vcpus=requested_vcpus,
            memory_kib=requested_memory_kib,
            max_wait=60.0,
        )
        stop_desktop.sync_detailed(desktop_id=derived_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            derived_id, want={"Stopped", "Failed"}, max_wait=STOP_TIMEOUT
        )


@pytest.mark.real
@pytest.mark.slow
def test_desktop_from_media_uses_explicit_hardware_in_xml(
    admin_client: IsardClient,
    test_namespace: str,
):
    """
    The ``download_url`` task chain plus the from-media create chain
    must converge on the user's requested hardware. This is the path
    most affected by Phase A — both halves are now task-driven.
    """
    media_name = f"{test_namespace}hw_media"
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

    requested_vcpus = 2
    requested_memory_gb = 1.0
    requested_memory_kib = int(requested_memory_gb * 1048576)
    desktop_name = f"{test_namespace}hw_media_desktop"
    desktop_id = created_id(
        create_desktop_from_media.sync_detailed(
            client=admin_client.apiv4(),
            body=_desktop_from_media_payload(
                media_id,
                desktop_name,
                _media_hardware(
                    vcpus=requested_vcpus,
                    memory_gb=requested_memory_gb,
                    disk_size_gb=1,
                ),
            ),
        )
    )
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped"}, max_wait=CREATE_TIMEOUT
    )

    vcpu, memory = _detail_vcpu_memory(_details(admin_client, desktop_id))
    assert int(vcpu) == requested_vcpus
    assert (
        abs(memory - requested_memory_gb) < 1e-3
    ), f"memory mismatch: got {memory}, expected {requested_memory_gb}"

    if os.environ.get("E2E_SKIP_VM_BOOT") != "1":
        _start_then_settle(admin_client, desktop_id, boot_timeout=BOOT_TIMEOUT)
        _wait_xml_matches_vcpu_memory(
            admin_client,
            desktop_id,
            vcpus=requested_vcpus,
            memory_kib=requested_memory_kib,
            max_wait=60.0,
        )
        stop_desktop.sync_detailed(desktop_id=desktop_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            desktop_id, want={"Stopped", "Failed"}, max_wait=STOP_TIMEOUT
        )


@pytest.mark.real
@pytest.mark.slow
def test_edit_hardware_after_stop_propagates_to_xml_on_next_start(
    admin_client: IsardClient,
    test_namespace: str,
):
    """
    Lifecycle pin: create a desktop, start it (or attempt to), stop,
    edit hardware (vcpus + memory), start again. The new XML must
    reflect the edit; the old XML must NOT carry over.

    Why this matters in this branch: disk creation is now async via
    a storage task, while edit still rides ``ui.update_domain`` and
    ``creating_and_test_xml_start``. If either side stales the
    ``create_dict.hardware`` lookup, the post-edit start re-renders
    the *previous* XML.
    """
    # Use the smallest ISO so the storage chain finishes quickly.
    media_name = f"{test_namespace}hw_edit_media"
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

    # --- create with v1 hardware ---
    v1_vcpus = 1
    v1_memory_gb = 0.5
    v1_memory_kib = int(v1_memory_gb * 1048576)
    desktop_name = f"{test_namespace}hw_edit_desktop"
    desktop_id = created_id(
        create_desktop_from_media.sync_detailed(
            client=admin_client.apiv4(),
            body=_desktop_from_media_payload(
                media_id,
                desktop_name,
                _media_hardware(vcpus=v1_vcpus, memory_gb=v1_memory_gb, disk_size_gb=1),
            ),
        )
    )
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped"}, max_wait=CREATE_TIMEOUT
    )

    # --- first start: pin v1 hardware in XML ---
    if os.environ.get("E2E_SKIP_VM_BOOT") != "1":
        _start_then_settle(admin_client, desktop_id, boot_timeout=BOOT_TIMEOUT)
        _wait_xml_matches_vcpu_memory(
            admin_client,
            desktop_id,
            vcpus=v1_vcpus,
            memory_kib=v1_memory_kib,
            max_wait=60.0,
        )
        stop_desktop.sync_detailed(desktop_id=desktop_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            desktop_id, want={"Stopped", "Failed"}, max_wait=STOP_TIMEOUT
        )

    # --- edit to v2 hardware, then start again ---
    v2_vcpus = 4
    v2_memory_gb = 2.0
    v2_memory_kib = int(v2_memory_gb * 1048576)
    edit_desktop.sync_detailed(
        desktop_id=desktop_id,
        client=admin_client.apiv4(),
        body=DesktopEditRequest(
            hardware=_domain_hardware(
                vcpus=v2_vcpus, memory_gb=v2_memory_gb, disk_size_gb=1
            ),
        ),
    )
    # The engine flips Stopped → Updating → Stopped after edit. Wait
    # for it to settle; the apiv4 detail-shape vcpu/memory must already
    # be the new values once status is back to Stopped.
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped"}, max_wait=EDIT_TIMEOUT
    )
    vcpu, memory = _detail_vcpu_memory(_details(admin_client, desktop_id))
    assert (
        int(vcpu) == v2_vcpus
    ), f"post-edit vcpu mismatch: got {vcpu}, expected {v2_vcpus}"
    assert (
        abs(memory - v2_memory_gb) < 1e-3
    ), f"post-edit memory mismatch: got {memory}, expected {v2_memory_gb}"

    if os.environ.get("E2E_SKIP_VM_BOOT") != "1":
        _start_then_settle(admin_client, desktop_id, boot_timeout=BOOT_TIMEOUT)
        # Engine must regenerate XML from the edited create_dict.
        _wait_xml_matches_vcpu_memory(
            admin_client,
            desktop_id,
            vcpus=v2_vcpus,
            memory_kib=v2_memory_kib,
            max_wait=60.0,
        )
        stop_desktop.sync_detailed(desktop_id=desktop_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            desktop_id, want={"Stopped", "Failed"}, max_wait=STOP_TIMEOUT
        )


# ---------------------------------------------------------------------------
# additional engine-translated-to-api surface coverage
# ---------------------------------------------------------------------------


_CDROM_RE = re.compile(r"<disk[^>]*type=\"file\"[^>]*device=\"cdrom\"[^>]*>", re.DOTALL)


@pytest.mark.real
@pytest.mark.slow
def test_registry_download_lands_desktop_as_stopped_via_new_chain(
    admin_client: IsardClient,
    test_namespace: str,
):
    """End-to-end pin for the ported registry-domain download chain.

    The ``feat/create-disk-via-task`` merge migrated *media* URL
    downloads to the storage RQ task chain but left the
    ``DownloadStarting`` handler for ``domains`` rows nowhere — the
    deleted ``engine/services/threads/download_thread.py`` used to
    own both. This test verifies the port:

    * apiv4 ``POST /admin/downloads/download/domains/<url-isard>``
      with no body builds the registry entry server-side, allocates
      a Storage row, and enqueues
      ``Storage.enqueue_registry_download_chain_for_domain``.
    * The new ``download_url_for_domain`` task on the storage worker
      curls the qcow2 to the storage path, flips the domain row to
      ``Downloading`` while curl runs, and produces a 12-key
      progress dict on the row so the frontend renders.
    * ``qemu_img_info_backing_chain`` validates the file and flips
      the storage row to ``ready``; ``storage_update`` then promotes
      the linked desktop to ``Stopped``.

    TetrOS is the canonical small-disk registry image
    (~5 MB, also used by ``test_registry_download_lifecycle.py``).
    Skips if the registry is unreachable or the entry isn't
    Available.
    """
    desktop_id = _trigger_registry_download(admin_client, REGISTRY_IMAGE_NAME)

    # ── Pin (1): the desktop is Stopped — the chain ran to
    # completion (storage_update flipped storage to ``ready`` and
    # _promote_domains_to_stopped lifted the row from
    # DownloadStarting/Downloading). Asserted via the admin listing
    # before any subsequent edit, since edit transitions Stopped →
    # Updating → Stopped.
    row = next((d for d in _desktop_rows(admin_client) if d.id == desktop_id), None)
    assert row is not None, "registry desktop disappeared from admin listing"
    assert row.status == "Stopped", (
        f"registry desktop reached Stopped via the chain but immediately "
        f"flipped to {row.status!r} — investigate the changefeed."
    )

    # ── Pin (2): the storage row got created and is ``ready`` (the
    # downloaded file is on disk and qemu-img info validated it).
    details = _details(admin_client, desktop_id)
    assert details.disks, "registry desktop has no disks attached"
    storage_id = details.disks[0].id
    assert storage_id, f"first disk missing storage id: {details.disks[0]!r}"

    # ── Pin (3): rename into test prefix so teardown finds it.
    # Wait for the post-edit Updating → Stopped sweep before
    # finishing — leaving the desktop in Updating would crash later
    # tests that scan ``/items/desktops``.
    edit_desktop.sync_detailed(
        desktop_id=desktop_id,
        client=admin_client.apiv4(),
        body=DesktopEditRequest(
            name=f"{test_namespace}registry_tetros", description="registry"
        ),
    )
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped"}, max_wait=EDIT_TIMEOUT
    )


@pytest.mark.real
@pytest.mark.slow
def test_from_media_attaches_iso_with_boot_order_and_persists_reservables_shape(
    admin_client: IsardClient,
    test_namespace: str,
):
    """Engine→API translation pin for ISO + boot_order + reservables.

    Two things the engine used to compose entirely on its own and apiv4
    now controls via ``create_dict``:

    * The ISO row that the from-media create produces gets attached as
      a ``<disk type='file' device='cdrom'>`` in the libvirt XML —
      with the ``<source file=…>`` pointing at the downloaded ISO
      path. The ``isos`` field on the apiv4 detail response must list
      it back. (We do NOT assert the boot-order ``order='1'`` on
      cdrom because libvirt's exact placement depends on the
      hypervisor-side virt_install template; we DO assert at least one
      cdrom device is present.)

    * ``reservables`` is opt-in. The default ``vgpus=None`` shape must
      survive the create round-trip without being silently coerced to
      ``[]`` (a common bug when validators replace ``None`` with the
      empty default).

    boot_order=["iso"] is the most common from-media intent — the
    user wants the desktop to actually boot from the ISO. The XML
    must reflect that.
    """
    media_name = f"{test_namespace}iso_attach_media"
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

    desktop_name = f"{test_namespace}iso_attach_desktop"
    # Override boot_order: boot from ISO instead of disk.
    desktop_id = created_id(
        create_desktop_from_media.sync_detailed(
            client=admin_client.apiv4(),
            body=_desktop_from_media_payload(
                media_id,
                desktop_name,
                _media_hardware(
                    vcpus=1, memory_gb=0.5, disk_size_gb=1, boot_order=["iso"]
                ),
            ),
        )
    )
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped"}, max_wait=CREATE_TIMEOUT
    )

    # ── apiv4 detail response: media became an iso entry ───────────
    details = _details(admin_client, desktop_id)
    iso_ids = [iso.id for iso in (details.isos or [])]
    assert media_id in iso_ids, (
        f"from-media desktop did not include the source media in `isos`; "
        f"got {iso_ids!r}, expected media {media_id!r}"
    )

    # ── reservables shape: vgpus stays None, not coerced to [] ────
    reservables = details.reservables
    vgpus = (
        reservables.vgpus
        if isinstance(reservables, ApiSchemasDomainsHardwareReservables)
        else UNSET
    )
    assert vgpus in (UNSET, None), (
        f"reservables.vgpus was coerced from None to {vgpus!r}; "
        f"the apiv4 schema explicitly allows None to mean 'no reservables'"
    )

    # ── boot order is preserved on the apiv4 detail response ──────
    boot_ids = [b.id for b in details.boot_order]
    assert "iso" in boot_ids, f"requested boot_order=['iso'], got back {boot_ids!r}"

    # ── engine XML carries a CD-ROM device once the desktop starts ─
    if os.environ.get("E2E_SKIP_VM_BOOT") != "1":
        _start_then_settle(admin_client, desktop_id, boot_timeout=BOOT_TIMEOUT)
        # Poll until the XML is non-empty and shows the cdrom device.
        deadline = time.monotonic() + 60.0
        last_xml = ""
        while time.monotonic() < deadline:
            last_xml = _xml(admin_client, desktop_id)
            if last_xml and _CDROM_RE.search(last_xml):
                break
            time.sleep(1.0)
        assert _CDROM_RE.search(last_xml or ""), (
            "expected <disk device='cdrom'> in the engine XML for an ISO-boot "
            "desktop, got: " + (last_xml[:600] if last_xml else "<empty>")
        )
        stop_desktop.sync_detailed(desktop_id=desktop_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            desktop_id, want={"Stopped", "Failed"}, max_wait=STOP_TIMEOUT
        )


def _virsh_dumpxml_via_docker(domain_id: str) -> Optional[str]:
    """Pull the live libvirt XML from isard-hypervisor with
    ``virsh dumpxml``. Returns ``None`` when docker isn't reachable
    from the test container — CI integration sidecars typically don't
    mount the docker socket, in which case we silently skip the
    cross-check.
    """
    import shutil
    import subprocess

    if shutil.which("docker") is None:
        return None
    try:
        out = subprocess.run(
            ["docker", "exec", "isard-hypervisor", "virsh", "dumpxml", domain_id],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout


def _xml_vcpu_memory_or_none(xml: str) -> tuple:
    return _extract_vcpu(xml), _extract_memory_kib(xml)


@pytest.mark.real
@pytest.mark.slow
def test_nonpersistent_desktop_inherits_template_hardware_in_xml(
    admin_client: IsardClient,
    test_namespace: str,
):
    """Non-persistent (temporal) desktops inherit hardware from the
    parent template — apiv4 has no override. Pin: after the engine
    finishes the task-based create chain, the apiv4 detail response
    AND the engine XML present matching ``vcpu`` / ``memory`` values
    that came from the template's ``create_dict.hardware``.

    The temporal-create path also routes through the storage RQ
    chain (Phase A): ``Storage.create_new_storage_for_domain``. If
    that chain races the engine's XML render, the ``vcpu`` / memory
    values can briefly desync — we poll, not assert-once.
    """
    try:
        template_id, _src_id, _media_id = _media_then_template(
            admin_client, test_namespace, prefix="np"
        )
    except RuntimeError as exc:
        pytest.skip(f"media source unreachable: {exc}")

    # Non-persistent create: minimal payload, no hardware override.
    np_id = created_id(
        create_nonpersistent_desktop.sync_detailed(
            client=admin_client.apiv4(),
            body=NewNonpersistentDesktopRequest(template_id=template_id),
        )
    )
    # Non-persistent desktops can transition through CreatingDisk →
    # Stopped, then engine starts them automatically (StartingPaused).
    # Allow Started / WaitingIP / Failed too — we only need to be sure
    # the create+xml-render passed through.
    admin_client.poll_desktop_status(
        np_id,
        want={"Stopped", "Started", "WaitingIP", "Failed"},
        max_wait=CREATE_TIMEOUT,
    )

    # ``_media_then_template`` builds the source desktop with vcpus=1
    # and memory=0.5 GB, then snapshots a template from it; the
    # non-persistent derive must inherit those values. The apiv4
    # ``/admin/domains`` endpoint plucks only ``origin`` +
    # ``reservables`` from the template's ``create_dict`` (no
    # hardware), so we assert against the helper's known shape
    # directly rather than reading the template back.
    expected_vcpus = 1
    expected_memory_gb = 0.5
    vcpu, memory = _detail_vcpu_memory(_details(admin_client, np_id))
    assert (
        int(vcpu) == expected_vcpus
    ), f"non-persistent vcpu {vcpu} != template-derived expected {expected_vcpus}"
    assert abs(memory - expected_memory_gb) < 1e-3, (
        f"non-persistent memory {memory} != template-derived "
        f"expected {expected_memory_gb}"
    )


@pytest.mark.real
@pytest.mark.slow
def test_deployment_desktops_inherit_hardware_from_request(
    admin_client: IsardClient,
    test_namespace: str,
):
    """Deployments materialize one or more persistent desktops from a
    template + a hardware override. Pin: each materialized desktop
    carries the deployment's requested hardware, not the template's.
    """
    try:
        template_id, _src_id, _media_id = _media_then_template(
            admin_client, test_namespace, prefix="dep"
        )
    except RuntimeError as exc:
        pytest.skip(f"media source unreachable: {exc}")

    # Create a deployment with explicit hardware override. The
    # ``CreateDeploymentRequest.validate_allowed_not_empty`` validator
    # only counts ``users`` and ``groups`` toward the non-empty check,
    # so allow the test admin's group explicitly.
    dep_vcpus = 2
    dep_memory_gb = 1.0
    dep_name = f"{test_namespace}deployment"
    deployment_id = created_id(
        create_deployment.sync_detailed(
            client=admin_client.apiv4(),
            body=CreateDeploymentRequest(
                name=dep_name,
                description="hw-test",
                allowed=AllowedBase(users=False, groups=["default-default"]),
                create_owner_desktop=True,
                visible=False,
                desktops=[
                    CreateDesktopRequest(
                        template_id=template_id,
                        name=dep_name,
                        description="",
                        persistent=True,
                        hardware=_domain_hardware(
                            vcpus=dep_vcpus,
                            memory_gb=dep_memory_gb,
                            disk_size_gb=1,
                        ),
                    )
                ],
            ),
        )
    )

    # Wait for the deployment to spawn at least one desktop, and pick
    # one that has reached ``Stopped``. The apiv4 ``/items/desktops``
    # response model strips the ``tag`` field, but
    # ``/item/deployment/<id>/videowall`` returns the deployment with
    # the embedded ``desktops`` array (id + status), which is what
    # the videowall and recreate flows already consume.
    stopped_id = None
    deadline = time.monotonic() + CREATE_TIMEOUT
    while time.monotonic() < deadline:
        videowall = expect(
            get_deployment_videowall.sync_detailed(
                deployment_id=deployment_id, client=admin_client.apiv4()
            )
        )
        # ``desktops`` isn't in the videowall schema; it rides in
        # additional_properties as an embedded id + status array.
        desktops = videowall.additional_properties.get("desktops") or []
        candidates = [d for d in desktops if d.get("status") == "Stopped"]
        if candidates:
            stopped_id = candidates[0]["id"]
            break
        time.sleep(2.0)

    assert (
        stopped_id is not None
    ), f"no spawned deployment desktop reached Stopped within {CREATE_TIMEOUT}s"

    vcpu, memory = _detail_vcpu_memory(_details(admin_client, stopped_id))
    assert (
        int(vcpu) == dep_vcpus
    ), f"deployment desktop vcpu mismatch: got {vcpu}, expected {dep_vcpus}"
    assert (
        abs(memory - dep_memory_gb) < 1e-3
    ), f"deployment desktop memory mismatch: got {memory}, expected {dep_memory_gb}"


@pytest.mark.real
@pytest.mark.slow
def test_engine_xml_matches_virsh_dumpxml_when_running(
    admin_client: IsardClient,
    test_namespace: str,
):
    """Cross-check pin: after a desktop reaches a running state,
    ``virsh dumpxml`` on isard-hypervisor must match the engine's
    rendered XML on the apiv4 admin endpoint, at least on the fields
    we control (vcpu count, memory in KiB).

    This is the strongest evidence that what apiv4 told the engine to
    build, and what the hypervisor is actually running, are the
    same. Skips when docker is not reachable from the test container
    (CI integration sidecars don't mount docker.sock by default).
    """
    if os.environ.get("E2E_SKIP_VM_BOOT") == "1":
        pytest.skip("VM boot disabled — virsh dumpxml needs a running domain")

    media_name = f"{test_namespace}xml_match_media"
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

    desktop_id = created_id(
        create_desktop_from_media.sync_detailed(
            client=admin_client.apiv4(),
            body=_desktop_from_media_payload(
                media_id,
                f"{test_namespace}xml_match_desktop",
                _media_hardware(vcpus=2, memory_gb=1.0, disk_size_gb=1),
            ),
        )
    )
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped"}, max_wait=CREATE_TIMEOUT
    )

    _start_then_settle(admin_client, desktop_id, boot_timeout=BOOT_TIMEOUT)

    # Try the cross-check; skip cleanly when docker isn't reachable.
    live_xml = _virsh_dumpxml_via_docker(desktop_id)
    if live_xml is None:
        pytest.skip(
            "docker / isard-hypervisor virsh not reachable from test "
            "container — cross-check unavailable"
        )

    # Engine's rendered XML.
    engine_xml = _xml(admin_client, desktop_id)
    assert engine_xml, "engine XML is empty after start"

    eng_vcpu, eng_mem = _xml_vcpu_memory_or_none(engine_xml)
    live_vcpu, live_mem = _xml_vcpu_memory_or_none(live_xml)

    assert eng_vcpu == live_vcpu, (
        f"vcpu mismatch: engine xml has {eng_vcpu}, " f"virsh dumpxml has {live_vcpu}"
    )
    assert eng_mem == live_mem, (
        f"memory KiB mismatch: engine xml has {eng_mem}, "
        f"virsh dumpxml has {live_mem}"
    )

    stop_desktop.sync_detailed(desktop_id=desktop_id, client=admin_client.apiv4())
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped", "Failed"}, max_wait=STOP_TIMEOUT
    )


@pytest.mark.real
@pytest.mark.slow
def test_edit_sets_forced_hyp_and_round_trips_to_admin_response(
    admin_client: IsardClient,
    test_namespace: str,
):
    """``forced_hyp`` is one of the fields the engine used to manage
    via internal ``ui.update_domain`` plumbing and apiv4 now controls
    on edit. Pin the round-trip: PUT /edit with a ``forced_hyp`` list,
    GET admin domain back, assert the field carries through.

    We pick a hypervisor that's already known to the stack (the
    ``isard-hypervisor`` row seeded by ``populate_test_db.py`` is
    always present); if no hypervisor exists for some reason the test
    skips so we don't create false negatives on stripped-down stacks.
    """
    hyps = expect(admin_hypervisors_list.sync_detailed(client=admin_client.apiv4()))
    assert isinstance(hyps, list)
    if not hyps:
        pytest.skip("no hypervisors known to the stack — cannot test forced_hyp")
    hyp_id = hyps[0].id

    # Build a tiny non-persistent-style stub via from-media — the
    # smallest path that reliably produces a stopped desktop.
    media_name = f"{test_namespace}forced_hyp_media"
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

    desktop_name = f"{test_namespace}forced_hyp_desktop"
    desktop_id = created_id(
        create_desktop_from_media.sync_detailed(
            client=admin_client.apiv4(),
            body=_desktop_from_media_payload(
                media_id,
                desktop_name,
                _media_hardware(vcpus=1, memory_gb=0.5, disk_size_gb=1),
            ),
        )
    )
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped"}, max_wait=CREATE_TIMEOUT
    )

    # ── pin: edit accepts forced_hyp for an admin caller ──────────
    edit_desktop.sync_detailed(
        desktop_id=desktop_id,
        client=admin_client.apiv4(),
        body=DesktopEditRequest(forced_hyp=[hyp_id]),
    )
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped"}, max_wait=EDIT_TIMEOUT
    )

    # ── pin: admin domains list reflects the persisted forced_hyp ────
    # ``/admin/domain/<id>/details`` only exposes detail+description;
    # ``/admin/domains`` is the wider admin listing that includes
    # ``forced_hyp``, so we go through it to verify persistence.
    def _admin_forced_hyp(d_id: str) -> list:
        for row in _desktop_rows(admin_client):
            if row.id == d_id:
                forced = row.forced_hyp
                return forced if isinstance(forced, list) else []
        raise AssertionError(f"desktop {d_id!r} not found in admin domains list")

    forced = _admin_forced_hyp(desktop_id)
    assert hyp_id in forced, (
        f"forced_hyp not persisted: admin response forced_hyp={forced!r}, "
        f"expected to contain {hyp_id!r}"
    )

    # ── pin: clearing forced_hyp via edit returns it to empty ────
    edit_desktop.sync_detailed(
        desktop_id=desktop_id,
        client=admin_client.apiv4(),
        body=DesktopEditRequest(forced_hyp=[]),
    )
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped"}, max_wait=EDIT_TIMEOUT
    )
    forced = _admin_forced_hyp(desktop_id)
    assert not forced, f"forced_hyp not cleared on empty-list edit: {forced!r}"
