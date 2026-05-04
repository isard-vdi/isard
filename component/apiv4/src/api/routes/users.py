#
#   Copyright © 2025 Naomi Hidalgo Piñar
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
from io import BytesIO
from typing import Literal

from api import (
    advanced_router,
    direct_viewer_router,
    open_router,
    password_reset_router,
    register_router,
    token_router,
)
from api.schemas.common import EmptyResponse, ErrorResponse, SimpleResponse
from api.schemas.deployments import DeploymentGroup, DeploymentUser
from api.schemas.users import (
    GroupsUsersCountPutData,
    GroupsUsersCountResponse,
    RegisterPostData,
    UserAllowedHardwareResponse,
    UserAPIKeyResponse,
    UserAppliedQuotaResponse,
    UserConfigResponse,
    UserDesktop,
    UserDetailsResponse,
    UserOwnsDesktopRequest,
    UserPasswordPolicyResponse,
    UserQuotaResponse,
    UserResponse,
    UserSetEmailPutData,
    UserSetLangPutData,
    UserSetPasswordPutData,
    UserVpnData,
)
from api.services.desktops import DesktopService
from api.services.error import Error
from api.services.groups import GroupsService
from api.services.users import UsersService
from cachetools import TTLCache, cached
from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from isardvdi_common.lib.users.groups.groups import GroupsProcessed as CommonGroups
from isardvdi_common.lib.users.users.user import UsersProcessed as CommonUsers

# Separate caches per endpoint so a read of /items/users does not evict
# the cached /items/groups response (both are keyed by category_id/role,
# so a single shared maxsize=1 cache would thrash between them).
users_list_cache = TTLCache(maxsize=10, ttl=360)
groups_list_cache = TTLCache(maxsize=10, ttl=360)


def _items_list_key(request: Request):
    """Cache key for /items/users and /items/groups.

    Admin sees everything (one shared entry keyed "admin"); managers see
    only their own category. The Request object must not be part of the
    key — each HTTP request is a fresh object, so keying by it would
    make the cache a no-op and (worse) keep an unawaited coroutine per
    call until TTL expiry.
    """
    payload = request.token_payload
    if payload["role_id"] == "admin":
        return "admin"
    return payload["category_id"]


def clear_users_list_cache():
    """Invalidate the /items/users cache after a user-list mutation."""
    users_list_cache.clear()


def clear_groups_list_cache():
    """Invalidate the /items/groups cache after a group-list mutation."""
    groups_list_cache.clear()


tag = "users"


## ENDPOINTS WITH DB CONNECTION ##


@register_router.post(
    "/item/user/register",
    tags=[tag],
    summary="Register a new user",
    description="Registers a new user in the system.",
    responses={
        404: {"model": ErrorResponse, "description": "Register code not found"},
        400: {"model": ErrorResponse, "description": "Invalid registration data"},
        500: {"model": ErrorResponse, "description": "Failed to register user"},
    },
    response_model=SimpleResponse,
    status_code=201,
)
async def register_user(register_post_data: RegisterPostData, request: Request):
    try:
        new_user_data = await asyncio.to_thread(
            GroupsService.code_search, register_post_data.code
        )
        if request.token_payload["category_id"] != new_user_data["category_id"]:
            raise Error(
                "not_found",
                f"Register code not found in the category {request.token_payload['category_id']}.",
            )
        user_exists = await asyncio.to_thread(
            UsersService.check_user_exists,
            uid=request.token_payload["user_id"],
            category_id=request.token_payload["category_id"],
            provider=request.token_payload["provider"],
        )
        if user_exists:
            raise Error(
                "bad_request",
                "User already exists with the provided UID in the category.",
            )
        new_user = await asyncio.to_thread(
            UsersService.create,
            provider=request.token_payload["provider"],
            category_id=request.token_payload["category_id"],
            uid=request.token_payload["user_id"],
            username=request.token_payload["username"],
            name=request.token_payload["name"],
            role_id=new_user_data["role_id"],
            group_id=new_user_data["group_id"],
            photo=request.token_payload["photo"],
            email=request.token_payload["email"],
        )
        return SimpleResponse(id=new_user.id)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to register user",
            traceback.format_exc(),
        )


