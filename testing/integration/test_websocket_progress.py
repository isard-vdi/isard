# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression test for media-from-URL SocketIO progress events.

Pins the backend contract the webapp admin + both frontends rely on:
when a media is downloading, the change-handler emits ``media_update``
events on BOTH ``/userspace`` (room=user) and ``/administrators``
(BaseHandler emits to room=admins for the admin role). Progress must
tick — we assert received_percent > 0 on at least one intermediate
event, and a terminal event with status=="Downloaded".

Historical context: the webapp "upload from URL" progress bar went
silent after the change-handler split landed. Root cause was not in
this handler (BaseHandler already emits to admins), but we keep this
test so a future refactor of the room routing can't silently regress
the admin flow.
"""

from __future__ import annotations

import os
import time

import pytest

from .helpers.client import IsardClient
from .helpers.sockets import SocketIOListener

# Small-enough media to finish within the test budget but large enough
# that progress ticks intermediate percentages (> 0, < 100) before the
# final Downloaded event. MS-DOS 6.22 is ~2.9 MB on archive.org.
DEFAULT_MEDIA_URL = os.environ.get(
    "E2E_MEDIA_URL",
    "https://archive.org/download/ms-dos-6.22_dvd/MS-DOS%206.22.iso",
)


@pytest.mark.real
def test_media_from_url_emits_progress_to_admins_and_userspace(
    admin_client: IsardClient,
    ws: SocketIOListener,
    test_namespace: str,
):
    media_name = f"{test_namespace}bug_c_ws_media"
    ws.clear()

    resp = admin_client.post(
        "/api/v4/item/media",
        json_body={
            "url": DEFAULT_MEDIA_URL,
            "name": media_name,
            "description": "regression: progress WS events reach admins",
            "kind": "iso",
            "allowed": {
                "roles": False,
                "categories": False,
                "groups": False,
                "users": False,
            },
            "hypervisors_pools": ["default"],
        },
    )
    media_id = resp["id"]

    # Wait up to 120 s for the Downloaded terminal event on both
    # namespaces — tiny image, TCG hypervisor, generous budget.
    deadline = time.monotonic() + 120
    saw_progress_admin = False
    saw_progress_user = False
    saw_downloaded_admin = False
    saw_downloaded_user = False

    def matches_media(payload) -> bool:
        return isinstance(payload, dict) and payload.get("id") == media_id

    while time.monotonic() < deadline:
        for ns, event, payload in ws.snapshot():
            if event != "media_update" or not matches_media(payload):
                continue
            progress = payload.get("progress") or {}
            pct = progress.get("received_percent") or progress.get("total_percent") or 0
            try:
                pct = int(pct)
            except (TypeError, ValueError):
                pct = 0
            status = payload.get("status")
            if ns == "/administrators":
                if pct > 0:
                    saw_progress_admin = True
                if status == "Downloaded":
                    saw_downloaded_admin = True
            elif ns == "/userspace":
                if pct > 0:
                    saw_progress_user = True
                if status == "Downloaded":
                    saw_downloaded_user = True
        if (
            saw_progress_admin
            and saw_downloaded_admin
            and saw_progress_user
            and saw_downloaded_user
        ):
            break
        time.sleep(1)

    # Emit the observed events in the failure message so we can see
    # which step actually broke on regression.
    seen = [
        (ns, ev, (pl.get("status") if isinstance(pl, dict) else None))
        for ns, ev, pl in ws.snapshot()
        if ev == "media_update" and matches_media(pl)
    ]
    assert saw_progress_admin, (
        f"no /administrators media_update with received_percent>0 for {media_id}; "
        f"seen={seen}"
    )
    assert (
        saw_downloaded_admin
    ), f"no /administrators media_update with status=Downloaded for {media_id}; seen={seen}"
    assert (
        saw_progress_user
    ), f"no /userspace media_update with received_percent>0 for {media_id}; seen={seen}"
    assert (
        saw_downloaded_user
    ), f"no /userspace media_update with status=Downloaded for {media_id}; seen={seen}"
    # Teardown deletes the media via cleanup_by_prefix (session fixture).
    assert media_id  # pin — teardown finds it by name prefix
