# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import os
import random
import time

from cachetools import TTLCache, cached
from flask import request

from api import app

from ..libv2.api_desktops_common import ApiDesktopsCommon
from ..libv2.api_desktops_persistent import ApiDesktopsPersistent
from ..libv2.api_logging import logs_domain_event_directviewer
from ..libv2.rate_limiter import RateLimiter
from .decorators import get_remote_addr, maintenance

common = ApiDesktopsCommon()
desktops = ApiDesktopsPersistent()
rate_limiter = RateLimiter()

NOT_FOUND_RESPONSE = (
    json.dumps({"error": "not_found", "msg": "Not found"}),
    404,
    {"Content-Type": "application/json"},
)

# Floor response time for all failures. Deliberately slow to:
# 1. Make brute-force scanning impractical (~20 tokens/min/IP max)
# 2. Mask timing differences between failure modes
# 3. Match user expectation (frontend shows loading page during wait)
MIN_RESPONSE_TIME = float(os.environ.get("DIRECT_VIEWER_MIN_RESPONSE_TIME", "3.0"))

_ALLOWED_PROTOCOLS = {
    "browser-vnc",
    "browser-rdp",
    "file-spice",
    "file-rdpgw",
    "file-rdpvpn",
}


def _timed_not_found(start_time):
    """Return 404 after enforcing minimum response time with jitter.

    Jitter: +/-0.5s around MIN_RESPONSE_TIME prevents fingerprinting
    the exact floor value.
    """
    elapsed = time.time() - start_time
    target = MIN_RESPONSE_TIME + random.uniform(-0.5, 0.5)
    remaining = target - elapsed
    if remaining > 0:
        time.sleep(remaining)
    return NOT_FOUND_RESPONSE


@app.route("/api/v3/direct/<token>", methods=["GET"])
def api_v3_viewer(token):
    start_time = time.time()

    if rate_limiter.is_limited(request):
        log.warning(f"Rate limited direct viewer request from {request.remote_addr}")
        return _timed_not_found(start_time)

    try:
        maintenance()
        viewers = common.DesktopViewerFromToken(token, request=request)
    except Exception:
        log.warning(f"Direct viewer invalid token from {get_remote_addr(request)}")
        return _timed_not_found(start_time)

    if not viewers:
        return _timed_not_found(start_time)

    vmState = viewers.pop("vmState", None)
    return (
        json.dumps(
            {
                "desktopId": viewers.pop("desktopId", None),
                "jwt": viewers.pop("jwt", None),
                "vmName": viewers.pop("vmName", None),
                "vmDescription": viewers.pop("vmDescription", None),
                "vmState": vmState,
                "scheduled": viewers.pop("scheduled", None),
                "viewers": viewers,
                "needs_booking": viewers.pop("needs_booking", False),
                "next_booking_start": viewers.pop("next_booking_start", None),
                "next_booking_end": viewers.pop("next_booking_end", None),
            }
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/direct/<token>/reset", methods=["PUT"])
def api_v3_desktop_reset(token):
    start_time = time.time()

    if rate_limiter.is_limited(request):
        return _timed_not_found(start_time)

    try:
        maintenance()
        result = desktops.Reset(token, request=request)
    except Exception:
        log.warning(
            f"Direct viewer invalid reset token from {get_remote_addr(request)}"
        )
        return _timed_not_found(start_time)

    return (
        json.dumps({"id": result}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/direct/<token>/viewer/<protocol>", methods=["POST"])
def api_v3_direct_viewer_open(token, protocol):
    start_time = time.time()

    if rate_limiter.is_limited(request):
        return _timed_not_found(start_time)

    if protocol not in _ALLOWED_PROTOCOLS:
        return _timed_not_found(start_time)

    try:
        maintenance()
        domain = common.DesktopFromToken(token)
    except Exception:
        log.warning(f"Direct viewer invalid token from {get_remote_addr(request)}")
        return _timed_not_found(start_time)

    logs_domain_event_directviewer(
        domain["id"],
        action_user=None,
        viewer_type=protocol,
        user_request=request,
    )
    return (json.dumps({}), 200, {"Content-Type": "application/json"})


@cached(cache=TTLCache(maxsize=1, ttl=360))
@app.route("/api/v3/direct/docs", methods=["GET"])
def api_v3_viewer_docs():
    return (
        json.dumps(
            {
                "viewers_documentation_url": os.environ.get(
                    "FRONTEND_VIEWERS_DOCS_URI",
                    "https://isard.gitlab.io/isardvdi-docs/user/viewers/viewers/",
                )
            }
        ),
        200,
        {"Content-Type": "application/json"},
    )
