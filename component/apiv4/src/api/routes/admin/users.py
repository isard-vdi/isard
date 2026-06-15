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

import asyncio
import traceback
from typing import Literal, Optional

from api import admin_router, manager_router
from api.dependencies.alloweds import owns_category_id, owns_group_id, owns_user_id
from api.schemas.admin.users import (
    AdminAppliedQuotaResponse,
    AdminBastionDomainData,
    AdminBastionDomainResponse,
    AdminBroadcastData,
    AdminBulkUserCreateData,
    AdminCategoryCreateData,
    AdminCategoryDetailResponse,
    AdminCategoryFrontendItem,
    AdminCategoryItem,
    AdminCategoryNavItem,
    AdminCategoryUpdateData,
    AdminCategoryUserItem,
    AdminCheckGroupCategoryData,
    AdminCheckMigratedData,
    AdminCheckMigratedResponse,
    AdminCSVImportResponse,
    AdminCSVUserEditData,
    AdminCSVUserEditRow,
    AdminCSVUserImportData,
    AdminCSVValidateCreateResponse,
    AdminDeleteChecksData,
    AdminDeleteChecksResponse,
    AdminGroup,
    AdminGroupCreateData,
    AdminGroupEnrollmentData,
    AdminGroupEnrollmentResponse,
    AdminGroupFullDataResponse,
    AdminGroupListItem,
    AdminGroupNavItem,
    AdminGroupUpdateData,
    AdminGroupUserItem,
    AdminLimitsUpdateData,
    AdminMigrationErrorsResponse,
    AdminMigrationStartedResponse,
    AdminPasswordPolicyResponse,
    AdminPasswordResetData,
    AdminQuotasResponse,
    AdminQuotaUpdateData,
    AdminRoleItem,
    AdminRoleUpdateData,
    AdminSecondaryGroupsData,
    AdminSecretCreateData,
    AdminSecretCreateResponse,
    AdminSecretItem,
    AdminTemplateItem,
    AdminUser,
    AdminUserCreateData,
    AdminUserDeleteData,
    AdminUserDeleteResponse,
    AdminUserDesktopItem,
    AdminUserFullDataResponse,
    AdminUserIdResponse,
    AdminUserImpersonateJwtResponse,
    AdminUserNavItem,
    AdminUserSchemaResponse,
    AdminUserSearchData,
    AdminUserSearchItem,
    AdminUserTemplateItem,
    AdminUserUpdateData,
    AdminUserVpnFileResponse,
    AutoRegisterRequest,
    AutoRegisterResponse,
    RequiredCheckResponse,
)
from api.schemas.common import EmptyResponse, ErrorResponse, PasswordPolicyErrorResponse
from api.services.admin.socketio import AdminSocketioService
from api.services.admin.users import AdminUsersService
from api.services.error import Error
from cachetools import TTLCache, cached
from fastapi import BackgroundTasks, Depends, Header, Path, Query, Request
from fastapi.responses import JSONResponse, Response
from isardvdi_common.models.user import UserModel as UserDBModel
from pydantic import ValidationError

tag = "admin_users"

# Named cache so writers (admin user updates further down this module
# and in admin_users service) can invalidate the cached profile blob.
admin_user_full_data_cache: TTLCache = TTLCache(maxsize=100, ttl=60)


def clear_admin_user_full_data_cache():
    """Invalidate the per-user admin profile cache after a user mutation."""
    admin_user_full_data_cache.clear()


# ══════════════════════════════════════════════════════════════════════════
#  User CRUD & Management
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/item/jwt/{user_id}",
    tags=[tag],
    response_model=AdminUserImpersonateJwtResponse,
    summary="Get impersonation JWT for user",
    description="Generates a JWT token to impersonate the specified user. Requires ownership check.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_jwt(request: Request, user_id: str):
    try:
        await asyncio.to_thread(
            AdminUsersService.owns_user_id, request.token_payload, user_id
        )
        result = await asyncio.to_thread(
            AdminUsersService.get_impersonate_jwt, request.token_payload, user_id
        )
        return JSONResponse(
            content=AdminUserImpersonateJwtResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to generate JWT for user",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/item/user/{user_id}/exists",
    tags=[tag],
    response_model=bool,
    summary="Check if user exists",
    description="Returns whether a user with the given ID exists.",
    responses={
        200: {"description": "User existence check result"},
        500: {"model": ErrorResponse},
    },
)
async def admin_user_exists(request: Request, user_id: str):
    try:
        await asyncio.to_thread(
            AdminUsersService.owns_user_id, request.token_payload, user_id
        )
        return JSONResponse(
            content=bool(
                await asyncio.to_thread(AdminUsersService.user_exists, user_id)
            ),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to check user existence",
            traceback.format_exc(),
        )


