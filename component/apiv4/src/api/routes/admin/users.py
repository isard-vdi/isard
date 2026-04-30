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

import json
import traceback
from typing import Literal, Optional

from api import admin_router, manager_router
from api.schemas.admin_users import (
    AdminBastionDomainData,
    AdminBroadcastData,
    AdminBulkUserCreateData,
    AdminCategoryCreateData,
    AdminCategoryUpdateData,
    AdminCheckGroupCategoryData,
    AdminCheckMigratedData,
    AdminCSVUserEditData,
    AdminDeleteChecksData,
    AdminGroup,
    AdminGroupCreateData,
    AdminGroupEnrollmentData,
    AdminGroupUpdateData,
    AdminLimitsUpdateData,
    AdminPasswordResetData,
    AdminQuotaUpdateData,
    AdminSecondaryGroupsData,
    AdminSecretCreateData,
    AdminTemplateItem,
    AdminUser,
    AdminUserCreateData,
    AdminUserDeleteData,
    AdminUserDeleteResponse,
    AdminUserSearchData,
    AdminUserUpdateData,
    AutoRegisterRequest,
    AutoRegisterResponse,
    RequiredCheckResponse,
)
from api.schemas.common import EmptyResponse, ErrorResponse
from api.services.admin_socketio import AdminSocketioService
from api.services.admin_users import AdminUsersService
from api.services.error import Error
from cachetools import TTLCache, cached
from fastapi import Path, Query, Request
from fastapi.responses import JSONResponse

tag = "admin_users"


