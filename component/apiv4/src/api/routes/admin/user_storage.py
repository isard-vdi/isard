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

from api import admin_router
from api.schemas.admin_user_storage import (
    UserStorageAddRequest,
    UserStorageAutoRegisterRequest,
    UserStorageConnTestRequest,
)
from api.schemas.common import EmptyResponse, ErrorResponse
from api.services.admin_user_storage import AdminUserStorageService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse

tag = "admin-user-storage"


# ══════════════════════════════════════════════════════════════════════════
#  Auto Register
# ══════════════════════════════════════════════════════════════════════════


@admin_router.post(
    "/admin/user_storage/auto_register",
    tags=[tag],
    summary="Auto-register user storage provider",
    description="Auto-registers a user storage provider with the given credentials.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_user_storage_auto_register(
    request: Request, data: UserStorageAutoRegisterRequest
):
    try:
        result = AdminUserStorageService.auto_register(
            data.domain, data.user, data.password, data.intra_docker, data.verify_cert
        )
        return {"id": result}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to auto-register user storage provider",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Connection Test
# ══════════════════════════════════════════════════════════════════════════


@admin_router.post(
    "/admin/user_storage/conn_test",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Test user storage connection",
    description="Tests the connection to a user storage provider.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_user_storage_test(request: Request, data: UserStorageConnTestRequest):
    try:
        AdminUserStorageService.conn_test(
            data.provider,
            data.url,
            data.urlprefix,
            data.user,
            data.password,
            data.verify_cert,
        )
        return {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to test user storage connection",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Login Auth
# ══════════════════════════════════════════════════════════════════════════


@admin_router.get(
    "/admin/user_storage/{provider_id}/login_auth",
    tags=[tag],
    summary="Get user storage login auth URL",
    description="Returns the login authentication URL for a user storage provider.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_user_storage_login_auth(request: Request, provider_id: str):
    try:
        login_url = AdminUserStorageService.get_login_auth(provider_id)
        return {"login_url": login_url}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get user storage login auth URL",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  List / Get / Delete Providers
# ══════════════════════════════════════════════════════════════════════════


@admin_router.get(
    "/admin/user_storage",
    tags=[tag],
    summary="List user storage providers",
    description="Returns all user storage providers.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_user_storage_list(request: Request):
    try:
        providers = AdminUserStorageService.list_providers()
        return providers
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list user storage providers",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/user_storage/users",
    tags=[tag],
    summary="List user storage users",
    description="Returns all users with user storage configured.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_user_storage_users(request: Request):
    try:
        users = AdminUserStorageService.get_users()
        return users
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list user storage users",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/user_storage/{provider_id}",
    tags=[tag],
    summary="Get user storage provider",
    description="Returns a specific user storage provider by ID.",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def admin_user_storage_get(request: Request, provider_id: str):
    try:
        provider = AdminUserStorageService.get_provider(provider_id)
        return provider
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get user storage provider",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/user_storage/{provider_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete user storage provider",
    description="Deletes a user storage provider by ID.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_user_storage_remove(request: Request, provider_id: str):
    try:
        AdminUserStorageService.delete_provider(provider_id)
        return {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete user storage provider",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Reset
# ══════════════════════════════════════════════════════════════════════════


@admin_router.delete(
    "/admin/user_storage/{provider_id}/reset",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Reset user storage provider",
    description="Resets a user storage provider by ID.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_user_storage_reset(request: Request, provider_id: str):
    try:
        AdminUserStorageService.reset_provider(provider_id)
        return {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to reset user storage provider",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/user_storage/reset/all",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Reset all user storage providers",
    description="Resets all user storage providers.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_user_storage_reset_all(request: Request):
    try:
        AdminUserStorageService.reset_all()
        return {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to reset all user storage providers",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Add Provider
# ══════════════════════════════════════════════════════════════════════════


@admin_router.post(
    "/admin/user_storage/new/{auth_protocol}",
    tags=[tag],
    summary="Add user storage provider",
    description="Adds a user storage provider using the specified auth protocol "
    "(auth_basic or auth_oauth2).",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_user_storage_add(
    request: Request, auth_protocol: str, data: UserStorageAddRequest
):
    try:
        if auth_protocol == "auth_basic":
            result = AdminUserStorageService.add_provider_basic_auth(
                data.provider,
                data.name,
                data.description,
                data.url,
                data.urlprefix,
                data.access,
                data.quota,
                data.verify_cert,
            )
            return {"id": result}
        raise Error(
            "bad_request",
            f"Auth protocol '{auth_protocol}' is not supported",
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to add user storage provider",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Sync
# ══════════════════════════════════════════════════════════════════════════


@admin_router.put(
    "/admin/user_storage/{provider_id}/sync/{item}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Sync user storage provider",
    description="Syncs groups, users, or all for a user storage provider.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_user_storage_sync(request: Request, provider_id: str, item: str):
    try:
        AdminUserStorageService.sync(provider_id, item)
        return {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to sync user storage provider",
            traceback.format_exc(),
        )