@password_reset_router.get(
    "/item/user/get-password-policy",
    tags=[tag],
    summary="Get user password policy",
    description="Returns the password policy for the user.",
    responses={
        500: {"description": "Failed to retrieve password policy"},
    },
    response_model=UserPasswordPolicyResponse,
)
async def get_user_password_policy(request: Request):
    try:
        return await asyncio.to_thread(
            UsersService.get_user_password_policy,
            user_id=request.token_payload["user_id"],
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user password policy",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user/get-vpn",
    tags=[tag],
    response_class=StreamingResponse,
    summary="Get the user vpn",
    description="Returns the VPN for the user.",
    operation_id="get_user_vpn",
    responses={
        200: {
            "description": "VPN configuration file (text/plain or download)",
            "content": {"text/plain": {}, "application/octet-stream": {}},
        },
        500: {"description": "Failed to retrieve the user VPN"},
    },
)
async def get_user_vpn(request: Request):
    try:
        file = await asyncio.to_thread(
            UsersService.get_user_vpn,
            user_id=request.token_payload["user_id"],
        )

        file_bytes = file["content"].encode("utf-8")  # convert str to bytes
        file_like = BytesIO(file_bytes)

        return StreamingResponse(
            file_like,
            media_type=file.get("mime", "text/plain"),
            headers={
                "Content-Disposition": f'attachment; filename="{file["name"]}.{file["ext"]}"'
            },
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user VPN",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/user/reset-vpn",
    tags=[tag],
    status_code=204,
    response_class=Response,
    summary="Reset the user vpn",
    description="Resets the VPN keys for the user.",
    responses={
        204: {},
        500: {"description": "Failed to reset the user VPN"},
    },
)
async def user_reset_vpn(request: Request):
    try:
        await asyncio.to_thread(
            UsersService.reset_user_vpn, request.token_payload["user_id"]
        )

        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to reset the user VPN",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user/get-allowed-hardware",
    tags=[tag],
    summary="Get allowed hardware for the user",
    description="Returns the hardware configurations allowed for the user.",
    responses={
        500: {"description": "Failed to retrieve allowed hardware"},
    },
    response_model=UserAllowedHardwareResponse,
)
async def get_allowed_hardware(request: Request):
    try:
        allowed_hardware = await asyncio.to_thread(
            UsersService.get_allowed_hardware,
            user_id=request.token_payload["user_id"],
        )
        return UserAllowedHardwareResponse(**allowed_hardware)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve allowed hardware",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user/get-allowed-hardware/{domain_id}",
    tags=[tag],
    summary="Get allowed hardware for the user considering a domain",
    description=(
        "Returns the hardware configurations allowed for the user, taking "
        "into account the resources already used by the specified domain "
        "(so the caller can render an edit dialog with the domain's current "
        "resources available again)."
    ),
    responses={
        500: {"description": "Failed to retrieve allowed hardware"},
    },
    response_model=UserAllowedHardwareResponse,
)
async def get_allowed_hardware_for_domain(request: Request, domain_id: str):
    try:
        allowed_hardware = await asyncio.to_thread(
            UsersService.get_allowed_hardware,
            user_id=request.token_payload["user_id"],
            domain_id=domain_id,
        )
        return UserAllowedHardwareResponse(**allowed_hardware)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve allowed hardware for domain",
            traceback.format_exc(),
        )


@cached(cache=users_list_cache, key=_items_list_key)
@advanced_router.get(
    "/items/users",
    summary="Get all users",
    tags=[tag],
    response_model=list[dict],
    responses={
        200: {"description": "Users retrieved successfully"},
        500: {"description": "Failed to retrieve users"},
    },
    description="Returns all the users that the user in the payload can see.",
)
async def get_all_users(request: Request) -> list[dict]:
    try:
        return (
            CommonUsers.get_with_category(
                request.token_payload["category_id"]
                if request.token_payload["role_id"] != "admin"
                else None
            )
            or []
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve users",
            traceback.format_exc(),
        )


