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

from api import admin_router, manager_router, token_router
from api.dependencies.alloweds import owns_domain_id
from api.dependencies.bastion import can_use_bastion, can_use_bastion_individual_domains
from api.schemas.bastion import (
    AdminBastionConfigResponse,
    AdminBastionConfigUpdateRequest,
    BastionActiveResponse,
    BastionAuthorizedKeysRequest,
    BastionDomainsRequest,
    BastionDomainVerificationConfigResponse,
    BastionDomainVerifyRequest,
    BastionDomainVerifyResponse,
    BastionRequest,
    BastionResponse,
    DeleteBastionDisallowedTargetsResponse,
)
from api.schemas.common import EmptyResponse, ErrorResponse
from api.services.bastion import BastionService
from api.services.error import Error
from fastapi import Depends, Path, Request
from fastapi.responses import JSONResponse, Response
from isardvdi_common.models.targets import Targets

tag = "bastion"


@token_router.get(
    "/items/bastions",
    tags=[tag],
    response_model=list[BastionResponse],
    summary="Get user's bastion targets",
    description="Returns a list of bastion target configurations for the user.",
    deprecated=True,
)
async def get_bastion_targets(
    request: Request, can_use_bastion=Depends(can_use_bastion)
):
    # TODO*: remove when old-frontend is removed
    targets = await asyncio.to_thread(
        Targets.get_user_targets, request.token_payload["user_id"]
    )
    return JSONResponse(
        content=[
            BastionResponse(**target).model_dump(mode="json") for target in targets
        ],
        status_code=200,
    )


@token_router.get(
    "/item/desktop/{desktop_id}/bastion",
    tags=[tag],
    response_model=BastionResponse,
    summary="Get bastion target for desktop",
    description="Returns the bastion target configuration for a desktop. Creates an empty target if none exists.",
    operation_id="get_desktop_bastion",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_domain_id("desktop_id")),
        Depends(can_use_bastion),
    ],
    deprecated=True,
)
async def get_desktop_bastion(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    # TODO*: remove when old-frontend is removed
    try:
        return JSONResponse(
            content=BastionResponse(
                **await asyncio.to_thread(
                    BastionService.get_desktop_bastion, desktop_id
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
            "Failed to retrieve desktop bastion target",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/desktop/{desktop_id}/bastion/active",
    tags=[tag],
    response_model=BastionActiveResponse,
    summary="Get read-only bastion status for a desktop",
    description="Returns whether bastion SSH/HTTP access is enabled for the desktop, "
    "plus the data needed to render the read-only access links. Never creates a "
    "target, so it can be called lazily on demand for any desktop in any status.",
    operation_id="get_desktop_bastion_active",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_domain_id("desktop_id")),
        Depends(can_use_bastion),
    ],
)
async def get_desktop_bastion_active(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        return JSONResponse(
            content=BastionActiveResponse(
                **await asyncio.to_thread(
                    BastionService.get_desktop_bastion_active, desktop_id
                )
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve desktop bastion status",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/desktop/{desktop_id}/bastion",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update bastion target for desktop",
    description="Updates the bastion target configuration for a desktop. If the user cannot use individual domains, the domain field is cleared.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_domain_id("desktop_id")),
        Depends(can_use_bastion),
    ],
    deprecated=True,
)
async def update_desktop_bastion(
    request: Request,
    data: BastionRequest,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    # TODO*: remove when old-frontend is removed
    try:
        try:
            can_use_individual_domains = await can_use_bastion_individual_domains(
                request.token_payload
            )
        except Error:
            raise
        except Exception:
            can_use_individual_domains = False
        bastion_data = data.model_dump(exclude_none=True)
        await asyncio.to_thread(
            BastionService.update_desktop_bastion,
            desktop_id,
            bastion_data,
            can_use_individual_domains,
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update desktop bastion target",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/desktop/{desktop_id}/bastion/authorized-keys",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update bastion SSH authorized keys",
    description="Updates the SSH authorized keys for a desktop's bastion target.",
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_domain_id("desktop_id")),
        Depends(can_use_bastion),
    ],
)
async def update_bastion_authorized_keys(
    request: Request,
    data: BastionAuthorizedKeysRequest,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        await asyncio.to_thread(
            BastionService.update_bastion_authorized_keys,
            desktop_id,
            data.authorized_keys,
            request.token_payload["user_id"],
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update bastion authorized keys",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/desktop/{desktop_id}/bastion/domains",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update bastion custom domains",
    description="Updates the custom domain names for a desktop's bastion target. New domains are verified via DNS if domain verification is required.",
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        412: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_domain_id("desktop_id")),
    ],
)
async def update_bastion_domains(
    request: Request,
    data: BastionDomainsRequest,
    desktop_id: str = Path(..., description="The ID of the desktop"),
    can_use_individual: bool = Depends(can_use_bastion_individual_domains),
):
    try:
        if not can_use_individual:
            raise Error(
                "forbidden",
                "User cannot use individual bastion domains",
            )
        await asyncio.to_thread(
            BastionService.update_bastion_domains,
            desktop_id,
            data.domains,
            request.token_payload["category_id"],
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update bastion domains",
            traceback.format_exc(),
        )


