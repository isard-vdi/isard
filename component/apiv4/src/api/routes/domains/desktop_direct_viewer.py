#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Miriam Melina Gamboa Valdez
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import logging
import random
import time
import traceback

from api import direct_viewer_router, open_router, token_router
from api.dependencies.alloweds import owns_domain_id
from api.dependencies.rate_limiting import MIN_RESPONSE_TIME, direct_viewer_limiter
from api.schemas.common import (
    DesktopNotBookedErrorResponse,
    ErrorResponse,
    SimpleResponse,
)

log = logging.getLogger(__name__)


async def _timed_not_found(start_time):
    """Return 404 after enforcing minimum response time with jitter."""
    elapsed = time.time() - start_time
    target = MIN_RESPONSE_TIME + random.uniform(-0.5, 0.5)
    remaining = target - elapsed
    if remaining > 0:
        await asyncio.sleep(remaining)
    return JSONResponse(
        content={"error": "not_found", "msg": "Not found"}, status_code=404
    )


from api.schemas.domains.desktop_direct_viewer import (
    DesktopShareLinkResponse,
    DesktopUpdateShareLinkRequest,
    DesktopViewerResponse,
    ViewersDocsResponse,
)
from api.schemas.domains.desktops import DesktopDetailsResponse, DesktopNetworksResponse
from api.services.desktops import DesktopService
from api.services.error import Error
from cachetools import cached
from fastapi import Depends, Path, Request
from fastapi.responses import JSONResponse
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache

tag = "desktop_direct_viewer"

# Named caches so the share-link writer (update_share_link below) can
# invalidate the read cache, and the reset-desktop writer can drop the
# rate-limit cache. The viewer-docs cache holds a global config blob.
share_link_cache: SynchronizedTTLCache = SynchronizedTTLCache(maxsize=20, ttl=10)
viewer_docs_cache: SynchronizedTTLCache = SynchronizedTTLCache(maxsize=1, ttl=360)
reset_desktop_cache: SynchronizedTTLCache = SynchronizedTTLCache(maxsize=20, ttl=10)


def clear_share_link_cache() -> None:
    """Invalidate the share-link read cache after toggling sharing."""
    share_link_cache.clear()


def clear_viewer_docs_cache() -> None:
    """Invalidate the viewer-docs cache after admin updates the URL."""
    viewer_docs_cache.clear()


