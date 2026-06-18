# SPDX-License-Identifier: AGPL-3.0-or-later

"""Full lifecycle on a desktop downloaded from ``registry.isardvdi.com``.

Downloads TetrOS (small, ~5 MB; the canonical download test image used
by ``testing/test_deployments.sh``), renames it into the session's
prefix so teardown can find it, and exercises the same start → stop →
template → derive → start → stop cycle as the media-from-URL test.

The key regression this pins is **Bug B**: downloaded domains, after
commit 42a235720, carry no top-level ``hardware`` field.
``new_template`` and ``new_from_template`` must resolve the parent
disk via ``create_dict.hardware.disks[0].storage_id`` + the Storage
model. Without the fix, template creation 500s.
"""

from __future__ import annotations

import os
import time

import pytest
from isardvdi_apiv4_client.api.role_admin import (
    admin_downloads_action_id,
    admin_downloads_kind,
)
from isardvdi_apiv4_client.api.role_advanced import create_template
from isardvdi_apiv4_client.api.role_manager import admin_list_domains
from isardvdi_apiv4_client.api.role_user import (
    create_desktop,
    edit_desktop,
    start_desktop,
    stop_desktop,
)
from isardvdi_apiv4_client.models.admin_downloads_kind_kind import (
    AdminDownloadsKindKind,
)
from isardvdi_apiv4_client.models.admin_list_domains_data import AdminListDomainsData
from isardvdi_apiv4_client.models.admin_list_domains_data_kind import (
    AdminListDomainsDataKind,
)
from isardvdi_apiv4_client.models.allowed_base import AllowedBase
from isardvdi_apiv4_client.models.create_desktop_request import CreateDesktopRequest
from isardvdi_apiv4_client.models.desktop_edit_request import DesktopEditRequest
from isardvdi_apiv4_client.models.download_item import DownloadItem
from isardvdi_apiv4_client.models.new_template_request import NewTemplateRequest

from .helpers.client import IsardClient
from .helpers.responses import created_id, expect
from .helpers.sockets import SocketIOListener

REGISTRY_IMAGE_NAME = os.environ.get("E2E_REGISTRY_IMAGE", "TetrOS")

DOWNLOAD_TIMEOUT = 300  # registry + disk write; generous for small runners.
BOOT_TIMEOUT = 180
STOP_TIMEOUT = 90
TEMPLATE_TIMEOUT = 180


def _desktop_rows(admin_client: IsardClient) -> list:
    rows = expect(
        admin_list_domains.sync_detailed(
            client=admin_client.apiv4(),
            body=AdminListDomainsData(kind=AdminListDomainsDataKind.DESKTOP),
        )
    )
    assert isinstance(rows, list)
    return rows


def _find_registry_entry(admin_client: IsardClient, name: str) -> DownloadItem | None:
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


def _wait_for_new_download_desktop(
    admin_client: IsardClient,
    name: str,
    exclude_ids: set[str],
    timeout: float,
) -> str:
    """Poll the admin-domains list until a desktop with ``name`` appears
    whose id is not in ``exclude_ids`` (the set of already-existing
    desktops by that name when the test started)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for row in _desktop_rows(admin_client):
            if (row.name or "") == name and row.id not in exclude_ids:
                return row.id
        time.sleep(2)
    raise TimeoutError(f"no new desktop named {name!r} appeared within {timeout}s")


@pytest.mark.real
@pytest.mark.slow
def test_registry_download_full_lifecycle(
    admin_client: IsardClient,
    ws: SocketIOListener,
    test_namespace: str,
):
    registry_entry = _find_registry_entry(admin_client, REGISTRY_IMAGE_NAME)
    if registry_entry is None:
        pytest.skip(
            f"{REGISTRY_IMAGE_NAME!r} not listed at /api/v4/admin/items/downloads/domains — "
            "check registry reachability / registration"
        )
    # ``status`` / ``url-isard`` aren't in the DownloadItem schema; they ride
    # along in additional_properties on the registry listing.
    status = registry_entry.additional_properties.get("status")
    if status and status != "Available":
        pytest.skip(
            f"{REGISTRY_IMAGE_NAME!r} not Available in registry (status={status!r})"
        )

    # --- Step 1: capture pre-existing desktops by the same name ---
    # The registry download creates a desktop named REGISTRY_IMAGE_NAME.
    # If a developer already has one (outside our prefix), record its id
    # so we don't mistake it for ours later.
    existing_ids = {
        r.id
        for r in _desktop_rows(admin_client)
        if (r.name or "") == REGISTRY_IMAGE_NAME
    }

    # --- Step 2: trigger download ---
    download_id = (
        registry_entry.additional_properties.get("url-isard") or registry_entry.id
    )
    assert isinstance(download_id, str) and download_id, "registry entry has no id"
    download = admin_downloads_action_id.sync_detailed(
        action="download",
        kind="domains",
        id=download_id,
        client=admin_client.apiv4(),
        body=DownloadItem(),
    )
    assert download.status_code in (
        200,
        201,
        204,
    ), f"registry download -> {download.status_code}"

    # --- Step 3: wait for the new domain row to appear ---
    tetros_id = _wait_for_new_download_desktop(
        admin_client,
        REGISTRY_IMAGE_NAME,
        exclude_ids=existing_ids,
        timeout=60,
    )

    # --- Step 4: rename into our namespace so teardown finds it ---
    tetros_name = f"{test_namespace}tetros"
    edit_desktop.sync_detailed(
        desktop_id=tetros_id,
        client=admin_client.apiv4(),
        body=DesktopEditRequest(
            name=tetros_name, description="e2e real-stack lifecycle"
        ),
    )

    # --- Step 5: wait for download complete (status Stopped) ---
    admin_client.poll_desktop_status(
        tetros_id, want={"Stopped"}, max_wait=DOWNLOAD_TIMEOUT
    )

    # --- Step 6: start → stop ---
    if os.environ.get("E2E_SKIP_VM_BOOT") != "1":
        start_desktop.sync_detailed(desktop_id=tetros_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            tetros_id, want={"Started", "WaitingIP"}, max_wait=BOOT_TIMEOUT
        )
        stop_desktop.sync_detailed(desktop_id=tetros_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            tetros_id, want={"Stopped"}, max_wait=STOP_TIMEOUT
        )

    # --- Step 7: create template from stopped downloaded desktop (Bug B) ---
    template_name = f"{test_namespace}tetros_template"
    template_id = created_id(
        create_template.sync_detailed(
            client=admin_client.apiv4(),
            body=NewTemplateRequest(
                desktop_id=tetros_id,
                name=template_name,
                description="",
                allowed=AllowedBase(users=False, groups=False),
                enabled=True,
            ),
        )
    )
    admin_client.wait_for_template_created(
        source_desktop_id=tetros_id,
        template_id=template_id,
        max_wait=TEMPLATE_TIMEOUT,
    )

    # --- Step 8: derive a new desktop from the template ---
    derived_name = f"{test_namespace}tetros_derived"
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

    # --- Step 9: start → stop derived ---
    if os.environ.get("E2E_SKIP_VM_BOOT") != "1":
        start_desktop.sync_detailed(desktop_id=derived_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            derived_id, want={"Started", "WaitingIP"}, max_wait=BOOT_TIMEOUT
        )
        stop_desktop.sync_detailed(desktop_id=derived_id, client=admin_client.apiv4())
        admin_client.poll_desktop_status(
            derived_id, want={"Stopped"}, max_wait=STOP_TIMEOUT
        )
