#
#   Copyright © 2026 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Thin client for the engine's internal Flask API (isard-engine:5000).

Used to fetch data the engine keeps in process RAM (never in the database),
such as a started desktop's live libvirt XML. Port of upstream MR !4535's
``api/src/api/libv2/api_engine.py``; lives in ``isardvdi_common.helpers``
(mirroring ``isard_vpn.py``) so apiv4 services call it via
``asyncio.to_thread``.
"""

import os
import time
import traceback

import jwt
import requests

from .error_factory import Error

ENGINE_URL = os.environ.get("ENGINE_URL", "http://isard-engine:5000")


def _engine_service_token() -> str:
    """Mint a short-lived admin service JWT the engine's @is_admin accepts."""
    return jwt.encode(
        {
            "exp": int(time.time()) + 30,
            "kid": "isardvdi",
            "data": {
                "role_id": "admin",
                "user_id": "local-default-admin-admin",
                "category_id": "default",
            },
        },
        os.environ["API_ISARDVDI_SECRET"],
        algorithm="HS256",
    )


def get_desktop_live_xml(domain_id: str) -> dict:
    """Return the engine's in-RAM live libvirt XML for a started desktop.

    Returns the engine JSON dict ``{"xml": ..., "hyp": ...}``. Raises Error with
    a meaningful code on not-running (409), not-captured (404), or engine
    failures, so the api error handler maps it to the right HTTP status.
    """
    try:
        resp = requests.get(
            f"{ENGINE_URL}/engine/desktop/{domain_id}/live_xml",
            headers={"Authorization": f"Bearer {_engine_service_token()}"},
            timeout=15,
        )
    except requests.RequestException as e:
        raise Error(
            "gateway_timeout",
            f"engine unreachable: {e}",
            traceback.format_exc(),
        )
    if resp.status_code == 409:
        raise Error("conflict", "Desktop is not running")
    if resp.status_code == 404:
        raise Error(
            "not_found",
            "Live XML not captured for this desktop (restart it to capture)",
        )
    if resp.status_code != 200:
        raise Error(
            "internal_server",
            f"engine returned {resp.status_code} fetching live xml",
        )
    return resp.json()