@cached(cache=share_link_cache)
@token_router.get(
    "/item/desktop/{desktop_id}/get-share-link",
    response_model=DesktopShareLinkResponse,
    tags=[tag],
    summary="Get an url to share a desktop",
    description="Returns a link to share an IsardVDI desktop based on an ID.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_domain_id("desktop_id"))],
)
async def get_share_link(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        link = await asyncio.to_thread(
            DesktopService.get_desktop_share_link, desktop_id
        )
        return JSONResponse(
            content=DesktopShareLinkResponse(link=link).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve desktop",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/desktop/{desktop_id}/update-share-link",
    response_model=DesktopShareLinkResponse,
    tags=[tag],
    summary="Generate an link to share a desktop",
    description="Generates a link to share an IsardVDI desktop based on an ID",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_domain_id("desktop_id"))],
)
async def update_share_link(
    request: Request,
    data: DesktopUpdateShareLinkRequest,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        link = await asyncio.to_thread(
            DesktopService.update_desktop_share_link, desktop_id, data.enabled
        )
        return JSONResponse(
            content=DesktopShareLinkResponse(link=link).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve desktop",
            traceback.format_exc(),
        )


@open_router.get(
    "/item/desktop/token/{token}/get-viewer",
    tags=[tag],
    response_model=DesktopViewerResponse,
    operation_id="get_desktop_viewer_by_token",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        428: {"model": DesktopNotBookedErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_desktop_viewer(
    request: Request,
    token: str = Path(
        ...,
        description="Code provided for the desktop viewer. Mainly defined when generating the share link.",
    ),
):
    start_time = time.time()
    # Rate limit: return identical 404 when exceeded (invisible to attacker)
    if direct_viewer_limiter.is_limited(request):
        log.warning(f"Direct viewer rate limit exceeded for token request")
        return await _timed_not_found(start_time)
    try:
        desktop = await asyncio.to_thread(
            DesktopService.get_desktop_direct_viewer_from_token, token, request
        )
        return JSONResponse(
            content=DesktopViewerResponse(**desktop).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        # All failures return generic 404 with timing normalization
        log.warning("Direct viewer token handler failed", exc_info=True)
        return await _timed_not_found(start_time)


@cached(cache=viewer_docs_cache)
@open_router.get(
    "/item/desktop/get-viewers-docs",
    tags=[tag],
    response_model=ViewersDocsResponse,
    summary="Get viewer documentation URL",
    description="Returns the URL for the viewer documentation",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_viewer_docs(request: Request):
    try:
        docs_link = await asyncio.to_thread(DesktopService.get_direct_viewer_docs)
        return JSONResponse(
            content=ViewersDocsResponse(viewers_documentation_url=docs_link).model_dump(
                mode="json"
            ),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve viewer documentation",
            traceback.format_exc(),
        )


_VIEWER_PROTOCOLS = {
    "file-spice",
    "browser-vnc",
    "browser-rdp",
    "file-rdpgw",
}


@open_router.post(
    "/item/desktop/token/{token}/viewer/{protocol}",
    tags=[tag],
    response_model=SimpleResponse,
    responses={
        404: {"model": ErrorResponse},
        428: {"model": DesktopNotBookedErrorResponse},
    },
)
async def log_viewer_click(
    request: Request,
    token: str = Path(..., description="Direct viewer share token"),
    protocol: str = Path(..., description="Viewer protocol used"),
):
    """Log a direct viewer click event with the protocol used."""
    start_time = time.time()
    if direct_viewer_limiter.is_limited(request):
        return await _timed_not_found(start_time)
    if protocol not in _VIEWER_PROTOCOLS:
        return await _timed_not_found(start_time)
    try:
        desktop = await asyncio.to_thread(
            DesktopService.get_desktop_direct_viewer_from_token, token, request
        )
        from isardvdi_common.helpers.logging import Logging

        Logging.logs_domain_event_directviewer(
            desktop["id"],
            action_user=None,
            viewer_type=protocol,
            user_request=request,
        )
        return JSONResponse(
            content=SimpleResponse(id=desktop["id"]).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        log.warning("Direct viewer click logging failed", exc_info=True)
        return await _timed_not_found(start_time)


@direct_viewer_router.get(
    "/item/desktop/token/{token}/get-networks",
    tags=[tag],
    response_model=DesktopNetworksResponse,
    operation_id="get_networks_from_token",
    summary="Get networks of a desktop from a direct viewer token",
    description=(
        "Returns the networks information about an IsardVDI desktop "
        "identified by a direct viewer share token. Requires a direct "
        "viewer JWT as Authorization bearer."
    ),
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_desktop_networks_from_token(
    request: Request,
    token: str = Path(
        ...,
        description="Code provided for the desktop viewer. Mainly defined when generating the share link.",
    ),
):
    start_time = time.time()
    if direct_viewer_limiter.is_limited(request):
        log.warning("Direct viewer rate limit exceeded for networks request")
        return await _timed_not_found(start_time)
    try:
        networks = DesktopService.get_desktop_networks_from_token(token)
        return JSONResponse(
            content=DesktopNetworksResponse(networks=networks).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        log.warning("Direct viewer networks token lookup failed")
        return await _timed_not_found(start_time)


@direct_viewer_router.get(
    "/item/desktop/token/{token}/get-details",
    tags=[tag],
    response_model=DesktopDetailsResponse,
    operation_id="get_desktop_details_from_token",
    summary="Get the details of a desktop from a direct viewer token",
    description=(
        "Returns the details of an IsardVDI desktop identified by a "
        "direct viewer share token. Requires a direct viewer JWT as "
        "Authorization bearer."
    ),
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_desktop_details_from_token(
    request: Request,
    token: str = Path(
        ...,
        description="Code provided for the desktop viewer.",
    ),
):
    start_time = time.time()
    if direct_viewer_limiter.is_limited(request):
        log.warning("Direct viewer rate limit exceeded for details request")
        return await _timed_not_found(start_time)
    try:
        details = await asyncio.to_thread(
            DesktopService.get_desktop_details_from_token, token
        )
        return JSONResponse(
            content=DesktopDetailsResponse(**details).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        log.warning("Direct viewer details token lookup failed", exc_info=True)
        return await _timed_not_found(start_time)


@direct_viewer_router.put(
    "/item/desktop/token/{token}/start-desktop",
    tags=[tag],
    response_model=SimpleResponse,
    operation_id="start_desktop_from_token",
    summary="Start a desktop from a direct viewer token",
    description=(
        "Starts an IsardVDI desktop identified by a direct viewer share "
        "token. Requires a direct viewer JWT as Authorization bearer. "
        "No-op if the desktop is not in a stopped/failed state."
    ),
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def start_desktop(
    request: Request,
    token: str = Path(
        ...,
        description="Code provided for the desktop viewer. Mainly defined when generating the share link.",
    ),
):
    start_time = time.time()
    if direct_viewer_limiter.is_limited(request):
        log.warning("Direct viewer rate limit exceeded for start request")
        return await _timed_not_found(start_time)
    try:
        desktop_id = DesktopService.start_desktop_from_token(token, request)
        return JSONResponse(
            content=SimpleResponse(id=desktop_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        log.warning("Direct viewer start token lookup failed")
        return await _timed_not_found(start_time)


@cached(cache=reset_desktop_cache)
@direct_viewer_router.put(
    "/item/desktop/token/{token}/reset-desktop",
    tags=[tag],
    response_model=SimpleResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def reset_desktop(
    request: Request,
    token: str = Path(
        ...,
        description="Code provided for the desktop viewer. Mainly defined when generating the share link.",
    ),
):
    start_time = time.time()
    if direct_viewer_limiter.is_limited(request):
        log.warning("Direct viewer rate limit exceeded for reset request")
        return await _timed_not_found(start_time)
    try:
        desktop_id = await asyncio.to_thread(
            DesktopService.reset_desktop_from_token, token, request
        )
        return JSONResponse(
            content=SimpleResponse(id=desktop_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        log.warning("Direct viewer reset token handler failed", exc_info=True)
        return await _timed_not_found(start_time)