@cached(cache=groups_list_cache, key=_items_list_key)
@advanced_router.get(
    "/items/groups",
    summary="Get all groups",
    tags=[tag],
    response_model=list[DeploymentGroup],
    responses={
        200: {"description": "Groups retrieved successfully"},
        500: {"description": "Failed to retrieve groups"},
    },
    description="Returns all the groups that the user in the payload can see.",
)
async def get_all_groups(request: Request):
    try:
        return CommonGroups.get_with_category(
            request.token_payload["category_id"]
            if request.token_payload["role_id"] != "admin"
            else None
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve groups",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user",
    tags=[tag],
    response_model=UserResponse,
    summary="Get current user information",
    description="Returns basic information about the current user.",
)
async def get_user(request: Request):
    try:
        return UserResponse(
            **await asyncio.to_thread(
                UsersService.get_user_info,
                request.token_payload["user_id"],
            )
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve user info",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user/get-details",
    tags=[tag],
    response_model=UserDetailsResponse,
    response_model_exclude_none=True,
    summary="Get current user details",
    description="Returns detailed information about the current user.",
)
async def get_user_details(request: Request):
    try:
        # `response_model_exclude_none=True` drops `user_storage` when it
        # is None: the generated `isardvdi_apiv4_client` cannot handle
        # JSON null on $ref fields (`UserStorageModel.from_dict(None)`
        # crashes with TypeError), but it does handle the field being
        # absent (treated as UNSET).
        return UserDetailsResponse(
            **await asyncio.to_thread(
                UsersService.get_user_details,
                request.token_payload["user_id"],
            )
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user details",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user/get-quotas",
    tags=[tag],
    response_model=UserQuotaResponse,
    summary="Get user quotas information",
    description="Returns quotas information for the current user.",
)
async def get_user_quotas(request: Request):
    try:
        return UserQuotaResponse(
            **await asyncio.to_thread(
                UsersService.get_user_quotas,
                request.token_payload["user_id"],
            )
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user quotas",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user/get-config",
    tags=[tag],
    response_model=UserConfigResponse,
    summary="Get current user configuration",
    description="Returns configuration settings for the current user.",
)
async def get_user_config(request: Request):
    try:
        return UserConfigResponse(
            **await asyncio.to_thread(
                UsersService.get_user_config, request.token_payload
            ),
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve user info",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/user/set-lang",
    tags=[tag],
    summary="Set user language",
    description="Sets the language for the specified user.",
    responses={
        200: {"description": "Language set successfully"},
        404: {"description": "User not found"},
        500: {"description": "Failed to set language"},
    },
    response_model=SimpleResponse,
)
async def set_user_language(request: Request, data: UserSetLangPutData):
    try:
        await asyncio.to_thread(
            UsersService.set_user_language,
            user_id=request.token_payload["user_id"],
            lang=data.lang,
        )
        return SimpleResponse(id=request.token_payload["user_id"])
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to set language for user {request.token_payload['user_id']}",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/user/set-email",
    tags=[tag],
    summary="Set user email",
    description="Sets the email address for the specified user.",
    responses={
        200: {"description": "Email set successfully"},
        404: {"description": "User not found"},
        500: {"description": "Failed to update email"},
    },
    response_model=SimpleResponse,
)
async def set_user_email(request: Request, data: UserSetEmailPutData):
    try:
        await asyncio.to_thread(
            UsersService.set_user_email,
            user_id=request.token_payload["user_id"],
            email=data.email,
        )
        return SimpleResponse(id=request.token_payload["user_id"])
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to update email for user {request.token_payload['user_id']}",
            traceback.format_exc(),
        )


