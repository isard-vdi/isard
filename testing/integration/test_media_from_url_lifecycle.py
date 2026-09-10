# SPDX-License-Identifier: AGPL-3.0-or-later

"""Full lifecycle on a media added from a URL.

Covers the webapp/Vue flow we routinely regress on:

1. POST a media URL (no ``reservables``; Bug A regression).
2. Wait for download to complete; confirm Downloaded terminal event.
3. Create a desktop from that media, OMITTING ``reservables`` in the
   hardware payload (Bug A second-order regression: MediaHardware was
   reservables-required before the fix).
4. Start, stop, create a template from the stopped desktop (Bug B:
   downloaded-shape desktops have no top-level ``hardware``; template
   creation must use ``create_dict.hardware`` via the shared
   ``resolve_parent_disk`` helper).
5. Derive a new desktop from the template (same Bug B code path).
6. Start + stop the derived desktop.

Teardown deletes everything by name prefix.
"""

from __future__ import annotations

import os

import pytest
from isardvdi_apiv4_client.api.role_advanced import create_media, create_template
from isardvdi_apiv4_client.api.role_user import (
    create_desktop,
    create_desktop_from_media,
    start_desktop,
    stop_desktop,
)
from isardvdi_apiv4_client.models.allowed_base import AllowedBase
from isardvdi_apiv4_client.models.allowed_input import AllowedInput
from isardvdi_apiv4_client.models.create_desktop_from_media import (
    CreateDesktopFromMedia,
)
from isardvdi_apiv4_client.models.create_desktop_request import CreateDesktopRequest
from isardvdi_apiv4_client.models.create_media_request import CreateMediaRequest
from isardvdi_apiv4_client.models.domain_guest_properties_input import (
    DomainGuestPropertiesInput,
)
from isardvdi_apiv4_client.models.guest_properties_viewers_input import (
    GuestPropertiesViewersInput,
)
from isardvdi_apiv4_client.models.media_hardware import MediaHardware
from isardvdi_apiv4_client.models.media_hardware_boot_order_item import (
    MediaHardwareBootOrderItem,
)
from isardvdi_apiv4_client.models.media_kind_enum import MediaKindEnum
from isardvdi_apiv4_client.models.new_template_request import NewTemplateRequest
from isardvdi_apiv4_client.models.viewer_config import ViewerConfig

from .helpers.client import IsardClient
from .helpers.responses import created_id
from .helpers.sockets import SocketIOListener

DEFAULT_MEDIA_URL = os.environ.get(
    "E2E_MEDIA_URL",
    "https://archive.org/download/ms-dos-6.22_dvd/MS-DOS%206.22.iso",
)

# TCG emulation budgets — generous enough for CI, not idle.
BOOT_TIMEOUT = 180
# A guest under nested virtualisation can sit in Shutting-down well past 90s,
# so the stop budget is the larger one.
STOP_TIMEOUT = 180
DOWNLOAD_TIMEOUT = 240
TEMPLATE_TIMEOUT = 180


def _media_payload(url: str, name: str) -> CreateMediaRequest:
    return CreateMediaRequest(
        url=url,
        name=name,
        description="e2e real-stack lifecycle",
        kind=MediaKindEnum.ISO,
        allowed=AllowedInput(roles=False, categories=False, groups=False, users=False),
        hypervisors_pools=["default"],
    )


OS_TEMPLATE = os.environ.get("E2E_OS_TEMPLATE", "win7Virtio")


def _desktop_from_media_payload(media_id: str, name: str) -> CreateDesktopFromMedia:
    # Intentionally omit `reservables` — this exercises the Bug A fix
    # (MediaHardware.reservables must be optional). The os_template we
    # use is a real virt_install row (win7Virtio is the default seed);
    # we never actually boot a Windows 7 OS, just need the XML shape.
    return CreateDesktopFromMedia(
        media_id=media_id,
        kind=MediaKindEnum.ISO,
        os_template=OS_TEMPLATE,
        name=name,
        description="",
        guest_properties=DomainGuestPropertiesInput(
            viewers=GuestPropertiesViewersInput(browser_vnc=ViewerConfig()),
        ),
        hardware=MediaHardware(
            boot_order=[MediaHardwareBootOrderItem.DISK],
            disk_bus="default",
            disk_size=1,
            interfaces=["default"],
            memory=0.5,
            vcpus=1,
            videos=["default"],
        ),
    )


@pytest.mark.real
@pytest.mark.slow
def test_media_from_url_full_lifecycle(
    admin_client: IsardClient,
    ws: SocketIOListener,
    test_namespace: str,
):
    # --- Step 1: create media ---
    media_name = f"{test_namespace}media"
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
        pytest.skip(
            f"media source {DEFAULT_MEDIA_URL} was unreachable during this run: {exc}"
        )

    # --- Step 2: create desktop from media ---
    desktop_name = f"{test_namespace}media_desktop"
    desktop_id = created_id(
        create_desktop_from_media.sync_detailed(
            client=admin_client.apiv4(),
            body=_desktop_from_media_payload(media_id, desktop_name),
        )
    )
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped"}, max_wait=BOOT_TIMEOUT
    )

    # --- Step 3: start → stop (opt-out when KVM accel is unavailable) ---
    if os.environ.get("E2E_SKIP_VM_BOOT") != "1":
        start_desktop.sync_detailed(desktop_id=desktop_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            desktop_id, want={"Started", "WaitingIP"}, max_wait=BOOT_TIMEOUT
        )
        stop_desktop.sync_detailed(desktop_id=desktop_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            desktop_id, want={"Stopped"}, max_wait=STOP_TIMEOUT
        )

    # --- Step 4: create template from stopped desktop (Bug B) ---
    template_name = f"{test_namespace}media_template"
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

    # --- Step 5: derive new desktop from template (Bug B symmetric) ---
    derived_name = f"{test_namespace}media_derived"
    derived_id = created_id(
        create_desktop.sync_detailed(
            client=admin_client.apiv4(),
            body=CreateDesktopRequest(
                template_id=template_id,
                name=derived_name,
                description="",
            ),
        )
    )
    admin_client.poll_desktop_status(
        derived_id, want={"Stopped"}, max_wait=BOOT_TIMEOUT
    )

    # --- Step 6: start → stop derived ---
    if os.environ.get("E2E_SKIP_VM_BOOT") != "1":
        start_desktop.sync_detailed(desktop_id=derived_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            derived_id, want={"Started", "WaitingIP"}, max_wait=BOOT_TIMEOUT
        )
        stop_desktop.sync_detailed(desktop_id=derived_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            derived_id, want={"Stopped"}, max_wait=STOP_TIMEOUT
        )
