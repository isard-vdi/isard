#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import traceback
from typing import List, Literal, Optional

from api import admin_router
from api.schemas.common import EmptyResponse, ErrorResponse
from api.schemas.vpn import AdminVpnConnectionsDisconnectRequest, VpnConnectionRequest
from api.services.admin_vpn import AdminVpnService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse

tag = "vpn"


# =============================================================================
# VPN CONNECTION ENDPOINTS (admin_router)
# =============================================================================


@admin_router.post(
    "/admin/vpn_connection/{kind}/{client_ip}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Register VPN client connection",
    description="Registers a new VPN client connection (connected).",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def vpn_connection_connect(
    request: Request,
    kind: Literal["users", "hypers"],
    client_ip: str,
    data: VpnConnectionRequest,
):
    try:
        if AdminVpnService.active_client(
            kind, client_ip, data.remote_ip, data.remote_port, True
        ):
            return {}
        raise await Error.create(
            request,
            "not_found",
            f"No active VPN client {client_ip} of kind {kind}",
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to register vpn connection",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/vpn_connection/{kind}/{client_ip}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update VPN client connection (roamed)",
    description="Updates a VPN client connection after roaming.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def vpn_connection_roam(
    request: Request,
    kind: Literal["users", "hypers"],
    client_ip: str,
    data: VpnConnectionRequest,
):
    try:
        if AdminVpnService.active_client(
            kind, client_ip, data.remote_ip, data.remote_port, True
        ):
            return {}
        raise await Error.create(
            request,
            "not_found",
            f"No active VPN client {client_ip} of kind {kind}",
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update vpn connection",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/vpn_connection/{kind}/{client_ip}",
    tags=[tag],
    summary="Disconnect a VPN client",
    description="Disconnects a specific VPN client.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def vpn_connection_disconnect(
    request: Request, kind: Literal["users", "hypers"], client_ip: str
):
    try:
        result = AdminVpnService.active_client(kind, client_ip)
        return result
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to disconnect vpn client",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/vpn_connection/{kind}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Reset all VPN connections for a kind",
    description="Resets all VPN connections for the specified kind (all/users/hypers).",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def vpn_connection_reset(request: Request, kind: Literal["all"]):
    try:
        AdminVpnService.reset_connection_status(kind)
        return {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to reset vpn connections",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/vpn_connections",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Disconnect multiple VPN connections",
    description="Disconnects multiple VPN connections from a list.",
    responses={500: {"model": ErrorResponse}},
)
async def vpn_connections_disconnect(
    request: Request,
    data: AdminVpnConnectionsDisconnectRequest,
):
    try:
        AdminVpnService.reset_connections_list_status(data.root)
        return {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to disconnect vpn connections",
            traceback.format_exc(),
        )