@advanced_router.get(
    "/item/user/get-api-key",
    tags=[tag],
    summary="Get user API key",
    description="Returns the API key for the specified user.",
    responses={
        200: {"description": "API key retrieved successfully"},
        404: {"description": "User not found"},
        500: {"description": "Failed to retrieve API key"},
    },
    response_model=UserAPIKeyResponse,
)
async def get_user_api_key(request: Request):
    try:
        return UserAPIKeyResponse(
            **await asyncio.to_thread(
                UsersService.get_user_api_key, user_id=request.token_payload["user_id"]
            )
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve API key for user {request.token_payload['user_id']}",
            traceback.format_exc(),
        )


@advanced_router.delete(
    "/item/user/expire-api-key",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Expire user API key",
    description="Deletes the API key for the specified user, making it invalid.",
    responses={
        200: {"description": "API key expired successfully"},
        404: {"description": "User not found"},
        500: {"description": "Failed to expire API key"},
    },
)
async def expire_user_api_key(request: Request) -> EmptyResponse:
    try:
        await asyncio.to_thread(
            UsersService.delete_user_api_key, user_id=request.token_payload["user_id"]
        )

        return EmptyResponse()
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to expire API key for user {request.token_payload['user_id']}",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/user/set-password",
    tags=[tag],
    summary="Set user password",
    description="Sets the password for the user calling the endpoint.",
    responses={
        200: {"description": "Password set successfully"},
        404: {"description": "User not found"},
        500: {"description": "Failed to set password"},
    },
    response_model=SimpleResponse,
)
async def set_user_password(request: Request, data: UserSetPasswordPutData):
    try:
        await asyncio.to_thread(
            UsersService.set_user_password,
            user_id=request.token_payload["user_id"],
            new_password=data.password,
            current_password=data.current_password,
        )
        return SimpleResponse(id=request.token_payload["user_id"])
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to set password for user {request.token_payload['user_id']}",
            traceback.format_exc(),
        )


