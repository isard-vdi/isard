# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
"""Thin client for the engine's internal Flask API (isard-engine:5000).

Used to fetch data the engine keeps in process RAM (never in the database),
such as a started desktop's live libvirt XML.
"""

import os
import time
import traceback

import jwt
import requests
from isardvdi_common.api_exceptions import Error

ENGINE_URL = os.environ.get("ENGINE_URL", "http://isard-engine:5000")


def _engine_service_token():
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


def get_desktop_live_xml(domain_id):
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
