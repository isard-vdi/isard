#
#   Copyright © 2025 IsardVDI
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

import traceback
from typing import Optional

from api import admin_router
from api.schemas.admin_resources import QosDiskCreateRequest, QosDiskUpdateRequest
from api.schemas.common import EmptyResponse, ErrorResponse
from api.services.admin_resources import AdminResourcesService
from api.services.error import Error
from fastapi import Path, Request
from fastapi.responses import JSONResponse

tag = "admin_resources"


# =============================================================================
# REMOTE VPN
# =============================================================================


@admin_router.get(
    "/remote_vpn/{vpn_id}/{kind}/{os}",
    tags=[tag],
    summary="Get remote VPN data with OS",
    description="Get remote VPN configuration or installation data for a specific OS.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_remote_vpn_with_os(
    request: Request,
    vpn_id: str = Path(..., description="VPN ID"),
    kind: str = Path(..., description="VPN data kind: config or install"),
    os: str = Path(..., description="Operating system"),
):
    try:
        result = AdminResourcesService.get_remote_vpn(vpn_id, kind, os)
        return JSONResponse(content=result, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get remote VPN data",
            traceback.format_exc(),
        )


@admin_router.get(
    "/remote_vpn/{vpn_id}/{kind}",
    tags=[tag],
    summary="Get remote VPN data",
    description="Get remote VPN configuration data.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_remote_vpn(
    request: Request,
    vpn_id: str = Path(..., description="VPN ID"),
    kind: str = Path(..., description="VPN data kind: config or install"),
):
    try:
        result = AdminResourcesService.get_remote_vpn(vpn_id, kind)
        return JSONResponse(content=result, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get remote VPN data",
            traceback.format_exc(),
        )


# =============================================================================
# QOS DISK
# =============================================================================


@admin_router.post(
    "/qos_disk",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Add QoS disk profile",
    description="Add a new QoS disk profile with IO tune parameters.",
    responses={
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_qos_disk_add(
    request: Request,
    data: QosDiskCreateRequest,
):
    try:
        AdminResourcesService.add_qos_disk(data.model_dump(exclude_none=True))
        return JSONResponse(
            content=EmptyResponse().model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to add QoS disk profile",
            traceback.format_exc(),
        )


@admin_router.put(
    "/qos_disk",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update QoS disk profile",
    description="Update an existing QoS disk profile.",
    responses={
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_qos_disk_update(
    request: Request,
    data: QosDiskUpdateRequest,
):
    try:
        AdminResourcesService.update_qos_disk(data.model_dump(exclude_none=True))
        return JSONResponse(
            content=EmptyResponse().model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update QoS disk profile",
            traceback.format_exc(),
        )