@token_router.delete(
    "/item/user",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete current user",
    description="Deletes the current user (self-deletion).",
    responses={
        200: {"description": "User deleted successfully"},
        404: {"description": "User not found"},
        500: {"description": "Failed to delete user"},
    },
)
async def delete_user(request: Request) -> EmptyResponse:
    try:
        await asyncio.to_thread(
            UsersService.delete_user,
            user_id=request.token_payload["user_id"],
        )
        return EmptyResponse()
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to delete user {request.token_payload['user_id']}",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user/desktops",
    tags=[tag],
    response_model=list[dict],
    summary="Get user desktops",
    description="Returns a list of desktops for the current user.",
    operation_id="get_user_desktops_legacy",
    responses={
        200: {"description": "Desktops retrieved successfully"},
        404: {"description": "User not found"},
        500: {"description": "Failed to retrieve desktops"},
    },
)
async def get_user_desktops(request: Request) -> list[dict]:
    try:
        desktops = await asyncio.to_thread(
            UsersService.get_user_desktops,
            user_id=request.token_payload["user_id"],
        )
        return desktops or []
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user desktops",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user/desktop/{desktop_id}",
    tags=[tag],
    summary="Get specific desktop details",
    description="Returns details of a specific desktop for the current user.",
    responses={
        200: {"description": "Desktop retrieved successfully"},
        404: {"description": "Desktop not found"},
        500: {"description": "Failed to retrieve desktop"},
    },
    response_model=UserDesktop,
)
async def get_user_desktop(request: Request, desktop_id: str):
    try:
        desktop = await asyncio.to_thread(
            UsersService.get_user_desktop,
            desktop_id=desktop_id,
            user_id=request.token_payload["user_id"],
        )
        return UserDesktop(**desktop)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve desktop {desktop_id}",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user/vpn/{kind}/{os}",
    tags=[tag],
    summary="Get VPN config with OS",
    description="Returns VPN configuration for the user with the specified kind and OS.",
    responses={
        200: {"description": "VPN data retrieved successfully"},
        500: {"description": "Failed to retrieve VPN data"},
    },
    response_model=UserVpnData,
)
async def get_user_vpn_with_os(
    request: Request, kind: Literal["config", "install"], os: str
):
    try:
        vpn_data = await asyncio.to_thread(
            UsersService.get_user_vpn_data,
            kind=kind,
            os=os,
            user_id=request.token_payload["user_id"],
        )
        return UserVpnData(**vpn_data)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve VPN data",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user/vpn/{kind}",
    tags=[tag],
    summary="Get VPN config",
    description="Returns VPN configuration for the user with the specified kind.",
    operation_id="get_user_vpn_by_kind",
    responses={
        200: {"description": "VPN data retrieved successfully"},
        400: {"description": "Invalid VPN request"},
        500: {"description": "Failed to retrieve VPN data"},
    },
    response_model=UserVpnData,
)
async def get_user_vpn(request: Request, kind: Literal["config"]):
    try:
        vpn_data = await asyncio.to_thread(
            UsersService.get_user_vpn_data,
            kind=kind,
            os=False,
            user_id=request.token_payload["user_id"],
        )
        return UserVpnData(**vpn_data)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve VPN data",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user/webapp-desktops",
    tags=[tag],
    response_model=list[dict],
    summary="Get webapp desktops",
    description="Returns webapp desktops for the current user.",
    responses={
        200: {"description": "Webapp desktops retrieved successfully"},
        500: {"description": "Failed to retrieve webapp desktops"},
    },
)
async def get_webapp_desktops(request: Request) -> list[dict]:
    try:
        desktops = await asyncio.to_thread(
            UsersService.get_webapp_desktops,
            user_id=request.token_payload["user_id"],
        )
        return desktops or []
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve webapp desktops",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user/webapp-templates",
    tags=[tag],
    response_model=list[dict],
    summary="Get webapp templates",
    description="Returns webapp templates for the current user.",
    responses={
        200: {"description": "Webapp templates retrieved successfully"},
        500: {"description": "Failed to retrieve webapp templates"},
    },
)
async def get_webapp_templates(request: Request) -> list[dict]:
    try:
        templates = await asyncio.to_thread(
            UsersService.get_webapp_templates,
            user_id=request.token_payload["user_id"],
        )
        return templates or []
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve webapp templates",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/items/groups-users/count",
    tags=[tag],
    summary="Count users in groups",
    description="Returns the total number of users in the specified groups.",
    responses={
        200: {"description": "Count retrieved successfully"},
        500: {"description": "Failed to count users in groups"},
    },
    response_model=GroupsUsersCountResponse,
)
async def groups_users_count(request: Request, data: GroupsUsersCountPutData):
    try:
        quantity = await asyncio.to_thread(
            UsersService.groups_users_count,
            groups=data.groups,
            user_id=request.token_payload["user_id"],
        )
        return GroupsUsersCountResponse(quantity=quantity)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to count users in groups",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user/hardware/{kind}/allowed",
    tags=[tag],
    response_model=dict,
    summary="Get allowed hardware by kind",
    description="Returns the allowed hardware configurations for a specific hardware kind.",
    responses={
        200: {"description": "Hardware kind allowed retrieved successfully"},
        404: {"description": "User not found"},
        500: {"description": "Failed to retrieve hardware kind allowed"},
    },
)
async def get_hardware_kind_allowed(
    request: Request,
    kind: Literal[
        "interfaces",
        "graphics",
        "videos",
        "boot_order",
        "qos_id",
        "reservables",
        "forced_hyp",
        "favourite_hyp",
        "quota",
        "isos",
        "floppies",
        "disk_bus",
    ],
) -> dict:
    try:
        result = await asyncio.to_thread(
            UsersService.get_hardware_kind_allowed,
            user_id=request.token_payload["user_id"],
            kind=kind,
        )
        return result or {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve allowed hardware for kind {kind}",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user/applied-quota",
    tags=[tag],
    summary="Get applied quota",
    description="Returns the applied quota for the current user.",
    responses={
        200: {"description": "Applied quota retrieved successfully"},
        500: {"description": "Failed to retrieve applied quota"},
    },
    response_model=UserAppliedQuotaResponse,
)
async def get_user_applied_quota(request: Request):
    try:
        applied_quota = await asyncio.to_thread(
            UsersService.get_applied_quota,
            user_id=request.token_payload["user_id"],
        )
        return applied_quota
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve applied quota",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/user/bastion-allowed",
    tags=[tag],
    response_model=dict,
    summary="Check bastion access",
    description="Returns whether the current user is allowed to use bastion.",
    responses={
        200: {"description": "Bastion access check completed"},
        500: {"description": "Failed to check bastion access"},
    },
)
async def get_bastion_allowed(request: Request) -> dict:
    try:
        result = await asyncio.to_thread(
            UsersService.get_bastion_allowed,
            payload=request.token_payload,
        )
        return result or {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to check bastion access",
            traceback.format_exc(),
        )