@token_router.post(
    "/item/desktop/{desktop_id}/bastion/domain/verify",
    tags=[tag],
    response_model=BastionDomainVerifyResponse,
    summary="Verify bastion domain DNS",
    description="Verifies a single domain's DNS configuration without saving. Returns success if the CNAME record is valid.",
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        412: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_domain_id("desktop_id")),
    ],
    deprecated=True,
)
async def verify_bastion_domain(
    request: Request,
    data: BastionDomainVerifyRequest,
    desktop_id: str = Path(..., description="The ID of the desktop"),
    can_use_individual: bool = Depends(can_use_bastion_individual_domains),
):
    # TODO*: remove when old-frontend is removed
    try:
        if not can_use_individual:
            raise Error(
                "forbidden",
                "User cannot use individual bastion domains",
            )
        return JSONResponse(
            content=BastionDomainVerifyResponse(
                **await asyncio.to_thread(
                    BastionService.verify_bastion_domain,
                    desktop_id,
                    data.domain,
                    request.token_payload["category_id"],
                )
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to verify bastion domain",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/item/config/bastion",
    tags=[tag],
    response_model=AdminBastionConfigResponse,
    summary="Get admin bastion configuration",
    description="Returns the bastion configuration overview including enabled status, domain, SSH port, and domain verification settings.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_admin_bastion_config(request: Request):
    try:
        return JSONResponse(
            content=AdminBastionConfigResponse(
                **await asyncio.to_thread(BastionService.get_admin_bastion_config)
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve admin bastion configuration",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/items/bastion/disallowed",
    tags=[tag],
    response_model=dict,
    summary="Remove disallowed bastion targets",
    description="Removes bastion targets that are no longer allowed based on current permissions.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def remove_disallowed_bastion_targets(request: Request):
    try:
        result = await asyncio.to_thread(
            BastionService.remove_disallowed_bastion_targets
        )
        return JSONResponse(
            content=DeleteBastionDisallowedTargetsResponse(
                removed_targets=result
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to remove disallowed bastion targets",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/item/config/bastion",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update bastion configuration",
    description="Updates the bastion configuration including enabled status, domain, and domain verification settings.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def update_bastion_config(
    request: Request,
    data: AdminBastionConfigUpdateRequest,
):
    try:
        await asyncio.to_thread(
            BastionService.update_bastion_config,
            data.enabled,
            data.bastion_domain,
            data.domain_verification_required,
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update bastion configuration",
            traceback.format_exc(),
        )


@manager_router.get(
    "/bastion/config",
    tags=[tag],
    response_model=BastionDomainVerificationConfigResponse,
    summary="Get bastion domain verification configuration",
    description="Returns whether domain verification is required for bastion domains.",
    responses={
        500: {"model": ErrorResponse},
    },
    deprecated=True,
)
async def get_bastion_domain_verification_config(request: Request):
    # TODO@: probably not in use
    try:
        config = await asyncio.to_thread(
            BastionService.get_bastion_domain_verification_config
        )
        return JSONResponse(
            content=BastionDomainVerificationConfigResponse(**config).model_dump(
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
            "Failed to retrieve bastion domain verification configuration",
            traceback.format_exc(),
        )
