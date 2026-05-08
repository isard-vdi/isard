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
import traceback

from api import admin_router, migration_router, token_router
from api.schemas.common import EmptyResponse, ErrorResponse, SimpleResponse
from api.schemas.migrations import (
    AdminMigrationsResponse,
    ImportUserRequest,
    MigrationConfigResponse,
    MigrationConfigUpdateRequest,
    MigrationExportResponse,
    MigrationListItemsResponse,
    MigrationProviderEnabledResponse,
)
from api.services.config import ConfigService
from api.services.error import Error
from api.services.migrations import MigrationService
from fastapi import Request
from fastapi.responses import JSONResponse, Response

tag = "user_migration"


@migration_router.put(
    "/item/user-migration/export-user",
    tags=[tag],
    response_model=MigrationExportResponse,
    summary="Generate a JWT token to export user data for migration purposes.",
    description="Generates a JWT token that contains the user's data for migration to another IsardVDI user.",
    responses={403: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def migration_export_user(request: Request):
    try:
        return JSONResponse(
            content=MigrationExportResponse(
                token=await asyncio.to_thread(
                    MigrationService.export_user, request.token_payload["user_id"]
                )
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to generate export token for user migration",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/user-migration/import-user",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Import user data from a JWT token for migration purposes.",
    description="Imports user data from a JWT token generated for migration to another IsardVDI user.",
    responses={
        403: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def migration_import_user(request: Request, data: ImportUserRequest):
    try:
        await asyncio.to_thread(
            MigrationService.import_user, request.token_payload["user_id"], data.token
        )
        return JSONResponse(
            content=SimpleResponse(id=request.token_payload["user_id"]).model_dump(
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
            f"Failed to import user data for migration",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user-migration/list-items",
    tags=[tag],
    response_model=MigrationListItemsResponse,
    summary="List items available for user migration.",
    description="Lists the items available for migration for the authenticated user.",
    responses={
        403: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def migration_list_items(request: Request):
    try:
        result = await asyncio.to_thread(
            MigrationService.list_migration_items, request.token_payload["user_id"]
        )
        if result.get("errors"):
            return JSONResponse(
                content={"errors": result["errors"]},
                status_code=428,
            )
        return JSONResponse(
            content=MigrationListItemsResponse(**result["items"]).model_dump(
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
            f"Failed to list migration items",
            traceback.format_exc(),
        )


@token_router.post(
    "/item/user-migration/migrate-user",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Migrate user data from one user to another.",
    description="Migrates user data from the source user to the user calling the endpoint.",
    responses={
        403: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def migration_migrate_user(request: Request):
    try:
        result = await asyncio.to_thread(
            MigrationService.migrate_user, request.token_payload["user_id"]
        )
        if result:
            return JSONResponse(
                content={"errors": result["errors"]},
                status_code=428,
            )
        return JSONResponse(
            content=SimpleResponse(id=request.token_payload["user_id"]).model_dump(
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
            f"Failed to migrate user data",
            traceback.format_exc(),
        )


@migration_router.get(
    "/authentication/export/{provider_id}",
    tags=[tag],
    response_model=MigrationProviderEnabledResponse,
    summary="Check if provider allows exporting user migrations.",
    description="Returns whether the authentication provider allows users to export their data for migration.",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_provider_export_enabled(request: Request, provider_id: str):
    try:
        provider_config = await asyncio.to_thread(
            ConfigService.get_provider_config, provider_id
        )
        enabled = provider_config.get("migration", {}).get("export", False)
        return JSONResponse(
            content=MigrationProviderEnabledResponse(enabled=enabled).model_dump(
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
            f"Failed to get provider export configuration for '{provider_id}'",
            traceback.format_exc(),
        )


@migration_router.get(
    "/authentication/import/{provider_id}",
    tags=[tag],
    response_model=MigrationProviderEnabledResponse,
    summary="Check if provider allows importing user migrations.",
    description="Returns whether the authentication provider allows users to import data from another user.",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_provider_import_enabled(request: Request, provider_id: str):
    try:
        provider_config = await asyncio.to_thread(
            ConfigService.get_provider_config, provider_id
        )
        enabled = provider_config.get("migration", {}).get("import", False)
        return JSONResponse(
            content=MigrationProviderEnabledResponse(enabled=enabled).model_dump(
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
            f"Failed to get provider import configuration for '{provider_id}'",
            traceback.format_exc(),
        )


# ── Admin migration management endpoints ─────────────────────────────────

admin_tag = "admin_migrations"


@admin_router.get(
    "/admin/config/user-migration",
    tags=[admin_tag],
    response_model=MigrationConfigResponse,
    summary="Get user migration configuration",
    description="Returns the user migration configuration settings.",
)
async def get_migration_config(request: Request):
    try:
        config = await asyncio.to_thread(MigrationService.get_admin_migration_config)
        return JSONResponse(
            content=MigrationConfigResponse(**config).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve migration configuration",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/config/user-migration",
    tags=[admin_tag],
    response_model=MigrationConfigResponse,
    summary="Update user migration configuration",
    description="Updates the user migration configuration settings.",
)
async def update_migration_config(request: Request, data: MigrationConfigUpdateRequest):
    try:
        result = await asyncio.to_thread(
            MigrationService.update_admin_migration_config,
            data.model_dump(exclude_none=True),
        )
        return JSONResponse(
            content=MigrationConfigResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update migration configuration",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/migrations",
    tags=[admin_tag],
    response_model=AdminMigrationsResponse,
    summary="List all user migrations",
    description="Returns the list of all user migration records.",
)
async def get_all_migrations(request: Request):
    try:
        migrations = await asyncio.to_thread(MigrationService.get_all_migrations)
        return JSONResponse(
            content=AdminMigrationsResponse(migrations=migrations).model_dump(
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
            "Failed to retrieve migrations list",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/migrations/{migration_id}/revoke",
    tags=[admin_tag],
    response_model=EmptyResponse,
    summary="Revoke a user migration",
    description="Changes the status of a user migration to revoked.",
)
async def revoke_migration(request: Request, migration_id: str):
    try:
        await asyncio.to_thread(MigrationService.revoke_migration, migration_id)
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to revoke migration",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/migrations/{migration_id}",
    tags=[admin_tag],
    response_model=EmptyResponse,
    summary="Delete a user migration",
    description="Permanently deletes a user migration record.",
)
async def delete_migration(request: Request, migration_id: str):
    try:
        await asyncio.to_thread(MigrationService.delete_migration, migration_id)
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete migration",
            traceback.format_exc(),
        )