@direct_viewer_router.post(
    "/item/user/owns-desktop",
    tags=[tag],
    summary="Check desktop viewer ownership",
    description=(
        "Verify that the caller is authorised to reach a running "
        "desktop's viewer. Used by rdpgw, websockify and guac as a "
        "service-side preflight before proxying a connection.\n\n"
        "Dispatches on three mutually-exclusive variants:\n"
        "- If the JWT payload carries a ``desktop_id`` "
        "(direct-viewer token), the body may contain an ``ip`` which "
        "must match the desktop's viewer ``guest_ip``.\n"
        "- Else if the body contains ``ip``, look up the running "
        "desktop by ``guest_ip`` index.\n"
        "- Else the body must contain ``proxy_video``, "
        "``proxy_hyper_host`` and ``port``, and the desktop is found "
        "via the ``proxies`` index.\n\n"
        "This endpoint replaces v3's ``GET /user/owns_desktop`` "
        "which used a GET-with-body pattern that could not be "
        "represented in OpenAPI."
    ),
    responses={
        200: {"description": "Caller owns or may access the desktop viewer"},
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    response_model=EmptyResponse,
)
async def user_owns_desktop(request: Request, body: UserOwnsDesktopRequest):
    try:
        payload = request.token_payload

        # Variant 1: direct-viewer token carries desktop_id.
        desktop_id = payload.get("desktop_id")
        if desktop_id:
            await asyncio.to_thread(
                DesktopService.owns_desktop_viewer_by_desktop_id,
                desktop_id=desktop_id,
                user_id=payload.get("user_id"),
                category_id=payload.get("category_id"),
                role_id=payload.get("role_id"),
                connection_ip=body.ip,
            )
            return EmptyResponse()

        # Variant 2: guess_ip in body → lookup by guest_ip index.
        if body.ip:
            await asyncio.to_thread(
                DesktopService.owns_desktop_viewer_by_ip,
                user_id=payload.get("user_id"),
                category_id=payload.get("category_id"),
                role_id=payload.get("role_id"),
                guess_ip=body.ip,
            )
            return EmptyResponse()

        # Variant 3: proxy_video + proxy_hyper_host + port → proxies index.
        if not body.proxy_video or not body.proxy_hyper_host or not body.port:
            raise Error(
                "bad_request",
                "Missing or incorrect parameters.",
                traceback.format_exc(),
                description_code="bad_request",
            )
        await asyncio.to_thread(
            DesktopService.owns_desktop_viewer_by_proxies,
            user_id=payload.get("user_id"),
            category_id=payload.get("category_id"),
            role_id=payload.get("role_id"),
            proxy_video=body.proxy_video,
            proxy_hyper_host=body.proxy_hyper_host,
            port=body.port,
        )
        return EmptyResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to verify desktop viewer ownership",
            traceback.format_exc(),
        )