# ══════════════════════════════════════════════════════════════════════════
#  User CRUD & Management
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/jwt/{user_id}",
    tags=[tag],
    summary="Get impersonation JWT for user",
    description="Generates a JWT token to impersonate the specified user. Requires ownership check.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_jwt(request: Request, user_id: str):
    try:
        AdminUsersService.owns_user_id(request.token_payload, user_id)
        result = AdminUsersService.get_impersonate_jwt(user_id)
        return JSONResponse(content=result, status_code=200)
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
    "/admin/user/{user_id}/exists",
    tags=[tag],
    summary="Check if user exists",
    description="Returns whether a user with the given ID exists.",
    responses={
        200: {"description": "User existence check result"},
        500: {"model": ErrorResponse},
    },
)
async def admin_user_exists(request: Request, user_id: str):
    try:
        AdminUsersService.owns_user_id(request.token_payload, user_id)
        return JSONResponse(
            content=AdminUsersService.user_exists(user_id),
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


@cached(cache=TTLCache(maxsize=100, ttl=60))
@manager_router.get(
    "/admin/user/{user_id}",
    tags=[tag],
    summary="Get user full data",
    description="Returns full data for a user.",
    responses={
        200: {"description": "User data retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user(request: Request, user_id: str):
    try:
        AdminUsersService.owns_user_id(request.token_payload, user_id)
        return JSONResponse(
            content=AdminUsersService.get_user_full_data(user_id),
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
    "/admin/user/{user_id}/raw",
    tags=[tag],
    summary="Get user raw data",
    description="Returns raw user data from database.",
    responses={
        200: {"description": "Raw user data retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user_raw(request: Request, user_id: str):
    try:
        AdminUsersService.owns_user_id(request.token_payload, user_id)
        return JSONResponse(
            content=AdminUsersService.get_user_raw(user_id),
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
    "/admin/users",
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
        result = AdminUsersService.list_users(category_id=category_id)
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
    "/admin/users/{nav}/users",
    tags=[tag],
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
        return JSONResponse(
            content=AdminUsersService.list_users_nav(request.token_payload, nav),
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
    "/admin/user",
    tags=[tag],
    summary="Create user",
    description="Creates a new user.",
    response_model=AdminUser,
    responses={
        200: {"description": "User created"},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_create_user(request: Request, data: AdminUserCreateData):
    try:
        result = AdminUsersService.create_user(request.token_payload, data.model_dump())
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
    "/admin/user/{user_id}",
    tags=[tag],
    summary="Update user",
    description="Updates a single user.",
    responses={
        200: {"description": "User updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_user(request: Request, user_id: str):
    try:
        try:
            data = await request.json()
        except json.JSONDecodeError:
            raise Error("bad_request", "Request body must be JSON")
        data["ids"] = [user_id]
        AdminUsersService.update_user(request.token_payload, user_id, data)
        return JSONResponse(content={}, status_code=200)
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
    "/admin/users/bulk",
    tags=[tag],
    summary="Bulk update users",
    description="Updates multiple users at once.",
    responses={
        200: {"description": "Users updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_users_bulk(request: Request):
    try:
        try:
            data = await request.json()
        except json.JSONDecodeError:
            raise Error("bad_request", "Request body must be JSON")
        AdminUsersService.update_multiple_users(request.token_payload, data)
        return JSONResponse(content={}, status_code=200)
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
    "/admin/user",
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
async def admin_delete_users(request: Request, data: AdminUserDeleteData):
    try:
        result, status = AdminUsersService.delete_users(
            request.token_payload, data.model_dump()
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
    "/admin/user/{user_id}/logout",
    tags=[tag],
    summary="Force logout user",
    description="Revokes all sessions for a user.",
    responses={
        200: {"description": "User logged out"},
        500: {"model": ErrorResponse},
    },
)
async def admin_user_logout(request: Request, user_id: str):
    try:
        AdminUsersService.force_logout_user(request.token_payload, user_id)
        return JSONResponse(content={}, status_code=200)
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
    "/admin/users/search",
    tags=[tag],
    summary="Search users",
    description="Search users by name term.",
    responses={
        200: {"description": "Search results"},
        500: {"model": ErrorResponse},
    },
)
async def admin_search_users(request: Request, data: AdminUserSearchData):
    try:
        result = AdminUsersService.search_users(request.token_payload, data.term)
        return JSONResponse(content=result, status_code=200)
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
    "/admin/users/csv/validate",
    tags=[tag],
    summary="Validate CSV for user creation",
    description="Validates a list of users from CSV data.",
    responses={
        200: {"description": "Validation results"},
        500: {"model": ErrorResponse},
    },
)
async def admin_validate_csv_users(request: Request):
    try:
        try:
            user_list = await request.json()
        except json.JSONDecodeError:
            raise Error("bad_request", "Request body must be JSON")
        result = AdminUsersService.validate_csv_users(request.token_payload, user_list)
        return JSONResponse(content=result, status_code=200)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to validate CSV users",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/users/csv/validate",
    tags=[tag],
    summary="Validate CSV for user editing",
    description="Validates a list of users from CSV for editing.",
    responses={
        200: {"description": "Validation results"},
        500: {"model": ErrorResponse},
    },
)
async def admin_validate_csv_users_edit(request: Request):
    try:
        try:
            user_list = await request.json()
        except json.JSONDecodeError:
            raise Error("bad_request", "Request body must be JSON")
        result = AdminUsersService.validate_csv_users_edit(
            request.token_payload, user_list
        )
        return JSONResponse(content=result, status_code=200)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to validate CSV users for edit",
            traceback.format_exc(),
        )


@manager_router.post(
    "/admin/users/csv",
    tags=[tag],
    summary="Import users from CSV",
    description="Creates users from validated CSV data.",
    responses={
        200: {"description": "Import started"},
        500: {"model": ErrorResponse},
    },
)
async def admin_import_csv_users(request: Request):
    try:
        try:
            data = await request.json()
        except json.JSONDecodeError:
            raise Error("bad_request", "Request body must be JSON")
        result = AdminUsersService.import_csv_users(request.token_payload, data)
        return JSONResponse(
            content={
                "created": len(result.get("users", [])),
                "errors": result.get("errors", []),
            },
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to import CSV users",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/users/csv",
    tags=[tag],
    summary="Edit users from CSV",
    description="Updates users from validated CSV data.",
    responses={
        200: {"description": "Users updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_edit_csv_users(request: Request, data: AdminCSVUserEditData):
    try:
        AdminUsersService.edit_csv_users(request.token_payload, data.model_dump())
        return JSONResponse(content={}, status_code=200)
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
    "/admin/bulk/user",
    tags=[tag],
    summary="Bulk create users",
    description="Creates multiple users in bulk.",
    responses={
        200: {"description": "Bulk creation started"},
        500: {"model": ErrorResponse},
    },
)
async def admin_bulk_create_users(request: Request):
    try:
        try:
            try:
                data = await request.json()
            except json.JSONDecodeError:
                raise Error("bad_request", "Request body must be JSON")
        except Error:
            raise
        except Exception:
            raise await Error.create(
                request, "bad_request", "Request body must be JSON"
            )
        result = AdminUsersService.import_csv_users(request.token_payload, data)
        return JSONResponse(
            content={
                "created": len(result.get("users", [])),
                "errors": result.get("errors", []),
            },
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
    "/admin/user/secondary-groups/add",
    tags=[tag],
    summary="Add secondary groups",
    description="Adds secondary groups to specified users.",
    responses={
        200: {"description": "Secondary groups added"},
        500: {"model": ErrorResponse},
    },
)
async def admin_secondary_groups_add(request: Request, data: AdminSecondaryGroupsData):
    try:
        AdminUsersService.update_secondary_groups(
            request.token_payload, "add", data.model_dump()
        )
        return JSONResponse(content={}, status_code=200)
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
    "/admin/user/secondary-groups/overwrite",
    tags=[tag],
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
        AdminUsersService.update_secondary_groups(
            request.token_payload, "overwrite", data.model_dump()
        )
        return JSONResponse(content={}, status_code=200)
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
    "/admin/user/secondary-groups/delete",
    tags=[tag],
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
        AdminUsersService.update_secondary_groups(
            request.token_payload, "delete", data.model_dump()
        )
        return JSONResponse(content={}, status_code=200)
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
    "/admin/user/password-policy/{user_id}",
    tags=[tag],
    summary="Get user password policy",
    description="Returns the password policy for a user.",
    responses={
        200: {"description": "Password policy retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_password_policy(request: Request, user_id: str):
    try:
        return JSONResponse(
            content=AdminUsersService.get_password_policy(
                request.token_payload, user_id
            ),
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
    # NOTE: /admin/users/ (plural) so the path is not shadowed by the
    # /admin/user/{user_id} PUT catch-all on manager_router (defined above
    # in this file), which is registered earlier because manager_router is
    # included before admin_router in api/__init__.py.
    "/admin/users/reset-password",
    tags=[tag],
    summary="Reset user password",
    description="Admin resets a user's password.",
    response_model=EmptyResponse,
    responses={
        200: {"description": "Password reset"},
        500: {"model": ErrorResponse},
    },
)
async def admin_reset_password(request: Request, data: AdminPasswordResetData):
    try:
        AdminUsersService.reset_password(data.model_dump())
        return JSONResponse(
            content=EmptyResponse().model_dump(),
            status_code=200,
        )
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
    "/admin/user/required/password-reset/{user_id}",
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
                required=AdminUsersService.check_password_expiration(user_id)
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
    "/admin/user/required/email-verification/{user_id}",
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
                required=AdminUsersService.check_email_verified(user_id)
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
    "/admin/user/required/disclaimer-acknowledgement/{user_id}",
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
                required=AdminUsersService.check_disclaimer_acknowledgement(user_id)
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
    "/admin/user/reset-vpn/{user_id}",
    tags=[tag],
    summary="Reset user VPN",
    description="Resets VPN credentials for a user.",
    responses={
        200: {"description": "VPN reset"},
        500: {"model": ErrorResponse},
    },
)
async def admin_reset_vpn(request: Request, user_id: str):
    try:
        AdminUsersService.reset_vpn(request.token_payload, user_id)
        return JSONResponse(content={}, status_code=200)
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
    "/admin/groups",
    tags=[tag],
    summary="List groups",
    description="Returns all groups. Managers see only their category groups.",
    responses={
        200: {"description": "Groups list retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_list_groups(request: Request):
    try:
        return JSONResponse(
            content=AdminUsersService.list_groups(request.token_payload),
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
    "/admin/users/{nav}/groups",
    tags=[tag],
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
        return JSONResponse(
            content=AdminUsersService.list_groups_nav(request.token_payload, nav),
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
    "/admin/group/{group_id}",
    tags=[tag],
    summary="Get group",
    description="Returns full data for a group.",
    responses={
        200: {"description": "Group data retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_group(request: Request, group_id: str):
    try:
        return JSONResponse(
            content=AdminUsersService.get_group(group_id),
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
    "/admin/group",
    tags=[tag],
    summary="Create group",
    description="Creates a new group.",
    response_model=AdminGroup,
    responses={
        200: {"description": "Group created"},
        500: {"model": ErrorResponse},
    },
)
async def admin_create_group(request: Request, data: AdminGroupCreateData):
    try:
        result = AdminUsersService.create_group(
            request.token_payload, data.model_dump()
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
    "/admin/group/{group_id}",
    tags=[tag],
    summary="Update group",
    description="Updates a group.",
    responses={
        200: {"description": "Group updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_group(request: Request, group_id: str):
    try:
        try:
            data = await request.json()
        except json.JSONDecodeError:
            raise Error("bad_request", "Request body must be JSON")
        AdminUsersService.update_group(request.token_payload, group_id, data)
        return JSONResponse(content=data, status_code=200)
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
    "/admin/group/{group_id}",
    tags=[tag],
    summary="Delete group",
    description="Deletes a group.",
    responses={
        200: {"description": "Group deleted"},
        500: {"model": ErrorResponse},
    },
)
async def admin_delete_group(request: Request, group_id: str):
    try:
        AdminUsersService.delete_group(request.token_payload, group_id)
        return JSONResponse(content={}, status_code=200)
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
    "/admin/group/{group_id}/users",
    tags=[tag],
    summary="Get users in group",
    description="Returns all users in a specific group.",
    responses={
        200: {"description": "Group users retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_group_users(request: Request, group_id: str):
    try:
        return JSONResponse(
            content=AdminUsersService.get_group_users(request.token_payload, group_id),
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
    "/admin/group/enrollment",
    tags=[tag],
    summary="Update group enrollment",
    description="Updates enrollment settings for a group.",
    responses={
        200: {"description": "Enrollment updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_group_enrollment(request: Request, data: AdminGroupEnrollmentData):
    try:
        result = AdminUsersService.update_group_enrollment(
            request.token_payload, data.model_dump()
        )
        return JSONResponse(content=result, status_code=200)
    except Error:
        raise
    except Exception as e:
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
    "/admin/categories",
    tags=[tag],
    summary="List categories",
    description="Returns all categories.",
    responses={
        200: {"description": "Categories list retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_list_categories(request: Request):
    try:
        return JSONResponse(
            content=AdminUsersService.list_categories(request.token_payload),
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
    "/admin/categories/{frontend}",
    tags=[tag],
    summary="List frontend categories",
    description="Returns categories for frontend display.",
    responses={
        200: {"description": "Frontend categories list retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_list_categories_frontend(request: Request, frontend: str):
    try:
        return JSONResponse(
            content=AdminUsersService.list_categories(
                request.token_payload, frontend=True
            ),
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
    "/admin/users/{nav}/categories",
    tags=[tag],
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
        return JSONResponse(
            content=AdminUsersService.list_categories_nav(request.token_payload, nav),
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
    "/admin/category/{category_id}",
    tags=[tag],
    summary="Get category",
    description="Returns data for a specific category.",
    responses={
        200: {"description": "Category data retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_category(request: Request, category_id: str):
    try:
        return JSONResponse(
            content=AdminUsersService.get_category(request.token_payload, category_id),
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
    "/admin/category",
    tags=[tag],
    summary="Create category",
    description="Creates a new category with an associated Main group.",
    responses={
        200: {"description": "Category created"},
        500: {"model": ErrorResponse},
    },
)
async def admin_create_category(request: Request, data: AdminCategoryCreateData):
    try:
        result = AdminUsersService.create_category(
            request.token_payload, data.model_dump()
        )
        return JSONResponse(content=result, status_code=200)
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
    "/admin/category/{category_id}",
    tags=[tag],
    summary="Update category",
    description="Updates a category.",
    responses={
        200: {"description": "Category updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_category(request: Request, category_id: str):
    try:
        try:
            data = await request.json()
        except json.JSONDecodeError:
            raise Error("bad_request", "Request body must be JSON")
        AdminUsersService.update_category(request.token_payload, category_id, data)
        return JSONResponse(content=data, status_code=200)
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
    "/admin/category/{category_id}",
    tags=[tag],
    summary="Delete category",
    description="Deletes a category.",
    responses={
        200: {"description": "Category deleted"},
        500: {"model": ErrorResponse},
    },
)
async def admin_delete_category(request: Request, category_id: str):
    try:
        result = AdminUsersService.delete_category(request.token_payload, category_id)
        return JSONResponse(content=result, status_code=200)
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
    "/admin/category/{category_id}/users",
    tags=[tag],
    summary="Get users in category",
    description="Returns all users in a specific category.",
    responses={
        200: {"description": "Category users retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_category_users(request: Request, category_id: str):
    try:
        return JSONResponse(
            content=AdminUsersService.get_category_users(
                request.token_payload, category_id
            ),
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
    "/admin/category/get/{category_name}",
    tags=[tag],
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
        category_id = AdminUsersService.get_category_by_name(category_name)
        return JSONResponse(content=category_id, status_code=200)
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
    "/admin/group/get/{category_name}/{group_name}",
    tags=[tag],
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
        group_id = AdminUsersService.get_group_by_name_category(
            category_name, group_name
        )
        return JSONResponse(content=group_id, status_code=200)
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
    "/admin/quota/group/{group_id}",
    tags=[tag],
    summary="Update group quota",
    description="Updates quota for a group.",
    responses={
        200: {"description": "Group quota updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_group_quota(request: Request, group_id: str):
    try:
        try:
            data = await request.json()
        except json.JSONDecodeError:
            raise Error("bad_request", "Request body must be JSON")
        AdminUsersService.update_group_quota(request.token_payload, group_id, data)
        return JSONResponse(content=data, status_code=200)
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
    "/admin/quota/category/{category_id}",
    tags=[tag],
    summary="Update category quota",
    description="Updates quota for a category.",
    responses={
        200: {"description": "Category quota updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_category_quota(request: Request, category_id: str):
    try:
        try:
            data = await request.json()
        except json.JSONDecodeError:
            raise Error("bad_request", "Request body must be JSON")
        AdminUsersService.update_category_quota(
            request.token_payload, category_id, data
        )
        return JSONResponse(content=data, status_code=200)
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
    "/admin/limits/group/{group_id}",
    tags=[tag],
    summary="Update group limits",
    description="Updates limits for a group.",
    responses={
        200: {"description": "Group limits updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_group_limits(request: Request, group_id: str):
    try:
        try:
            data = await request.json()
        except json.JSONDecodeError:
            raise Error("bad_request", "Request body must be JSON")
        AdminUsersService.update_group_limits(request.token_payload, group_id, data)
        return JSONResponse(content=data, status_code=200)
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
    "/admin/limits/category/{category_id}",
    tags=[tag],
    summary="Update category limits",
    description="Updates limits for a category.",
    responses={
        200: {"description": "Category limits updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_category_limits(request: Request, category_id: str):
    try:
        try:
            data = await request.json()
        except json.JSONDecodeError:
            raise Error("bad_request", "Request body must be JSON")
        AdminUsersService.update_category_limits(
            request.token_payload, category_id, data
        )
        return JSONResponse(content=data, status_code=200)
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
    "/admin/user/delete/check",
    tags=[tag],
    summary="Check user deletion dependencies",
    description="Checks dependencies before deleting users.",
    responses={
        200: {"description": "Deletion check results"},
        500: {"model": ErrorResponse},
    },
)
async def admin_user_delete_check(request: Request, data: AdminDeleteChecksData):
    try:
        result = AdminUsersService.user_delete_checks(request.token_payload, data.ids)
        return JSONResponse(content=result, status_code=200)
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
    "/admin/group/delete/check",
    tags=[tag],
    summary="Check group deletion dependencies",
    description="Checks dependencies before deleting groups.",
    responses={
        200: {"description": "Deletion check results"},
        500: {"model": ErrorResponse},
    },
)
async def admin_group_delete_check(request: Request, data: AdminDeleteChecksData):
    try:
        result = AdminUsersService.group_delete_checks(request.token_payload, data.ids)
        return JSONResponse(content=result, status_code=200)
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
    "/admin/category/delete/check",
    tags=[tag],
    summary="Check category deletion dependencies",
    description="Checks dependencies before deleting categories.",
    responses={
        200: {"description": "Deletion check results"},
        500: {"model": ErrorResponse},
    },
)
async def admin_category_delete_check(request: Request, data: AdminDeleteChecksData):
    try:
        result = AdminUsersService.category_delete_checks(
            request.token_payload, data.ids
        )
        return JSONResponse(content=result, status_code=200)
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
    "/admin/check/group/category",
    tags=[tag],
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
        AdminUsersService.check_group_category(data.model_dump())
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
    "/admin/templates",
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
        result = AdminUsersService.get_admin_templates(request.token_payload)
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
    "/admin/user/{user_id}/templates",
    tags=[tag],
    summary="Get user templates",
    description="Returns templates allowed for a specific user.",
    responses={
        200: {"description": "User templates retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user_templates(request: Request, user_id: str):
    try:
        return JSONResponse(
            content=AdminUsersService.get_user_templates(
                request.token_payload, user_id
            ),
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
    "/admin/user/{user_id}/desktops",
    tags=[tag],
    summary="Get user desktops",
    description="Returns desktops for a specific user.",
    responses={
        200: {"description": "User desktops retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user_desktops(request: Request, user_id: str):
    try:
        return JSONResponse(
            content=AdminUsersService.get_user_desktops(request.token_payload, user_id),
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
    "/admin/roles",
    tags=[tag],
    summary="List available roles",
    description="Returns roles available to the current user.",
    responses={
        200: {"description": "Roles retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_roles(request: Request):
    try:
        return JSONResponse(
            content=AdminUsersService.get_roles(request.token_payload),
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
    "/admin/role/{role_id}",
    tags=[tag],
    summary="Update role",
    description="Updates a role.",
    responses={
        200: {"description": "Role updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_role(request: Request, role_id: str):
    try:
        try:
            try:
                data = await request.json()
            except json.JSONDecodeError:
                raise Error("bad_request", "Request body must be JSON")
        except Exception:
            raise await Error.create(
                request, "bad_request", "Request body must be JSON"
            )
        if not isinstance(data, dict):
            raise await Error.create(
                request, "bad_request", "Request body must be a JSON object"
            )
        # The id must come from the URL — accepting it from the body
        # would let an admin rename a role and overwrite a different
        # one. Force the URL id and let any body id be ignored.
        data["id"] = role_id
        AdminUsersService.update_role(data)
        return JSONResponse(content=data, status_code=200)
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
    "/admin/secrets",
    tags=[tag],
    summary="Get admin secrets",
    description="Returns admin secrets/keys.",
    responses={
        200: {"description": "Secrets retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_secrets(request: Request):
    try:
        return JSONResponse(
            content=AdminUsersService.get_secrets(),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve secrets",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/secret",
    tags=[tag],
    summary="Create admin secret",
    description="Creates a new admin secret.",
    responses={
        200: {"description": "Secret created"},
        500: {"model": ErrorResponse},
    },
)
async def admin_create_secret(request: Request, data: AdminSecretCreateData):
    try:
        result = AdminUsersService.create_secret(data.model_dump())
        return JSONResponse(content=result, status_code=200)
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
    "/admin/secret/{kid}",
    tags=[tag],
    summary="Delete admin secret",
    description="Deletes an admin secret.",
    responses={
        200: {"description": "Secret deleted"},
        500: {"model": ErrorResponse},
    },
)
async def admin_delete_secret(request: Request, kid: str):
    try:
        AdminUsersService.delete_secret(kid)
        return JSONResponse(content={}, status_code=200)
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
    "/admin/user/{user_id}/vpn/{kind}/{os}",
    tags=[tag],
    summary="Get user VPN config with OS",
    description="Returns VPN configuration for a user with kind and OS.",
    responses={
        200: {"description": "VPN data retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user_vpn_with_os(
    request: Request, user_id: str, kind: str, os: str
):
    try:
        return JSONResponse(
            content=AdminUsersService.get_user_vpn(
                request.token_payload, user_id, kind, os
            ),
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
    "/admin/user/{user_id}/vpn/{kind}",
    tags=[tag],
    summary="Get user VPN config",
    description="Returns VPN configuration for a user.",
    responses={
        200: {"description": "VPN data retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user_vpn(request: Request, user_id: str, kind: str):
    try:
        return JSONResponse(
            content=AdminUsersService.get_user_vpn(
                request.token_payload, user_id, kind
            ),
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
    "/admin/userschema",
    tags=[tag],
    summary="Get user schema",
    description="Returns roles, categories, and groups for admin forms.",
    responses={
        200: {"description": "User schema retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user_schema(request: Request):
    try:
        return JSONResponse(
            content=AdminUsersService.get_user_schema(request.token_payload),
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
    "/admin/quotas",
    tags=[tag],
    summary="Get admin quotas",
    description="Returns quotas for the admin view.",
    responses={
        200: {"description": "Quotas retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_quotas(request: Request):
    try:
        return JSONResponse(
            content=AdminUsersService.get_admin_quotas(request.token_payload),
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
    "/admin/user/appliedquota/{user_id}",
    tags=[tag],
    summary="Get user applied quota",
    description="Returns the applied quota for a specific user.",
    responses={
        200: {"description": "Applied quota retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user_applied_quota(request: Request, user_id: str):
    try:
        return JSONResponse(
            content=AdminUsersService.get_user_applied_quota(
                request.token_payload, user_id
            ),
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
    "/admin/user/email-category/{email}/{category}",
    tags=[tag],
    summary="Get user by email and category",
    description="Returns user ID by email and category.",
    responses={
        200: {"description": "User ID retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_user_by_email_category(request: Request, email: str, category: str):
    try:
        return JSONResponse(
            content={
                "id": AdminUsersService.get_user_by_email_and_category(email, category)
            },
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
    "/admin/user/auto-register",
    tags=[tag],
    summary="Auto register user",
    description="Auto-registers a user based on token payload.",
    response_model=AutoRegisterResponse,
    responses={
        200: {"description": "User auto-registered"},
        500: {"model": ErrorResponse},
    },
)
async def admin_auto_register(request: Request, data: AutoRegisterRequest):
    try:
        user_id = AdminUsersService.auto_register_user(
            request.token_payload, data.model_dump(exclude_none=True)
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
    "/admin/user/migrate/{user_id}/{target_user_id}",
    tags=[tag],
    summary="Migrate user",
    description="Migrates a user's resources to another user.",
    responses={
        200: {"description": "Migration started"},
        428: {"description": "Migration validation errors"},
        500: {"model": ErrorResponse},
    },
)
async def admin_migrate_user(request: Request, user_id: str, target_user_id: str):
    try:
        result, status = AdminUsersService.migrate_user(
            request.token_payload, user_id, target_user_id
        )
        return JSONResponse(content=result, status_code=status)
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
    "/admin/user/migrate/check/{user_id}/{target_user_id}",
    tags=[tag],
    summary="Check user migration",
    description="Checks if migration between two users is valid.",
    responses={
        200: {"description": "Migration check results"},
        500: {"model": ErrorResponse},
    },
)
async def admin_check_migration(request: Request, user_id: str, target_user_id: str):
    try:
        errors = AdminUsersService.check_valid_migration(
            request.token_payload, user_id, target_user_id
        )
        return JSONResponse(content={"errors": errors}, status_code=200)
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
    "/admin/user/migrate/resource/desktop/{user_id}/{target_user_id}",
    tags=[tag],
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
        AdminUsersService.migrate_user_resource(
            request.token_payload, user_id, target_user_id, "desktop"
        )
        return JSONResponse(content={}, status_code=200)
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
    "/admin/user/migrate/resource/template/{user_id}/{target_user_id}",
    tags=[tag],
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
        AdminUsersService.migrate_user_resource(
            request.token_payload, user_id, target_user_id, "template"
        )
        return JSONResponse(content={}, status_code=200)
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
    "/admin/user/migrate/resource/media/{user_id}/{target_user_id}",
    tags=[tag],
    summary="Migrate user media",
    description="Migrates media from one user to another.",
    responses={
        200: {"description": "Media migrated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_migrate_user_media(request: Request, user_id: str, target_user_id: str):
    try:
        AdminUsersService.migrate_user_resource(
            request.token_payload, user_id, target_user_id, "media"
        )
        return JSONResponse(content={}, status_code=200)
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
    "/admin/user/migrate/resource/deployments/{user_id}/{target_user_id}",
    tags=[tag],
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
        AdminUsersService.migrate_user_resource(
            request.token_payload, user_id, target_user_id, "deployments"
        )
        return JSONResponse(content={}, status_code=200)
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
    "/admin/user/check/migrated",
    tags=[tag],
    summary="Check migrated users",
    description="Checks if any users in the list are migrated.",
    responses={
        200: {"description": "Migration check results"},
        500: {"model": ErrorResponse},
    },
)
async def admin_check_migrated(request: Request, data: AdminCheckMigratedData):
    try:
        migrated = AdminUsersService.check_migrated_users(
            request.token_payload, data.users
        )
        return JSONResponse(content={"migrated": migrated}, status_code=200)
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
    "/admin/category/{category_id}/bastion_domain",
    tags=[tag],
    summary="Get category bastion domain",
    description="Returns the bastion domain for a category.",
    responses={
        200: {"description": "Bastion domain retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_bastion_domain(request: Request, category_id: str):
    try:
        bastion_domain = AdminUsersService.get_category_bastion_domain(
            request.token_payload, category_id
        )
        return JSONResponse(
            content={"bastion_domain": bastion_domain},
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
    "/admin/category/{category_id}/bastion_domain",
    tags=[tag],
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
        AdminUsersService.update_category_bastion_domain(
            request.token_payload, category_id, data.model_dump()
        )
        return JSONResponse(content=data.model_dump(), status_code=200)
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
    "/admin/socketio/broadcast",
    tags=[tag],
    summary="Broadcast admin message",
    description="Broadcasts a message to all connected users via SocketIO.",
    responses={
        200: {"description": "Message broadcast"},
        500: {"model": ErrorResponse},
    },
)
async def admin_broadcast(request: Request, data: AdminBroadcastData):
    try:
        AdminSocketioService.broadcast(data.type, data.message)
        return JSONResponse(content={}, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to broadcast message",
            traceback.format_exc(),
        )
