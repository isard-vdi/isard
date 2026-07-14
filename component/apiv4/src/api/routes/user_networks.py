#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import traceback

from api import token_router
from api.schemas.common import ErrorResponse, SimpleResponse
from api.schemas.user_networks import (
    CreateUserNetworkRequest,
    UpdateUserNetworkRequest,
    UserNetworkResponse,
)
from api.services.error import Error
from api.services.user_networks import UserNetworkService
from fastapi import Request
from fastapi.responses import JSONResponse, Response

tag = "user_networks"


# =============================================================================
# USER NETWORK ENDPOINTS (token_router)
# =============================================================================


@token_router.get(
    "/item/user/networks",
    tags=[tag],
    response_model=list[UserNetworkResponse],
    summary="List user networks",
    description="Returns all networks accessible to the current user.",
    responses={500: {"model": ErrorResponse}},
)
async def list_user_networks(request: Request):
    try:
        networks = await asyncio.to_thread(
            UserNetworkService.get_user_networks, request.token_payload
        )
        return JSONResponse(
            content=[
                UserNetworkResponse(**n).model_dump(mode="json")
                for n in (networks or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list user networks",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user/networks/{network_id}",
    tags=[tag],
    response_model=UserNetworkResponse,
    summary="Get a user network",
    description="Returns a specific user network by ID.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_user_network(request: Request, network_id: str):
    try:
        network = await asyncio.to_thread(
            UserNetworkService.get_user_network, network_id, request.token_payload
        )
        return JSONResponse(
            content=UserNetworkResponse(**(network or {})).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get user network",
            traceback.format_exc(),
        )


@token_router.post(
    "/item/user/networks",
    tags=[tag],
    response_model=UserNetworkResponse,
    summary="Create a user network",
    description="Creates a new user network with the given parameters.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_user_network(request: Request, data: CreateUserNetworkRequest):
    try:
        network = await asyncio.to_thread(
            UserNetworkService.create_user_network, data, request.token_payload
        )
        return JSONResponse(
            content=UserNetworkResponse(**(network or {})).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create user network",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/user/networks/{network_id}",
    tags=[tag],
    response_model=UserNetworkResponse,
    summary="Update a user network",
    description="Updates an existing user network. Only the owner, manager, or admin can update.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_user_network(
    request: Request, network_id: str, data: UpdateUserNetworkRequest
):
    try:
        network = await asyncio.to_thread(
            UserNetworkService.update_user_network,
            network_id,
            data,
            request.token_payload,
        )
        return JSONResponse(
            content=UserNetworkResponse(**(network or {})).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update user network",
            traceback.format_exc(),
        )


@token_router.delete(
    "/item/user/networks/{network_id}",
    tags=[tag],
    status_code=204,
    response_class=Response,
    summary="Delete a user network",
    description="Deletes a user network. Only the owner, manager, or admin can delete.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_user_network(request: Request, network_id: str):
    try:
        await asyncio.to_thread(
            UserNetworkService.delete_user_network, network_id, request.token_payload
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete user network",
            traceback.format_exc(),
        )
