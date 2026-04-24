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

from api import admin_router, disclaimer_router, manager_router, token_router
from api.schemas.admin_authentication import (
    MigrationExceptionCreateRequest,
    PolicyCreateRequest,
    PolicyEditRequest,
    ProviderConfigUpdateRequest,
)
from api.schemas.common import EmptyResponse, ErrorResponse
from api.services.admin_authentication import AdminAuthenticationService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse

tag = "admin-authentication"


# ══════════════════════════════════════════════════════════════════════════
#  Policies
# ══════════════════════════════════════════════════════════════════════════


@admin_router.post(
    "/admin/authentication/policy",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Create authentication policy",
    description="Creates a new authentication policy.",
    responses={
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_authentication_policy_add(request: Request, data: PolicyCreateRequest):
    try:
        AdminAuthenticationService.add_policy(data.model_dump(exclude_none=True))
        return JSONResponse(content={}, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create authentication policy",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/authentication/policies",
    tags=[tag],
    summary="List authentication policies",
    description="Returns all authentication policies.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_authentication_policies(request: Request):
    try:
        policies = AdminAuthenticationService.get_policies()
        return JSONResponse(content=policies, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list authentication policies",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/authentication/policy/{policy_id}",
    tags=[tag],
    summary="Get authentication policy",
    description="Returns an authentication policy by its ID.",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def admin_authentication_policy(request: Request, policy_id: str):
    try:
        policy = AdminAuthenticationService.get_policy(policy_id)
        return JSONResponse(content=policy, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get authentication policy",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/authentication/policy/{policy_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update authentication policy",
    description="Updates an authentication policy by its ID.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_authentication_policy_edit(
    request: Request, policy_id: str, data: PolicyEditRequest
):
    try:
        AdminAuthenticationService.edit_policy(
            policy_id, data.model_dump(exclude_none=True)
        )
        return JSONResponse(content={}, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update authentication policy",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/authentication/policy/{policy_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete authentication policy",
    description="Deletes an authentication policy by its ID.",
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_authentication_policy_delete(request: Request, policy_id: str):
    try:
        AdminAuthenticationService.delete_policy(policy_id)
        return JSONResponse(content={}, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete authentication policy",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Providers
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/authentication/providers",
    tags=[tag],
    summary="List authentication providers",
    description="Returns enabled status for all authentication providers.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_authentication_providers(request: Request):
    try:
        providers = AdminAuthenticationService.get_providers()
        return JSONResponse(content=providers, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list authentication providers",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Force Validate at Login
# ══════════════════════════════════════════════════════════════════════════


@admin_router.put(
    "/admin/authentication/force_validate/email/{policy_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Force email validation at login",
    description="Forces email validation at login for users matching the policy.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_force_email(request: Request, policy_id: str):
    try:
        AdminAuthenticationService.force_policy_at_login(policy_id, "email_verified")
        return JSONResponse(content={}, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to force email validation",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/authentication/force_validate/disclaimer/{policy_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Force disclaimer acknowledgement at login",
    description="Forces disclaimer acknowledgement at login for users matching the policy.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_force_disclaimer(request: Request, policy_id: str):
    try:
        AdminAuthenticationService.force_policy_at_login(
            policy_id, "disclaimer_acknowledged"
        )
        return JSONResponse(content={}, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to force disclaimer acknowledgement",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/authentication/force_validate/password/{policy_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Force password update at login",
    description="Forces password update at login for users matching the policy.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_force_password(request: Request, policy_id: str):
    try:
        AdminAuthenticationService.force_policy_at_login(
            policy_id, "password_last_updated"
        )
        return JSONResponse(content={}, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to force password update",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Disclaimer
# ══════════════════════════════════════════════════════════════════════════


@disclaimer_router.get(
    "/disclaimer",
    tags=[tag],
    summary="Get disclaimer template",
    description="Returns the disclaimer template for the current user.",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_disclaimer(request: Request):
    try:
        text = AdminAuthenticationService.get_disclaimer_template(
            request.token_payload["user_id"]
        )
        return JSONResponse(content=text, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get disclaimer template",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Provider Config (export/import status)
# ══════════════════════════════════════════════════════════════════════════


@token_router.get(
    "/authentication/export/{provider_id}",
    tags=[tag],
    summary="Get export enabled status for provider",
    description="Returns whether export is enabled for a specific provider.",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def export_provider_enabled(request: Request, provider_id: str):
    try:
        enabled = (
            AdminAuthenticationService.get_provider_config(provider_id)
            .get("migration", {})
            .get("export", False)
        )
        return JSONResponse(content={"enabled": enabled}, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get export status",
            traceback.format_exc(),
        )


@token_router.get(
    "/authentication/import/{provider_id}",
    tags=[tag],
    summary="Get import enabled status for provider",
    description="Returns whether import is enabled for a specific provider.",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def import_provider_enabled(request: Request, provider_id: str):
    try:
        enabled = (
            AdminAuthenticationService.get_provider_config(provider_id)
            .get("migration", {})
            .get("import", False)
        )
        return JSONResponse(content={"enabled": enabled}, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get import status",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Provider Config (admin)
# ══════════════════════════════════════════════════════════════════════════


@admin_router.get(
    "/authentication/provider/{provider}",
    tags=[tag],
    summary="Get provider configuration",
    description="Returns the configuration for a specific authentication provider.",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_provider_config_route(request: Request, provider: str):
    try:
        config = AdminAuthenticationService.get_provider_config(provider)
        return JSONResponse(content=config, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get provider configuration",
            traceback.format_exc(),
        )


@admin_router.put(
    "/authentication/provider/{provider}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update provider configuration",
    description="Updates the configuration for a specific authentication provider.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def edit_provider_config_route(
    request: Request, provider: str, data: ProviderConfigUpdateRequest
):
    try:
        AdminAuthenticationService.update_provider_config(
            provider, data.model_dump(exclude_none=True)
        )
        return JSONResponse(content={}, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update provider configuration",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Migration Exceptions
# ══════════════════════════════════════════════════════════════════════════


@admin_router.get(
    "/authentication/migrations/exceptions",
    tags=[tag],
    summary="List migration exceptions",
    description="Returns all migration exceptions.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_get_migration_exceptions(request: Request):
    try:
        exceptions = AdminAuthenticationService.get_migrations_exceptions()
        # Convert RethinkDB datetime objects to ISO strings for JSON serialization
        import json
        from datetime import datetime

        def _serialize(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        serialized = json.loads(json.dumps(exceptions, default=_serialize))
        return JSONResponse(content=serialized, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list migration exceptions",
            traceback.format_exc(),
        )


@admin_router.post(
    "/authentication/migrations/exceptions",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Add migration exception",
    description="Adds a migration exception for specific items.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_add_migration_exception(
    request: Request, data: MigrationExceptionCreateRequest
):
    try:
        AdminAuthenticationService.add_migration_exception(data.model_dump())
        return JSONResponse(content={}, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to add migration exception",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/authentication/migrations/exceptions/{exception_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete migration exception",
    description="Deletes a migration exception by its ID.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_delete_migration_exception(request: Request, exception_id: str):
    try:
        AdminAuthenticationService.delete_migration_exception(exception_id)
        return JSONResponse(content={}, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete migration exception",
            traceback.format_exc(),
        )