@cached(cache=admin_user_full_data_cache)
@manager_router.get(
    "/admin/item/user/{user_id}",
    tags=[tag],
    response_model=AdminUserFullDataResponse,
    summary="Get user full data",
    description="Returns full data for a user.",
    responses={
        200: {"description": "User data retrieved"},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_user_id())],
)
async def admin_get_user(request: Request, user_id: str):
    try:
        result = await asyncio.to_thread(AdminUsersService.get_user_full_data, user_id)
        return JSONResponse(
            # exclude_none: the generated client's nested from_dict() treats
            # an explicit null as a dict and raises; an absent key is UNSET.
            content=AdminUserFullDataResponse(**result).model_dump(
                mode="json", exclude_none=True
            ),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user data",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/item/user/{user_id}/raw",
    tags=[tag],
    response_model=AdminUserFullDataResponse,
    summary="Get user raw data",
    description="Returns raw user data from database.",
    responses={
        200: {"description": "Raw user data retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user_raw(request: Request, user_id: str):
    try:
        await asyncio.to_thread(
            AdminUsersService.owns_user_id, request.token_payload, user_id
        )
        result = await asyncio.to_thread(AdminUsersService.get_user_raw, user_id)
        return JSONResponse(
            # exclude_none: the generated client's nested from_dict() treats
            # an explicit null as a dict and raises; an absent key is UNSET.
            content=AdminUserFullDataResponse(**(result or {})).model_dump(
                mode="json", exclude_none=True
            ),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve raw user data",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/items/users",
    tags=[tag],
    summary="List users",
    description="Returns list of users. Admins see all, managers see their category.",
    response_model=list[AdminUser],
    responses={
        200: {"description": "Users list retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_list_users(request: Request):
    try:
        category_id = (
            request.token_payload["category_id"]
            if request.token_payload["role_id"] == "manager"
            else None
        )
        result = await asyncio.to_thread(
            AdminUsersService.list_users, category_id=category_id
        )
        return JSONResponse(
            content=[AdminUser(**u).model_dump(mode="json") for u in result],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list users",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/items/users/{nav}/users",
    tags=[tag],
    response_model=list[AdminUserNavItem],
    summary="List users by navigation context",
    description="Returns list of users for management or quotas_limits navigation.",
    responses={
        200: {"description": "Users list retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_list_users_nav(
    request: Request, nav: Literal["management", "quotas_limits"]
):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.list_users_nav, request.token_payload, nav
        )
        return JSONResponse(
            content=[
                AdminUserNavItem(**u).model_dump(mode="json") for u in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list users",
            traceback.format_exc(),
        )


@manager_router.post(
    "/admin/item/user",
    tags=[tag],
    summary="Create user",
    description="Creates a new user.",
    response_model=AdminUser,
    responses={
        200: {"description": "User created"},
        400: {"model": PasswordPolicyErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_create_user(request: Request, data: AdminUserCreateData):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.create_user, request.token_payload, data.model_dump()
        )
        return JSONResponse(
            content=AdminUser(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create user",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/user/{user_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update user",
    description="Updates a single user.",
    responses={
        200: {"description": "User updated"},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_user_id())],
)
async def admin_update_user(request: Request, user_id: str, data: AdminUserUpdateData):
    try:
        await asyncio.to_thread(
            AdminUsersService.update_user,
            request.token_payload,
            user_id,
            data.model_dump(exclude_none=True),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update user",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/items/users/bulk",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Bulk update users",
    description="Updates multiple users at once.",
    responses={
        200: {"description": "Users updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_users_bulk(
    request: Request,
    data: AdminUserUpdateData,
    background_tasks: BackgroundTasks,
):
    try:
        await asyncio.to_thread(
            AdminUsersService.update_multiple_users,
            request.token_payload,
            data.model_dump(exclude_none=True),
            background_tasks,
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to bulk update users",
            traceback.format_exc(),
        )


@manager_router.delete(
    "/admin/items/users",
    tags=[tag],
    summary="Delete users",
    description="Deletes one or more users.",
    response_model=AdminUserDeleteResponse,
    responses={
        200: {"description": "Users deleted"},
        428: {"description": "Some users could not be deleted"},
        500: {"model": ErrorResponse},
    },
)
async def admin_delete_users(
    request: Request,
    data: AdminUserDeleteData,
    background_tasks: BackgroundTasks,
):
    try:
        result, status = await asyncio.to_thread(
            AdminUsersService.delete_users,
            request.token_payload,
            data.model_dump(),
            background_tasks,
        )
        return JSONResponse(
            content=AdminUserDeleteResponse(**result).model_dump(mode="json"),
            status_code=status,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete users",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/user/{user_id}/logout",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Force logout user",
    description="Revokes all sessions for a user.",
    responses={
        200: {"description": "User logged out"},
        500: {"model": ErrorResponse},
    },
)
async def admin_user_logout(request: Request, user_id: str):
    try:
        await asyncio.to_thread(
            AdminUsersService.force_logout_user, request.token_payload, user_id
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to logout user",
            traceback.format_exc(),
        )


@manager_router.post(
    "/admin/items/users/search",
    tags=[tag],
    response_model=list[AdminUserSearchItem],
    summary="Search users",
    description="Search users by name term.",
    responses={
        200: {"description": "Search results"},
        500: {"model": ErrorResponse},
    },
)
async def admin_search_users(request: Request, data: AdminUserSearchData):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.search_users, request.token_payload, data.term
        )
        return JSONResponse(
            content=[
                AdminUserSearchItem(**u).model_dump(mode="json") for u in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to search users",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  CSV Operations
# ══════════════════════════════════════════════════════════════════════════


@manager_router.post(
    "/admin/items/users/csv/validate",
    tags=[tag],
    response_model=AdminCSVValidateCreateResponse,
    summary="Validate CSV for user creation",
    description="Validates a list of users from CSV data.",
    responses={
        200: {"description": "Validation results"},
        400: {"model": PasswordPolicyErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_validate_csv_users(request: Request, user_list: list[dict]):
    # Body is a raw JSON array — webapp sends ``JSON.stringify(csv_data.users)``
    # at ``static/admin/js/users_management.js`` line 1635. Declaring it as
    # a typed parameter (instead of ``await request.json()``) makes the OAS
    # spec carry a request body, which the generated client needs to expose
    # the body argument to its caller.
    try:
        result = await asyncio.to_thread(
            AdminUsersService.validate_csv_users, request.token_payload, user_list
        )
        return JSONResponse(
            content=AdminCSVValidateCreateResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to validate CSV users",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/items/users/csv/validate",
    tags=[tag],
    response_model=list[AdminCSVUserEditRow],
    summary="Validate CSV for user editing",
    description="Validates a list of users from CSV for editing.",
    responses={
        200: {"description": "Validation results"},
        400: {"model": PasswordPolicyErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_validate_csv_users_edit(request: Request, user_list: list[dict]):
    # Same raw-array body as the POST sibling above.
    try:
        result = await asyncio.to_thread(
            AdminUsersService.validate_csv_users_edit, request.token_payload, user_list
        )
        return JSONResponse(
            content=[
                AdminCSVUserEditRow(**u).model_dump(mode="json") for u in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to validate CSV users for edit",
            traceback.format_exc(),
        )


@manager_router.post(
    "/admin/items/users/csv",
    tags=[tag],
    response_model=AdminCSVImportResponse,
    summary="Import users from CSV",
    description="Creates users from validated CSV data.",
    responses={
        200: {"description": "Import started"},
        500: {"model": ErrorResponse},
    },
)
async def admin_import_csv_users(request: Request, data: AdminCSVUserImportData):
    # Import body has no ``id`` per row (rows are NEW users). Edit
    # body's ``id``-required schema would 422 those, so this route uses
    # the looser ``AdminCSVUserImportData`` shape.
    try:
        result = await asyncio.to_thread(
            AdminUsersService.import_csv_users, request.token_payload, data.model_dump()
        )
        return JSONResponse(
            content=AdminCSVImportResponse(
                created=len(result.get("users", [])),
                errors=result.get("errors", []),
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to import CSV users",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/items/users/csv",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Edit users from CSV",
    description="Updates users from validated CSV data.",
    responses={
        200: {"description": "Users updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_edit_csv_users(request: Request, data: AdminCSVUserEditData):
    try:
        await asyncio.to_thread(
            AdminUsersService.edit_csv_users, request.token_payload, data.model_dump()
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to edit CSV users",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Bulk User Creation
# ══════════════════════════════════════════════════════════════════════════


@manager_router.post(
    "/admin/items/bulk/user",
    tags=[tag],
    response_model=AdminCSVImportResponse,
    summary="Bulk create users",
    description="Creates multiple users in bulk.",
    responses={
        200: {"description": "Bulk creation started"},
        500: {"model": ErrorResponse},
    },
)
async def admin_bulk_create_users(request: Request, data: AdminBulkUserCreateData):
    # Body declared as ``AdminBulkUserCreateData`` (``{users:[...],
    # email_verified: bool}``) so the OAS spec advertises a
    # ``requestBody`` and the generated isardvdi_apiv4_client / k6
    # client can carry it. The webapp sends this exact shape from
    # ``static/admin/js/users_management.js:745``.
    try:
        result = await asyncio.to_thread(
            AdminUsersService.import_csv_users, request.token_payload, data.model_dump()
        )
        return JSONResponse(
            content=AdminCSVImportResponse(
                created=len(result.get("users", [])),
                errors=result.get("errors", []),
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to bulk create users",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Secondary Groups
# ══════════════════════════════════════════════════════════════════════════


@manager_router.put(
    "/admin/item/user/secondary-groups/add",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Add secondary groups",
    description="Adds secondary groups to specified users.",
    responses={
        200: {"description": "Secondary groups added"},
        500: {"model": ErrorResponse},
    },
)
async def admin_secondary_groups_add(request: Request, data: AdminSecondaryGroupsData):
    try:
        await asyncio.to_thread(
            AdminUsersService.update_secondary_groups,
            request.token_payload,
            "add",
            data.model_dump(),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to add secondary groups",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/user/secondary-groups/overwrite",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Overwrite secondary groups",
    description="Overwrites secondary groups for specified users.",
    responses={
        200: {"description": "Secondary groups overwritten"},
        500: {"model": ErrorResponse},
    },
)
async def admin_secondary_groups_overwrite(
    request: Request, data: AdminSecondaryGroupsData
):
    try:
        await asyncio.to_thread(
            AdminUsersService.update_secondary_groups,
            request.token_payload,
            "overwrite",
            data.model_dump(),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to overwrite secondary groups",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/user/secondary-groups/delete",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Remove secondary groups",
    description="Removes secondary groups from specified users.",
    responses={
        200: {"description": "Secondary groups removed"},
        500: {"model": ErrorResponse},
    },
)
async def admin_secondary_groups_delete(
    request: Request, data: AdminSecondaryGroupsData
):
    try:
        await asyncio.to_thread(
            AdminUsersService.update_secondary_groups,
            request.token_payload,
            "delete",
            data.model_dump(),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to remove secondary groups",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Password & Security
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/item/user/password-policy/{user_id}",
    tags=[tag],
    response_model=AdminPasswordPolicyResponse,
    summary="Get user password policy",
    description="Returns the password policy for a user.",
    responses={
        200: {"description": "Password policy retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_password_policy(request: Request, user_id: str):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.get_password_policy, request.token_payload, user_id
        )
        # ``UserPolicies.get_user_policy`` returns ``False`` when no
        # policy applies — coerce to an empty model so the response
        # always serialises through the strict shape.
        policy = result if isinstance(result, dict) else {}
        return JSONResponse(
            content=AdminPasswordPolicyResponse(**policy).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve password policy",
            traceback.format_exc(),
        )


@admin_router.put(
    # NOTE: /admin/items/users/ (plural) so the path is not shadowed by the
    # /admin/item/user/{user_id} PUT catch-all on manager_router (defined above
    # in this file), which is registered earlier because manager_router is
    # included before admin_router in api/__init__.py.
    "/admin/items/users/reset-password",
    tags=[tag],
    summary="Reset user password",
    description="Admin resets a user's password.",
    response_model=EmptyResponse,
    responses={
        200: {"description": "Password reset"},
        400: {"model": PasswordPolicyErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_reset_password(request: Request, data: AdminPasswordResetData):
    try:
        await asyncio.to_thread(AdminUsersService.reset_password, data.model_dump())
        # Return the declared 200/EmptyResponse (not 204): the Go ogen
        # client treats an undeclared 204 as a decode error and reports
        # a successful reset as a failure.
        return EmptyResponse()
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to reset password",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/item/user/required/password-reset/{user_id}",
    tags=[tag],
    summary="Check password reset required",
    description="Check if a user needs to reset their password.",
    response_model=RequiredCheckResponse,
    responses={
        200: {"description": "Password reset check result"},
        500: {"model": ErrorResponse},
    },
)
async def admin_check_password_reset_required(request: Request, user_id: str):
    try:
        return JSONResponse(
            content=RequiredCheckResponse(
                required=await asyncio.to_thread(
                    AdminUsersService.check_password_expiration, user_id
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
            "Failed to check password reset requirement",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/item/user/required/email-verification/{user_id}",
    tags=[tag],
    summary="Check email verification required",
    description="Check if a user needs to verify their email.",
    response_model=RequiredCheckResponse,
    responses={
        200: {"description": "Email verification check result"},
        500: {"model": ErrorResponse},
    },
)
async def admin_check_email_verification(request: Request, user_id: str):
    try:
        return JSONResponse(
            content=RequiredCheckResponse(
                required=await asyncio.to_thread(
                    AdminUsersService.check_email_verified, user_id
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
            "Failed to check email verification",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/item/user/required/disclaimer-acknowledgement/{user_id}",
    tags=[tag],
    summary="Check disclaimer acknowledgement",
    description="Check if a user has acknowledged the disclaimer.",
    response_model=RequiredCheckResponse,
    responses={
        200: {"description": "Disclaimer acknowledgement check result"},
        500: {"model": ErrorResponse},
    },
)
async def admin_check_disclaimer(request: Request, user_id: str):
    try:
        return JSONResponse(
            content=RequiredCheckResponse(
                required=await asyncio.to_thread(
                    AdminUsersService.check_disclaimer_acknowledgement, user_id
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
            "Failed to check disclaimer acknowledgement",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/user/reset-vpn/{user_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Reset user VPN",
    description="Resets VPN credentials for a user.",
    responses={
        200: {"description": "VPN reset"},
        500: {"model": ErrorResponse},
    },
)
async def admin_reset_vpn(request: Request, user_id: str):
    try:
        await asyncio.to_thread(
            AdminUsersService.reset_vpn, request.token_payload, user_id
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to reset VPN",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Groups CRUD
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/items/groups",
    tags=[tag],
    response_model=list[AdminGroupListItem],
    summary="List groups",
    description="Returns all groups. Managers see only their category groups.",
    responses={
        200: {"description": "Groups list retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_list_groups(request: Request):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.list_groups, request.token_payload
        )
        return JSONResponse(
            content=[
                AdminGroupListItem(**g).model_dump(mode="json") for g in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list groups",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/items/users/{nav}/groups",
    tags=[tag],
    response_model=list[AdminGroupNavItem],
    summary="List groups by navigation context",
    description="Returns groups for management or quotas_limits navigation.",
    responses={
        200: {"description": "Groups list retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_list_groups_nav(
    request: Request, nav: Literal["management", "quotas_limits"]
):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.list_groups_nav, request.token_payload, nav
        )
        return JSONResponse(
            content=[
                AdminGroupNavItem(**g).model_dump(mode="json") for g in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list groups",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/item/group/{group_id}",
    tags=[tag],
    response_model=AdminGroupFullDataResponse,
    summary="Get group",
    description="Returns full data for a group.",
    responses={
        200: {"description": "Group data retrieved"},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_group_id())],
)
async def admin_get_group(request: Request, group_id: str):
    try:
        result = await asyncio.to_thread(AdminUsersService.get_group, group_id)
        return JSONResponse(
            content=AdminGroupFullDataResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve group",
            traceback.format_exc(),
        )


@manager_router.post(
    "/admin/item/group",
    tags=[tag],
    summary="Create group",
    description="Creates a new group.",
    response_model=AdminGroup,
    responses={
        200: {"description": "Group created"},
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_create_group(request: Request, data: AdminGroupCreateData):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.create_group, request.token_payload, data.model_dump()
        )
        return JSONResponse(
            content=AdminGroup(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create group",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/group/{group_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update group",
    description="Updates a group.",
    responses={
        200: {"description": "Group updated"},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_group_id())],
)
async def admin_update_group(
    request: Request, group_id: str, data: AdminGroupUpdateData
):
    try:
        await asyncio.to_thread(
            AdminUsersService.update_group,
            request.token_payload,
            group_id,
            data.model_dump(exclude_none=True),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update group",
            traceback.format_exc(),
        )


@manager_router.delete(
    "/admin/item/group/{group_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete group",
    description="Deletes a group.",
    responses={
        200: {"description": "Group deleted"},
        500: {"model": ErrorResponse},
    },
)
async def admin_delete_group(request: Request, group_id: str):
    try:
        await asyncio.to_thread(
            AdminUsersService.delete_group, request.token_payload, group_id
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete group",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/items/group/{group_id}/users",
    tags=[tag],
    response_model=list[AdminGroupUserItem],
    summary="Get users in group",
    description="Returns all users in a specific group.",
    responses={
        200: {"description": "Group users retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_group_users(request: Request, group_id: str):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.get_group_users, request.token_payload, group_id
        )
        return JSONResponse(
            content=[
                AdminGroupUserItem(**u).model_dump(mode="json") for u in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve group users",
            traceback.format_exc(),
        )


@manager_router.post(
    "/admin/item/group/enrollment",
    tags=[tag],
    response_model=AdminGroupEnrollmentResponse,
    summary="Update group enrollment",
    description="Updates enrollment settings for a group.",
    responses={
        200: {"description": "Enrollment updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_group_enrollment(request: Request, data: AdminGroupEnrollmentData):
    try:
        # enrollment_action returns the new 6-char code (reset) or True (disable).
        result = await asyncio.to_thread(
            AdminUsersService.update_group_enrollment,
            request.token_payload,
            data.model_dump(),
        )
        return JSONResponse(
            content=AdminGroupEnrollmentResponse(code=result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update group enrollment",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Categories CRUD
# ══════════════════════════════════════════════════════════════════════════


@admin_router.get(
    "/admin/items/categories",
    tags=[tag],
    response_model=list[AdminCategoryItem],
    summary="List categories",
    description="Returns all categories.",
    responses={
        200: {"description": "Categories list retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_list_categories(request: Request):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.list_categories, request.token_payload
        )
        return JSONResponse(
            content=[
                AdminCategoryItem(**c).model_dump(mode="json") for c in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list categories",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/items/categories/{frontend}",
    tags=[tag],
    response_model=list[AdminCategoryFrontendItem],
    summary="List frontend categories",
    description="Returns categories for frontend display.",
    responses={
        200: {"description": "Frontend categories list retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_list_categories_frontend(request: Request, frontend: str):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.list_categories, request.token_payload, frontend=True
        )
        return JSONResponse(
            content=[
                AdminCategoryFrontendItem(**c).model_dump(mode="json")
                for c in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list frontend categories",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/items/users/{nav}/categories",
    tags=[tag],
    response_model=list[AdminCategoryNavItem],
    summary="List categories by navigation context",
    description="Returns categories for management or quotas_limits navigation.",
    responses={
        200: {"description": "Categories list retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_list_categories_nav(
    request: Request, nav: Literal["management", "quotas_limits"]
):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.list_categories_nav, request.token_payload, nav
        )
        return JSONResponse(
            content=[
                AdminCategoryNavItem(**c).model_dump(mode="json")
                for c in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list categories",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/item/category/{category_id}",
    tags=[tag],
    response_model=AdminCategoryDetailResponse,
    summary="Get category",
    description="Returns data for a specific category.",
    responses={
        200: {"description": "Category data retrieved"},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_category_id())],
)
async def admin_get_category(request: Request, category_id: str):
    try:
        result = await asyncio.to_thread(AdminUsersService.get_category, category_id)
        return JSONResponse(
            content=AdminCategoryDetailResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve category",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/item/category",
    tags=[tag],
    response_model=AdminCategoryDetailResponse,
    summary="Create category",
    description="Creates a new category with an associated Main group.",
    responses={
        200: {"description": "Category created"},
        500: {"model": ErrorResponse},
    },
)
async def admin_create_category(request: Request, data: AdminCategoryCreateData):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.create_category, request.token_payload, data.model_dump()
        )
        return JSONResponse(
            content=AdminCategoryDetailResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create category",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/item/category/{category_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update category",
    description="Updates a category.",
    responses={
        200: {"description": "Category updated"},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_category_id())],
)
async def admin_update_category(
    request: Request, category_id: str, data: AdminCategoryUpdateData
):
    try:
        await asyncio.to_thread(
            AdminUsersService.update_category,
            request.token_payload,
            category_id,
            data.model_dump(exclude_unset=True),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update category",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/item/category/{category_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete category",
    description="Deletes a category.",
    responses={
        200: {"description": "Category deleted"},
        500: {"model": ErrorResponse},
    },
)
async def admin_delete_category(request: Request, category_id: str):
    try:
        # ``CategoriesProcessed.delete_category`` returns ``None`` —
        # surface a 204 to match the pattern used by every other
        # ``EmptyResponse`` route in this module.
        await asyncio.to_thread(
            AdminUsersService.delete_category, request.token_payload, category_id
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete category",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/items/category/{category_id}/users",
    tags=[tag],
    response_model=list[AdminCategoryUserItem],
    summary="Get users in category",
    description="Returns all users in a specific category.",
    responses={
        200: {"description": "Category users retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_category_users(request: Request, category_id: str):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.get_category_users, request.token_payload, category_id
        )
        return JSONResponse(
            content=[
                AdminCategoryUserItem(**u).model_dump(mode="json")
                for u in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve category users",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/item/category/get/{category_name}",
    tags=[tag],
    response_model=str,
    summary="Get category by name",
    description="Returns a category ID by its name.",
    responses={
        200: {"description": "Category ID retrieved"},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_category_by_name(request: Request, category_name: str):
    try:
        category_id = await asyncio.to_thread(
            AdminUsersService.get_category_by_name, category_name
        )
        return JSONResponse(content=category_id or "", status_code=200)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve category by name",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/item/group/get/{category_name}/{group_name}",
    tags=[tag],
    response_model=str,
    summary="Get group by category and name",
    description="Returns a group ID by category name and group name.",
    responses={
        200: {"description": "Group ID retrieved"},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_group_by_name_category(
    request: Request, category_name: str, group_name: str
):
    try:
        group_id = await asyncio.to_thread(
            AdminUsersService.get_group_by_name_category, category_name, group_name
        )
        return JSONResponse(content=group_id or "", status_code=200)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve group by name and category",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Quotas & Limits
# ══════════════════════════════════════════════════════════════════════════


@manager_router.put(
    "/admin/item/quota/group/{group_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update group quota",
    description="Updates quota for a group.",
    responses={
        200: {"description": "Group quota updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_group_quota(
    request: Request, group_id: str, data: AdminQuotaUpdateData
):
    try:
        await asyncio.to_thread(
            AdminUsersService.update_group_quota,
            request.token_payload,
            group_id,
            data.model_dump(exclude_none=True),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update group quota",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/item/quota/category/{category_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update category quota",
    description="Updates quota for a category.",
    responses={
        200: {"description": "Category quota updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_category_quota(
    request: Request, category_id: str, data: AdminQuotaUpdateData
):
    try:
        await asyncio.to_thread(
            AdminUsersService.update_category_quota,
            request.token_payload,
            category_id,
            data.model_dump(exclude_none=True),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update category quota",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/limits/group/{group_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update group limits",
    description="Updates limits for a group.",
    responses={
        200: {"description": "Group limits updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_group_limits(
    request: Request, group_id: str, data: AdminLimitsUpdateData
):
    try:
        await asyncio.to_thread(
            AdminUsersService.update_group_limits,
            request.token_payload,
            group_id,
            data.model_dump(exclude_none=True),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update group limits",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/item/limits/category/{category_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update category limits",
    description="Updates limits for a category.",
    responses={
        200: {"description": "Category limits updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_category_limits(
    request: Request, category_id: str, data: AdminLimitsUpdateData
):
    try:
        await asyncio.to_thread(
            AdminUsersService.update_category_limits,
            request.token_payload,
            category_id,
            data.model_dump(exclude_none=True),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update category limits",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Validation & Checks
# ══════════════════════════════════════════════════════════════════════════


@manager_router.post(
    "/admin/item/user/delete/check",
    tags=[tag],
    response_model=AdminDeleteChecksResponse,
    summary="Check user deletion dependencies",
    description="Checks dependencies before deleting users.",
    responses={
        200: {"description": "Deletion check results"},
        500: {"model": ErrorResponse},
    },
)
async def admin_user_delete_check(request: Request, data: AdminDeleteChecksData):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.user_delete_checks, request.token_payload, data.ids
        )
        payload = result if isinstance(result, dict) else {}
        return JSONResponse(
            content=AdminDeleteChecksResponse(**payload).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to check user deletion dependencies",
            traceback.format_exc(),
        )


@manager_router.post(
    "/admin/item/group/delete/check",
    tags=[tag],
    response_model=AdminDeleteChecksResponse,
    summary="Check group deletion dependencies",
    description="Checks dependencies before deleting groups.",
    responses={
        200: {"description": "Deletion check results"},
        500: {"model": ErrorResponse},
    },
)
async def admin_group_delete_check(request: Request, data: AdminDeleteChecksData):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.group_delete_checks, request.token_payload, data.ids
        )
        payload = result if isinstance(result, dict) else {}
        return JSONResponse(
            content=AdminDeleteChecksResponse(**payload).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to check group deletion dependencies",
            traceback.format_exc(),
        )


@manager_router.post(
    "/admin/item/category/delete/check",
    tags=[tag],
    response_model=AdminDeleteChecksResponse,
    summary="Check category deletion dependencies",
    description="Checks dependencies before deleting categories.",
    responses={
        200: {"description": "Deletion check results"},
        500: {"model": ErrorResponse},
    },
)
async def admin_category_delete_check(request: Request, data: AdminDeleteChecksData):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.category_delete_checks, request.token_payload, data.ids
        )
        payload = result if isinstance(result, dict) else {}
        return JSONResponse(
            content=AdminDeleteChecksResponse(**payload).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to check category deletion dependencies",
            traceback.format_exc(),
        )


@manager_router.post(
    "/admin/item/check/group/category",
    tags=[tag],
    response_model=list[dict],
    summary="Check group/category association",
    description="Validates a group/category association.",
    responses={
        200: {"description": "Check results"},
        500: {"model": ErrorResponse},
    },
)
async def admin_check_group_category(
    request: Request, data: AdminCheckGroupCategoryData
):
    try:
        await asyncio.to_thread(
            AdminUsersService.check_group_category, data.model_dump()
        )
        # ``check_group_category`` only raises on mismatch — success
        # surfaces as an empty list so the webapp's bulk-edit form can
        # treat a non-empty body as a hard failure.
        return JSONResponse(content=[], status_code=200)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to check group/category",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Supporting Endpoints
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/items/templates",
    tags=[tag],
    summary="Get admin templates",
    description="Returns templates allowed for the admin/manager.",
    response_model=list[AdminTemplateItem],
    responses={
        200: {"description": "Templates retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_templates(request: Request):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.get_admin_templates, request.token_payload
        )
        return JSONResponse(
            content=[AdminTemplateItem(**t).model_dump(mode="json") for t in result],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve templates",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/items/user/{user_id}/templates",
    tags=[tag],
    response_model=list[AdminUserTemplateItem],
    summary="Get user templates",
    description="Returns templates allowed for a specific user.",
    responses={
        200: {"description": "User templates retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user_templates(request: Request, user_id: str):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.get_user_templates, request.token_payload, user_id
        )
        return JSONResponse(
            content=[
                AdminUserTemplateItem(**t).model_dump(mode="json")
                for t in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user templates",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/items/user/{user_id}/desktops",
    tags=[tag],
    response_model=list[AdminUserDesktopItem],
    summary="Get user desktops",
    description="Returns desktops for a specific user.",
    responses={
        200: {"description": "User desktops retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user_desktops(request: Request, user_id: str):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.get_user_desktops, request.token_payload, user_id
        )
        return JSONResponse(
            content=[
                AdminUserDesktopItem(**d).model_dump(mode="json")
                for d in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user desktops",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/items/roles",
    tags=[tag],
    response_model=list[AdminRoleItem],
    summary="List available roles",
    description="Returns roles available to the current user.",
    responses={
        200: {"description": "Roles retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_roles(request: Request):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.get_roles, request.token_payload
        )
        return JSONResponse(
            content=[
                AdminRoleItem(**r).model_dump(mode="json") for r in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve roles",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/item/role/{role_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update role",
    description="Updates a role.",
    responses={
        200: {"description": "Role updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_role(request: Request, role_id: str, data: AdminRoleUpdateData):
    try:
        # The id must come from the URL — accepting it from the body
        # would let an admin rename a role and overwrite a different
        # one. Force the URL id and ignore any body id.
        body = data.model_dump(exclude_none=True)
        body["id"] = role_id
        await asyncio.to_thread(AdminUsersService.update_role, body)
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update role",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/items/secrets",
    tags=[tag],
    response_model=list[AdminSecretItem],
    summary="Get admin secrets",
    description="Returns admin secrets/keys.",
    responses={
        200: {"description": "Secrets retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_secrets(request: Request):
    try:
        result = await asyncio.to_thread(AdminUsersService.get_secrets)
        return JSONResponse(
            content=[
                AdminSecretItem(**s).model_dump(mode="json") for s in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise e
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve secrets",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/item/secret",
    tags=[tag],
    response_model=AdminSecretCreateResponse,
    summary="Create admin secret",
    description="Creates a new admin secret.",
    responses={
        200: {"description": "Secret created"},
        500: {"model": ErrorResponse},
    },
)
async def admin_create_secret(request: Request, data: AdminSecretCreateData):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.create_secret, data.model_dump()
        )
        return JSONResponse(
            content=AdminSecretCreateResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create secret",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/item/secret/{kid}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete admin secret",
    description="Deletes an admin secret.",
    responses={
        200: {"description": "Secret deleted"},
        500: {"model": ErrorResponse},
    },
)
async def admin_delete_secret(request: Request, kid: str):
    try:
        await asyncio.to_thread(AdminUsersService.delete_secret, kid)
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete secret",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/item/user/{user_id}/vpn/{kind}/{os}",
    tags=[tag],
    response_model=AdminUserVpnFileResponse,
    summary="Get user VPN config with OS",
    description="Returns VPN configuration for a user with kind and OS.",
    responses={
        200: {"description": "VPN data retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user_vpn_with_os(
    request: Request,
    user_id: str,
    kind: Literal["config", "install"],
    os: str,
):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.get_user_vpn, request.token_payload, user_id, kind, os
        )
        return JSONResponse(
            content=AdminUserVpnFileResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve VPN data",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/item/user/{user_id}/vpn/{kind}",
    tags=[tag],
    response_model=AdminUserVpnFileResponse,
    summary="Get user VPN config",
    description="Returns VPN configuration for a user.",
    responses={
        200: {"description": "VPN data retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user_vpn(
    request: Request, user_id: str, kind: Literal["config", "install"]
):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.get_user_vpn, request.token_payload, user_id, kind
        )
        return JSONResponse(
            content=AdminUserVpnFileResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve VPN data",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/item/userschema",
    tags=[tag],
    response_model=AdminUserSchemaResponse,
    summary="Get user schema",
    description="Returns roles, categories, and groups for admin forms.",
    responses={
        200: {"description": "User schema retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user_schema(request: Request):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.get_user_schema, request.token_payload
        )
        return JSONResponse(
            content=AdminUserSchemaResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user schema",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/items/quotas",
    tags=[tag],
    response_model=AdminQuotasResponse,
    summary="Get admin quotas",
    description="Returns quotas for the admin view.",
    responses={
        200: {"description": "Quotas retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_quotas(request: Request):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.get_admin_quotas, request.token_payload
        )
        return JSONResponse(
            content=AdminQuotasResponse(**result).model_dump(
                mode="json", by_alias=True
            ),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve quotas",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/item/user/appliedquota/{user_id}",
    tags=[tag],
    response_model=AdminAppliedQuotaResponse,
    summary="Get user applied quota",
    description="Returns the applied quota for a specific user.",
    responses={
        200: {"description": "Applied quota retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user_applied_quota(request: Request, user_id: str):
    try:
        result = await asyncio.to_thread(
            AdminUsersService.get_user_applied_quota, request.token_payload, user_id
        )
        return JSONResponse(
            content=AdminAppliedQuotaResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve applied quota",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/item/user/email-category/{email}/{category}",
    tags=[tag],
    response_model=AdminUserIdResponse,
    summary="Get user by email and category",
    description="Returns user ID by email and category.",
    responses={
        200: {"description": "User ID retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user_by_email_category(request: Request, email: str, category: str):
    try:
        user_id = await asyncio.to_thread(
            AdminUsersService.get_user_by_email_and_category, email, category
        )
        return JSONResponse(
            content=AdminUserIdResponse(id=user_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user by email and category",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Auto Register
# ══════════════════════════════════════════════════════════════════════════


@admin_router.post(
    "/admin/item/user/auto-register",
    tags=[tag],
    summary="Auto register user",
    description="Auto-registers a user from the Register-Claims token.",
    response_model=AutoRegisterResponse,
    responses={
        200: {"description": "User auto-registered"},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_auto_register(
    request: Request,
    data: AutoRegisterRequest,
    register_claims: str = Header(alias="Register-Claims"),
):
    try:
        # The Authorization token authorizes the call (admin service); the user
        # identity comes from the separate Register-Claims register token.
        from api.dependencies.jwt_token import TokenFastAPI

        claims = TokenFastAPI.get_jwt_payload(register_claims)
        if claims.get("type") != "register":
            raise Error(
                "forbidden",
                "Register-Claims must be a register token",
                description_code="invalid_register_token",
            )
        user_id = await asyncio.to_thread(
            AdminUsersService.auto_register_user,
            claims,
            data.model_dump(exclude_none=True),
        )
        return JSONResponse(
            content=AutoRegisterResponse(id=user_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to auto-register user",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Migration
# ══════════════════════════════════════════════════════════════════════════


@manager_router.put(
    "/admin/item/user/migrate/{user_id}/{target_user_id}",
    tags=[tag],
    response_model=AdminMigrationStartedResponse,
    summary="Migrate user",
    description="Migrates a user's resources to another user.",
    responses={
        200: {"description": "Migration started"},
        428: {"description": "Migration validation errors"},
        500: {"model": ErrorResponse},
    },
)
async def admin_migrate_user(
    request: Request,
    user_id: str,
    target_user_id: str,
    background_tasks: BackgroundTasks,
):
    try:
        result, status = await asyncio.to_thread(
            AdminUsersService.migrate_user,
            request.token_payload,
            user_id,
            target_user_id,
            background_tasks,
        )
        payload = result if isinstance(result, dict) else {}
        return JSONResponse(
            content=AdminMigrationStartedResponse(**payload).model_dump(mode="json"),
            status_code=status,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to migrate user",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/item/user/migrate/check/{user_id}/{target_user_id}",
    tags=[tag],
    response_model=AdminMigrationErrorsResponse,
    summary="Check user migration",
    description="Checks if migration between two users is valid.",
    responses={
        200: {"description": "Migration check results"},
        500: {"model": ErrorResponse},
    },
)
async def admin_check_migration(request: Request, user_id: str, target_user_id: str):
    try:
        errors = await asyncio.to_thread(
            AdminUsersService.check_valid_migration,
            request.token_payload,
            user_id,
            target_user_id,
        )
        return JSONResponse(
            content=AdminMigrationErrorsResponse(errors=errors or []).model_dump(
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
            "Failed to check migration validity",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/user/migrate/resource/desktop/{user_id}/{target_user_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Migrate user desktops",
    description="Migrates desktops from one user to another.",
    responses={
        200: {"description": "Desktops migrated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_migrate_user_desktops(
    request: Request, user_id: str, target_user_id: str
):
    try:
        await asyncio.to_thread(
            AdminUsersService.migrate_user_resource,
            request.token_payload,
            user_id,
            target_user_id,
            "desktop",
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to migrate desktops",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/user/migrate/resource/template/{user_id}/{target_user_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Migrate user templates",
    description="Migrates templates from one user to another.",
    responses={
        200: {"description": "Templates migrated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_migrate_user_templates(
    request: Request, user_id: str, target_user_id: str
):
    try:
        await asyncio.to_thread(
            AdminUsersService.migrate_user_resource,
            request.token_payload,
            user_id,
            target_user_id,
            "template",
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to migrate templates",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/user/migrate/resource/media/{user_id}/{target_user_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Migrate user media",
    description="Migrates media from one user to another.",
    responses={
        200: {"description": "Media migrated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_migrate_user_media(request: Request, user_id: str, target_user_id: str):
    try:
        await asyncio.to_thread(
            AdminUsersService.migrate_user_resource,
            request.token_payload,
            user_id,
            target_user_id,
            "media",
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to migrate media",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/user/migrate/resource/deployments/{user_id}/{target_user_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Migrate user deployments",
    description="Migrates deployments from one user to another.",
    responses={
        200: {"description": "Deployments migrated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_migrate_user_deployments(
    request: Request, user_id: str, target_user_id: str
):
    try:
        await asyncio.to_thread(
            AdminUsersService.migrate_user_resource,
            request.token_payload,
            user_id,
            target_user_id,
            "deployments",
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to migrate deployments",
            traceback.format_exc(),
        )


@manager_router.post(
    "/admin/item/user/check/migrated",
    tags=[tag],
    response_model=AdminCheckMigratedResponse,
    summary="Check migrated users",
    description="Checks if any users in the list are migrated.",
    responses={
        200: {"description": "Migration check results"},
        500: {"model": ErrorResponse},
    },
)
async def admin_check_migrated(request: Request, data: AdminCheckMigratedData):
    try:
        migrated = await asyncio.to_thread(
            AdminUsersService.check_migrated_users, request.token_payload, data.users
        )
        return JSONResponse(
            content=AdminCheckMigratedResponse(migrated=migrated).model_dump(
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
            "Failed to check migrated users",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Bastion Domain
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/item/category/{category_id}/bastion_domain",
    tags=[tag],
    response_model=AdminBastionDomainResponse,
    summary="Get category bastion domain",
    description="Returns the bastion domain for a category.",
    responses={
        200: {"description": "Bastion domain retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_bastion_domain(request: Request, category_id: str):
    try:
        bastion_domain = await asyncio.to_thread(
            AdminUsersService.get_category_bastion_domain,
            request.token_payload,
            category_id,
        )
        return JSONResponse(
            content=AdminBastionDomainResponse(
                bastion_domain=bastion_domain
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve bastion domain",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/category/{category_id}/bastion_domain",
    tags=[tag],
    response_model=AdminBastionDomainResponse,
    summary="Update category bastion domain",
    description="Updates the bastion domain for a category.",
    responses={
        200: {"description": "Bastion domain updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_bastion_domain(
    request: Request, category_id: str, data: AdminBastionDomainData
):
    try:
        await asyncio.to_thread(
            AdminUsersService.update_category_bastion_domain,
            request.token_payload,
            category_id,
            data.model_dump(),
        )
        # ``AdminBastionDomainData`` and the response share the same
        # ``bastion_domain`` field — round-trip the request body so the
        # caller can reconcile state without a follow-up GET.
        return JSONResponse(
            content=AdminBastionDomainResponse(
                bastion_domain=data.bastion_domain
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update bastion domain",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Broadcast (SocketIO)
# ══════════════════════════════════════════════════════════════════════════


@admin_router.post(
    "/admin/item/socketio/broadcast",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Broadcast admin message",
    description="Broadcasts a message to all connected users via SocketIO.",
    responses={
        200: {"description": "Message broadcast"},
        500: {"model": ErrorResponse},
    },
)
async def admin_broadcast(request: Request, data: AdminBroadcastData):
    try:
        await asyncio.to_thread(AdminSocketioService.broadcast, data.type, data.message)
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to broadcast message",
            traceback.format_exc(),
        )
