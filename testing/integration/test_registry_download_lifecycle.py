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

from .helpers.client import IsardClient
from .helpers.sockets import SocketIOListener

REGISTRY_IMAGE_NAME = os.environ.get("E2E_REGISTRY_IMAGE", "TetrOS")

DOWNLOAD_TIMEOUT = 300  # registry + disk write; generous for small runners.
BOOT_TIMEOUT = 180
STOP_TIMEOUT = 90
TEMPLATE_TIMEOUT = 180


def _find_registry_entry(admin_client: IsardClient, name: str) -> dict | None:
    entries = admin_client.get("/api/v4/admin/downloads/domains")
    for entry in entries:
        if (entry.get("name") or "").lower() == name.lower():
            return entry
    return None


def _find_existing_downloaded_desktop(
    admin_client: IsardClient, name: str
) -> dict | None:
    """Find a TetrOS-named desktop already owned by any admin (not ours)."""
    rows = (
        admin_client.post("/api/v4/admin/domains", json_body={"kind": "desktop"}) or []
    )
    for row in rows:
        if (row.get("name") or "") == name:
            return row
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
        rows = (
            admin_client.post("/api/v4/admin/domains", json_body={"kind": "desktop"})
            or []
        )
        for row in rows:
            if (row.get("name") or "") == name and row["id"] not in exclude_ids:
                return row["id"]
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
            f"{REGISTRY_IMAGE_NAME!r} not listed at /api/v4/admin/downloads/domains — "
            "check registry reachability / registration"
        )
    if registry_entry.get("status") and registry_entry["status"] != "Available":
        pytest.skip(
            f"{REGISTRY_IMAGE_NAME!r} not Available in registry "
            f"(status={registry_entry['status']!r})"
        )

    # --- Step 1: capture pre-existing desktops by the same name ---
    # The registry download creates a desktop named REGISTRY_IMAGE_NAME.
    # If a developer already has one (outside our prefix), record its id
    # so we don't mistake it for ours later.
    existing_rows = (
        admin_client.post("/api/v4/admin/domains", json_body={"kind": "desktop"}) or []
    )
    existing_ids = {
        r["id"] for r in existing_rows if (r.get("name") or "") == REGISTRY_IMAGE_NAME
    }

    # --- Step 2: trigger download ---
    admin_client.post(
        f"/api/v4/admin/downloads/download/domains/{registry_entry['id']}",
        expected=(200, 201, 204),
    )

    # --- Step 3: wait for the new domain row to appear ---
    tetros_id = _wait_for_new_download_desktop(
        admin_client,
        REGISTRY_IMAGE_NAME,
        exclude_ids=existing_ids,
        timeout=60,
    )

    # --- Step 4: rename into our namespace so teardown finds it ---
    tetros_name = f"{test_namespace}tetros"
    admin_client.raw(
        "PUT",
        f"/api/v4/item/desktop/{tetros_id}/edit",
        json={"name": tetros_name, "description": "e2e real-stack lifecycle"},
    )

    # --- Step 5: wait for download complete (status Stopped) ---
    admin_client.poll_desktop_status(
        tetros_id, want={"Stopped"}, max_wait=DOWNLOAD_TIMEOUT
    )

    # --- Step 6: start → stop ---
    if os.environ.get("E2E_SKIP_VM_BOOT") != "1":
        admin_client.raw("PUT", f"/api/v4/item/desktop/{tetros_id}/start")
        admin_client.poll_desktop_status(
            tetros_id, want={"Started", "WaitingIP"}, max_wait=BOOT_TIMEOUT
        )
        admin_client.raw("PUT", f"/api/v4/item/desktop/{tetros_id}/stop")
        admin_client.poll_desktop_status(
            tetros_id, want={"Stopped"}, max_wait=STOP_TIMEOUT
        )

    # --- Step 7: create template from stopped downloaded desktop (Bug B) ---
    template_name = f"{test_namespace}tetros_template"
    template = admin_client.post(
        "/api/v4/item/template",
        json_body={
            "desktop_id": tetros_id,
            "name": template_name,
            "description": "",
            "allowed": {"users": False, "groups": False},
            "enabled": True,
        },
    )
    template_id = template["id"]
    admin_client.wait_for_template_created(
        source_desktop_id=tetros_id,
        template_id=template_id,
        max_wait=TEMPLATE_TIMEOUT,
    )

    # --- Step 8: derive a new desktop from the template ---
    derived_name = f"{test_namespace}tetros_derived"
    derived = admin_client.post(
        "/api/v4/item/desktop",
        json_body={
            "template_id": template_id,
            "name": derived_name,
            "description": "",
        },
    )
    derived_id = derived["id"]
    admin_client.poll_desktop_status(
        derived_id, want={"Stopped"}, max_wait=BOOT_TIMEOUT
    )

    # --- Step 9: start → stop derived ---
    if os.environ.get("E2E_SKIP_VM_BOOT") != "1":
        admin_client.raw("PUT", f"/api/v4/item/desktop/{derived_id}/start")
        admin_client.poll_desktop_status(
            derived_id, want={"Started", "WaitingIP"}, max_wait=BOOT_TIMEOUT
        )
        admin_client.raw("PUT", f"/api/v4/item/desktop/{derived_id}/stop")
        admin_client.poll_desktop_status(
            derived_id, want={"Stopped"}, max_wait=STOP_TIMEOUT
        )
