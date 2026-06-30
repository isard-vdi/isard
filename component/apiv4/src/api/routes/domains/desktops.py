#
#   Copyright © 2025 Naomi Hidalgo Piñar, Miriam Melina Gamboa Valdez
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

from api import admin_router, advanced_router, manager_router, token_router
from api.dependencies.alloweds import (
    allowed_deployment_action,
    owns_deployment_id,
    owns_domain_id,
)
from api.dependencies.bastion import (
    bastion_domain_verification_required,
    can_use_bastion,
    can_use_bastion_individual_domains,
    domain_has_bastion_target,
)
from api.dependencies.domains import check_domain_kind
from api.dependencies.jwt_token import is_admin
from api.dependencies.storage_pools import (
    check_create_storage_pool_availability,
    check_virt_storage_pool_availability,
)
from api.schemas.common import (
    DeleteResponse,
    ErrorResponse,
    SimpleResponse,
    SimpleResponsePlural,
)
from api.schemas.domains.desktops import (
    AllowedReservablesResponse,
    BastionAuthorizedKeysUpdateRequest,
    BastionDomainsUpdateRequest,
    BastionDomainUpdateRequest,
    BastionDomainVerifyRequest,
    BastionDomainVerifyResponse,
    BulkCreatePersistentDesktopsRequest,
    BulkEditDesktopsRequest,
    CreateDesktopFromMedia,
    CreateDesktopRequest,
    Desktop,
    DesktopBastionResponse,
    DesktopDetailsResponse,
    DesktopEditRequest,
    DesktopFilterParams,
    DesktopGetViewerResponse,
    DesktopImagesResponse,
    DesktopImageType,
    DesktopNetworksResponse,
    DesktopSearchFields,
    DesktopsPaginationResponse,
    DesktopsStopRequest,
    DomainInfoResponse,
    NewNonpersistentDesktopRequest,
    UserDesktopsResponse,
)
from api.services.bastion import BastionService
from api.services.cards import CardService
from api.services.deployments import DeploymentService
from api.services.desktops import DesktopService
from api.services.domains import DomainService
from api.services.error import Error
from fastapi import Depends, Path, Query, Request
from fastapi.responses import JSONResponse, Response

tag = "desktops"


@token_router.post(
    "/item/desktop/new-nonpersistent",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Create (or reuse) a non-persistent desktop",
    description=(
        "Creates a non-persistent desktop from a template. If the user "
        "already has a non-persistent desktop derived from the same "
        "template it is reused (and started if stopped). ``@has_token`` — "
        "quota and allowlist checks are enforced server-side."
    ),
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(check_create_storage_pool_availability)],
)
async def create_nonpersistent_desktop(
    request: Request, data: NewNonpersistentDesktopRequest
):
    try:
        desktop_id = await asyncio.to_thread(
            DesktopService.create_nonpersistent_desktop,
            payload=request.token_payload,
            template_id=data.template_id,
        )
        return JSONResponse(
            content=SimpleResponse(id=desktop_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create non-persistent desktop",
            traceback.format_exc(),
        )


@token_router.post(
    "/item/desktop",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Create a desktop",
    description="Creates a desktop with the given parameters.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(check_create_storage_pool_availability)],
)
async def create_desktop(request: Request, data: CreateDesktopRequest):
    if data.bastion_target:
        await can_use_bastion(request.token_payload)

        if data.bastion_target.domain:
            await can_use_bastion_individual_domains(request.token_payload)
            if bastion_domain_verification_required():
                # The domain cannot be verified when creating a new target
                raise Error(
                    "bad_request",
                    "Cannot set a bastion domain when creating a new desktop",
                    traceback.format_exc(),
                )

    try:
        desktop_id = await asyncio.to_thread(
            DesktopService.create_desktop,
            user_id=request.token_payload["user_id"],
            data=data,
        )
        return JSONResponse(
            content=SimpleResponse(id=desktop_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to create desktop",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/desktop/{desktop_id}",
    response_model=Desktop,
    tags=[tag],
    summary="Get details of a desktop",
    description="Returns a desktop in IsardVDI based on an ID.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_domain_id("desktop_id"))],
)
async def get_desktop(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        desktop = await asyncio.to_thread(DesktopService.get_desktop, desktop_id)
        return JSONResponse(
            content=Desktop(**desktop).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve desktop",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/desktop/{desktop_id}/get-networks",
    response_model=DesktopNetworksResponse,
    tags=[tag],
    summary="Get details of a desktop networks",
    description="Returns the networks information about a IsardVDI desktops based on an ID.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_domain_id("desktop_id"))],
)
async def get_desktop_networks(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        networks = await asyncio.to_thread(
            DesktopService.get_desktop_networks, desktop_id
        )
        return JSONResponse(
            content=DesktopNetworksResponse(networks=networks).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve desktop",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/desktop/{desktop_id}/get-details",
    response_model=DesktopDetailsResponse,
    summary="Get the details of a desktop",
    tags=[tag],
    description="Gets a desktop details based on the desktop ID",
    operation_id="get_desktop_details",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_domain_id("desktop_id"))],
)
async def get_desktop_info(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        info = await asyncio.to_thread(DesktopService.get_desktop_details, desktop_id)
        return JSONResponse(
            content=DesktopDetailsResponse(**info).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise e
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve desktop",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/desktop/{desktop_id}/get-bastion",
    tags=[tag, "bastion"],
    response_model=DesktopBastionResponse,
    summary="Get desktop bastion configuration",
    description="Returns the bastion configuration for a desktop based on the desktop ID",
    operation_id="get_desktop_bastion_legacy",
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
async def get_desktop_bastion(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        bastion = await asyncio.to_thread(
            DesktopService.get_desktop_bastion, desktop_id
        )
        return JSONResponse(
            content=DesktopBastionResponse(**bastion).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve desktop bastion",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/desktop/{desktop_id}/update-bastion-authorized-keys",
    tags=[tag, "bastion"],
    response_model=SimpleResponse,
    summary="Update desktop bastion authorized keys",
    description="Updates the authorized keys for the desktop bastion",
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
async def update_desktop_bastion_authorized_keys(
    request: Request,
    data: BastionAuthorizedKeysUpdateRequest,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        await asyncio.to_thread(
            DesktopService.update_desktop_bastion_authorized_keys,
            desktop_id,
            data,
            request.token_payload["user_id"],
        )
        return JSONResponse(
            content=SimpleResponse(id=desktop_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to update desktop bastion authorized keys",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/desktop/{desktop_id}/extend-timeout",
    response_model=SimpleResponse,
    summary="Extend desktop timeout",
    tags=[tag],
    description="Extend the remaining time before automatic desktop shutdown.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_domain_id("desktop_id"))],
)
async def extend_desktop_timeout(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        await asyncio.to_thread(
            DesktopService.extend_desktop_timeout, request.token_payload, desktop_id
        )
        return JSONResponse(
            content=SimpleResponse(id=desktop_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to extend desktop timeout",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/desktop/{desktop_id}/stop",
    response_model=SimpleResponse,
    summary="Stop a desktop",
    tags=[tag],
    description="Stops a desktop based on the desktop ID",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_domain_id("desktop_id"))],
)
async def stop_desktop(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        await asyncio.to_thread(
            DesktopService.stop_desktop,
            desktop_id,
            user_id=request.token_payload["user_id"],
            request=request,
        )
        return JSONResponse(
            content=SimpleResponse(id=desktop_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to stop desktop {desktop_id}",
            traceback.format_exc(),
        )


@token_router.put(
    "/items/desktops/stop",
    response_model=SimpleResponse,
    summary="Stop all user desktops",
    tags=[tag],
    description="Stops all the desktops from the user",
    responses={500: {"model": ErrorResponse}},
)
async def stop_desktops(desktops_stop_request: DesktopsStopRequest, request: Request):
    try:
        await asyncio.to_thread(
            DesktopService.stop_user_desktops,
            user_id=request.token_payload["user_id"],
            force=desktops_stop_request.force,
            request=request,
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to stop desktops",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/desktop/{desktop_id}/start",
    response_model=SimpleResponse,
    summary="Start a desktop",
    tags=[tag],
    description="Starts a desktop based on the desktop ID",
    responses={
        404: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_domain_id("desktop_id")),
        Depends(check_virt_storage_pool_availability),
    ],
)
async def start_desktop(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        await asyncio.to_thread(
            DesktopService.start_desktop,
            desktop_id,
            user_id=request.token_payload["user_id"],
            request=request,
        )
        return JSONResponse(
            content=SimpleResponse(id=desktop_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to start desktop {desktop_id}",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/desktop/{desktop_id}/update-status",
    response_model=SimpleResponse,
    summary="Updates a desktop status",
    tags=[tag],
    description="Updates the desktop status based on the desktop ID. Mainly used when desktop is Failed",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_domain_id("desktop_id"))],
)
async def update_status_desktop(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        await asyncio.to_thread(DesktopService.desktop_update_status, desktop_id)
        return JSONResponse(
            content=SimpleResponse(id=desktop_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to start desktop {desktop_id}",
            traceback.format_exc(),
        )


@manager_router.put(
    "/item/desktop/{desktop_id}/change-owner/{user_id}",
    response_model=SimpleResponse,
    summary="Change desktop owner",
    tags=[tag],
    description=(
        "Reassigns a persistent desktop to a different user. "
        "``@is_admin_or_manager``. Both ``ownsUserId(user_id)`` and "
        "``ownsDomainId(desktop_id)`` are enforced by the service."
    ),
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def change_desktop_owner(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
    user_id: str = Path(..., description="The ID of the new owner"),
):
    try:
        await asyncio.to_thread(
            DesktopService.change_owner,
            payload=request.token_payload,
            desktop_id=desktop_id,
            new_user_id=user_id,
        )
        return JSONResponse(
            content=SimpleResponse(id=desktop_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to change desktop owner",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/desktop/{desktop_id}/retry",
    response_model=SimpleResponse,
    summary="Retry a Failed desktop",
    tags=[tag],
    description=(
        "Transitions a ``Failed`` desktop back to ``StartingPaused`` so the "
        "engine can validate it can start on a hypervisor again. Ports v3 "
        "``GET /desktop/updating/{desktop_id}``. Ownership is enforced."
    ),
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_domain_id("desktop_id"))],
)
async def retry_failed_desktop(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        result = await asyncio.to_thread(
            DesktopService.retry_failed_desktop,
            desktop_id,
            user_id=request.token_payload["user_id"],
        )
        return JSONResponse(
            content=SimpleResponse(id=result["id"]).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retry desktop {desktop_id}",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/items/desktops/bulk-edit",
    response_model=SimpleResponsePlural,
    summary="Bulk edit multiple desktops",
    tags=[tag],
    description=(
        "Applies a partial desktop update to every desktop in ``ids``. "
        "Ports v3 ``PUT /domain/bulk`` — the request body must contain an "
        "``ids`` list alongside the fields to update. Ownership is "
        "checked per id."
    ),
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def bulk_edit_desktops(request: Request, data: BulkEditDesktopsRequest):
    try:
        ids = data.ids
        update_payload = data.model_dump(exclude_unset=True, exclude={"ids"})

        if "forced_hyp" in update_payload or "favourite_hyp" in update_payload:
            await is_admin(request.token_payload)

        result = await asyncio.to_thread(
            DesktopService.bulk_edit_desktops,
            ids,
            update_payload,
            request.token_payload,
        )
        return JSONResponse(
            content=SimpleResponsePlural(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to bulk edit desktops",
            traceback.format_exc(),
        )


@advanced_router.post(
    "/items/desktops/bulk-create",
    response_model=SimpleResponsePlural,
    summary="Bulk create persistent desktops from a template",
    tags=[tag],
    description=(
        "Creates multiple persistent desktops from a template for a set "
        "of users/groups/categories/roles. Ports v3 ``POST "
        "/persistent_desktop/bulk``. Body requires ``template_id``, "
        "``name``, ``description`` and an ``allowed`` structure "
        "describing the target entities."
    ),
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def bulk_create_persistent_desktops(
    request: Request, data: BulkCreatePersistentDesktopsRequest
):
    try:
        result = await asyncio.to_thread(
            DesktopService.bulk_create_persistent_desktops,
            request.token_payload,
            data.model_dump(),
        )
        return JSONResponse(
            content=SimpleResponsePlural(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to bulk create persistent desktops",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/desktop/{desktop_id}/force-stop",
    response_model=SimpleResponse,
    summary="Force stop a desktop",
    tags=[tag],
    description="Force stops a desktop based on the desktop ID",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_domain_id("desktop_id"))],
)
async def force_stop_desktop(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        await asyncio.to_thread(
            DesktopService.stop_desktop,
            desktop_id,
            user_id=request.token_payload["user_id"],
            force=True,
            request=request,
        )
        return JSONResponse(
            content=SimpleResponse(id=desktop_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to force stop desktop {desktop_id}",
            traceback.format_exc(),
        )


@token_router.delete(
    "/item/desktop/{desktop_id}",
    tags=[tag],
    response_model=DeleteResponse,
    summary="Delete a desktop",
    description="Deletes desktop based on the desktop ID",
    responses={
        200: {"model": DeleteResponse},
        202: {"model": DeleteResponse},
        204: {},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_domain_id("desktop_id"))],
)
async def delete_desktop(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
    permanent: bool = Query(
        False, description="Whether to permanently delete the desktop"
    ),
):
    try:
        tasks = await asyncio.to_thread(
            DesktopService.delete_desktop,
            desktop_id,
            request.token_payload["user_id"],
            permanent=permanent,
        )
        if isinstance(tasks, bool):
            return Response(status_code=204)
        if tasks is None:
            return JSONResponse(
                content=DeleteResponse(
                    message="Item sent to recycle bin",
                    message_code="item.recycled",
                ).model_dump(mode="json"),
                status_code=200,
            )
        return JSONResponse(
            content=DeleteResponse(
                message="Task queued to delete desktop",
                message_code="item.queued",
                tasks_ids=[t["id"] for t in tasks],
            ).model_dump(mode="json"),
            status_code=202,
        )

    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve desktop",
            traceback.format_exc(),
        )


@token_router.get(
    "/items/desktops/get-images",
    tags=[tag],
    response_model=DesktopImagesResponse,
    summary="Get available desktop images",
    description="Returns available desktop images (stock and user cards)",
    operation_id="get_desktop_images",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_desktop_images(
    request: Request,
    image_type: Optional[DesktopImageType] = Query(
        None,
        description="Image type filter: 'stock', 'user', or omit for both.",
    ),
    domain_id: str = Query(None, description="Domain ID for user cards"),
):
    try:
        user_id = request.token_payload["user_id"]

        # Both ``CardService.get_stock_cards`` and ``get_user_cards`` are
        # sync ReQL helpers; calling them straight from this async handler
        # blocks the event loop. Offload via ``asyncio.to_thread`` so
        # concurrent callers don't serialise behind the rdb round-trip.
        if image_type is None:
            stock, user = await asyncio.gather(
                asyncio.to_thread(CardService.get_stock_cards),
                asyncio.to_thread(CardService.get_user_cards, user_id, domain_id),
            )
            images = stock + user
        elif image_type == "stock":
            images = await asyncio.to_thread(CardService.get_stock_cards)
        else:  # "user"
            images = await asyncio.to_thread(
                CardService.get_user_cards, user_id, domain_id
            )

        return JSONResponse(
            content=DesktopImagesResponse(images=images).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve desktop images",
            traceback.format_exc(),
        )


@token_router.delete(
    "/item/desktop/{deployment_id}/{user_id}",
    tags=[tag],
    # Gate deletion to deployment owners/co-owners; no service-level check exists.
    dependencies=[Depends(owns_deployment_id())],
    response_model=DeleteResponse,
    status_code=202,
    summary="Delete user desktops from a deployment",
    description="Deletes all desktops belonging to one user inside a deployment",
    responses={
        202: {"model": DeleteResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_user_deployment_desktops(
    request: Request,
    user_id: str = Path(..., description="The ID of the user"),
    deployment_id: str = Path(..., description="The ID of the deployment"),
):
    try:
        task_ids = await asyncio.to_thread(
            DeploymentService.delete_desktops, user_id, deployment_id, request
        )
        return JSONResponse(
            content=DeleteResponse(
                message="Task to delete desktops queued",
                message_code="item.queued",
                task_ids=task_ids,
            ).model_dump(mode="json"),
            status_code=202,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to delete desktops for user {user_id} in deployment {deployment_id}",
            traceback.format_exc(),
        )


@token_router.get(
    "/items/desktops",
    tags=[tag],
    response_model=UserDesktopsResponse,
    summary="Get user desktops",
    description="Returns a list of all desktops that belong to the user calling the endpoint.",
    operation_id="get_user_desktops",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_user_desktops(request: Request):
    try:
        user_id = request.token_payload["user_id"]
        user_desktops = await asyncio.to_thread(
            DesktopService.get_user_desktops, user_id
        )
        return JSONResponse(
            content=UserDesktopsResponse(desktops=user_desktops).model_dump(
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
            "Failed to retrieve user desktops",
            traceback.format_exc(),
        )


# TODO: For now pagination won't be used since the user load is not as high. Although this works, it is not needed yet.
@token_router.get(
    "/items/paginated/desktops",
    tags=[tag],
    response_model=DesktopsPaginationResponse,
    summary="Get user desktops",
    description="Returns a list of all desktops that belong to the user calling the endpoint.",
    operation_id="get_user_desktops_paginated",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_user_desktops(
    request: Request,
    start_after: int = Query(
        default=None,
        description="Start the retrieval after the given accessed. If not provided, starts from the beginning.",
    ),
    page_size: int = Query(
        default=10,
        description="Number of desktops to return. Default is 10. The given value will be multiplied by 5 in order to preload more desktops for the user.",
        ge=1,
        le=50,
    ),
    sort_field: Literal["accessed"] = Query(
        default="accessed",
        description="Field to sort the desktops by. Only 'accessed' is supported.",
    ),
    sort_order: Literal["desc", "asc"] = Query(
        default="desc",
        description="Order to sort the desktops by. Default is 'desc'. Can be 'asc' or 'desc'.",
    ),
    search: str = Query(
        default=None,
        description="Search term to filter desktops by name or description. If provided, search_field must also be provided.",
    ),
    search_field: Optional[DesktopSearchFields] = Query(
        default=None,
        description="Field to search in. If not provided, no search is performed.",
    ),
    filters: DesktopFilterParams = Depends(),
):
    try:
        if search and not search_field:
            raise Error(
                "bad_request",
                "search_field must be provided when search is set",
                traceback.format_exc(),
            )
        if search_field and not search:
            raise Error(
                "bad_request",
                "search must be provided when search_field is set",
                traceback.format_exc(),
            )
        filter_dict = filters.dict(exclude_none=True)
        user_desktops = await asyncio.to_thread(
            DesktopService.get_user_desktops_paginated,
            user_id=request.token_payload["user_id"],
            start_after=start_after,
            page_size=page_size,
            sort_field=sort_field,
            sort_order=sort_order,
            search=search,
            search_field=search_field,
            filters=filter_dict,
        )
        return JSONResponse(
            content=DesktopsPaginationResponse(**user_desktops).model_dump(mode="json"),
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


@admin_router.get(
    "/admin/items/desktops",
    tags=[tag],
    response_model=DesktopsPaginationResponse,
    summary="Get all desktops",
    description="Returns a list of all desktops in the system.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_all_desktops(
    request: Request,
    start_after: int = None,
    page_size: int = 10,
    sort_field: str = "accessed",
    sort_order: str = "desc",
    search: str = None,
    search_field: Optional[DesktopSearchFields] = None,
    # filters: DesktopFilterParams = Depends(), TODO: Implement filters
):
    try:
        if search and not search_field:
            raise Error(
                "bad_request",
                "search_field must be provided when search is set",
                traceback.format_exc(),
            )
        if search_field and not search:
            raise Error(
                "bad_request",
                "search must be provided when search_field is set",
                traceback.format_exc(),
            )
        # filter_dict = filters.dict(exclude_none=True)
        desktops = await asyncio.to_thread(
            DesktopService.get_all_desktops,
            start_after=start_after,
            page_size=page_size,
            sort_field=sort_field,
            sort_order=sort_order,
            search=search,
            search_field=search_field,
            # filters=filter_dict,
        )
        return JSONResponse(
            content=DesktopsPaginationResponse(**desktops).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve all desktops",
            traceback.format_exc(),
        )


@token_router.get(
    "/items/domains/get-allowed-reservables",
    tags=[tag],
    response_model=AllowedReservablesResponse,
    summary="Get allowed reservables for the calling user",
    description=(
        "Returns the reservable vGPUs visible to the calling user, "
        "filtered by category/group/role/user permissions."
    ),
)
async def get_domains_allowed_reservables(request: Request):
    try:
        vgpus = await asyncio.to_thread(
            DesktopService.get_user_allowed_reservables, request.token_payload
        )
        return JSONResponse(
            content=AllowedReservablesResponse(vgpus=vgpus).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve allowed reservables",
            traceback.format_exc(),
        )


@token_router.post(
    "/item/desktop/from-media",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Create a desktop from media",
    status_code=201,
    description=(
        "Creates a desktop from media with the given parameters. Available "
        "to any logged-in user; quota is enforced server-side."
    ),
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_desktop_from_media(request: Request, data: CreateDesktopFromMedia):
    try:
        desktop_id = await asyncio.to_thread(
            DesktopService.create_from_media,
            user_id=request.token_payload["user_id"],
            data=data,
        )
        return JSONResponse(
            content=SimpleResponse(id=desktop_id).model_dump(mode="json"),
            status_code=201,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to create desktop from media",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/desktop/{desktop_id}/get-info",
    tags=[tag],
    response_model=DomainInfoResponse,
    summary="Get desktop information",
    description="Returns detailed information about a specific desktop.",
    operation_id="get_desktop_info",
    dependencies=[Depends(owns_domain_id("desktop_id"))],
)
async def get_desktop_info(
    request: Request,
    desktop_id: str,
):

    try:
        desktop_data = await asyncio.to_thread(
            DomainService.get_domain_info, desktop_id, request.token_payload
        )

        try:
            bastion_target = await asyncio.to_thread(
                DesktopService.get_desktop_bastion, desktop_id
            )
        except Error:
            bastion_target = None

        if bastion_target:
            # Merge global bastion config so the modal can compose SSH/URL links.
            bastion_config = await asyncio.to_thread(
                BastionService.get_admin_bastion_config
            )
            bastion_target["bastion_domain"] = bastion_config.get("bastion_domain")
            bastion_target["ssh_port"] = bastion_config.get("bastion_ssh_port")

        desktop_data["bastion_target"] = bastion_target

        return JSONResponse(
            content=DomainInfoResponse(**desktop_data).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve desktop information",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/desktop/{desktop_id}/edit",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Edit a desktop",
    description="Updates a desktop with the given parameters.",
    dependencies=[
        Depends(owns_domain_id("desktop_id")),
        Depends(check_domain_kind("desktop_id", "desktop")),
    ],
)
async def edit_desktop(
    request: Request,
    desktop_id: str,
    data: DesktopEditRequest,
):
    if data.bastion_target:
        await can_use_bastion(request.token_payload)

        if data.bastion_target.domain:
            await can_use_bastion_individual_domains(request.token_payload)
            if bastion_domain_verification_required() and not domain_has_bastion_target(
                desktop_id
            ):
                # The domain cannot be verified when creating a new target
                raise Error(
                    "bad_request",
                    "Cannot set a bastion domain when the domain has no bastion target",
                    traceback.format_exc(),
                )

    try:
        payload = data.model_dump(exclude_unset=True)
        if data.image is not None and getattr(data.image, "file", None) is not None:
            payload["image"]["file"] = data.image.file.model_dump(exclude_unset=True)

        if "forced_hyp" in payload or "favourite_hyp" in payload:
            await is_admin(request.token_payload)

        await asyncio.to_thread(
            DesktopService.edit_desktop,
            desktop_id,
            payload,
            request.token_payload,
        )
        return JSONResponse(
            content=SimpleResponse(id=desktop_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to edit desktop {desktop_id}",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/desktop/{desktop_id}/get-viewer/{viewer_type}",
    tags=[tag],
    response_model=DesktopGetViewerResponse,
    summary="Get desktop viewer connection string",
    description="Returns the connection string for a specific viewer type for the given desktop.",
    operation_id="get_desktop_viewer_by_type",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_domain_id("desktop_id"))],
)
async def get_desktop_viewer(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
    viewer_type: Literal[
        "browser-vnc", "file-spice", "file-rdpgw", "file-rdpvpn", "browser-rdp"
    ] = Path(..., description="The type of viewer to get the connection string for"),
):
    try:
        connection_string = await asyncio.to_thread(
            DesktopService.get_desktop_viewer,
            request.token_payload["user_id"],
            desktop_id,
            viewer_type,
            request.token_payload["role_id"] == "admin",
            request,
        )
        # Log here, not in the @cached service: cache hits skip the body and would drop the audit entry.
        from isardvdi_common.helpers.logging import Logging

        Logging.logs_domain_event_viewer(
            desktop_id,
            request.token_payload["user_id"],
            viewer_type,
            user_request=request,
        )
        return JSONResponse(
            content=DesktopGetViewerResponse(**connection_string).model_dump(
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
            f"Failed to retrieve desktop viewer connection string",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/desktop/{desktop_id}/recreate",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Recreate desktop disk",
    description="Recreates the desktop disk from its parent template. Will delete the desktop storage and create a new one.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_domain_id("desktop_id")),
        Depends(check_domain_kind("desktop_id", "desktop")),
        Depends(allowed_deployment_action("recreate")),
    ],
)
async def recreate_desktop(
    request: Request,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        await asyncio.to_thread(
            DesktopService.recreate_desktop, request.token_payload, desktop_id
        )
        return JSONResponse(
            content=SimpleResponse(id=desktop_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to recreate desktop",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/desktop/{desktop_id}/update-bastion-domain",
    tags=[tag, "bastion"],
    response_model=SimpleResponse,
    summary="Update desktop bastion domain",
    description="Updates the domain name for the desktop's bastion target.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_domain_id("desktop_id")),
        Depends(can_use_bastion_individual_domains),
    ],
)
async def update_desktop_bastion_domain(
    request: Request,
    data: BastionDomainUpdateRequest,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        await asyncio.to_thread(
            DesktopService.update_desktop_bastion_domain, desktop_id, data.domain_name
        )
        return JSONResponse(
            content=SimpleResponse(id=desktop_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update desktop bastion domain",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/desktop/{desktop_id}/update-bastion-domains",
    tags=[tag, "bastion"],
    response_model=SimpleResponse,
    summary="Update desktop bastion domains (bulk)",
    description=(
        "Replaces the list of individual bastion domains for a desktop. "
        "Up to 10 domains are allowed; newly added domains are "
        "DNS-verified against the category's CNAME before being saved."
    ),
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_domain_id("desktop_id")),
        Depends(can_use_bastion_individual_domains),
    ],
)
async def update_desktop_bastion_domains(
    request: Request,
    data: BastionDomainsUpdateRequest,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        await asyncio.to_thread(
            DesktopService.update_desktop_bastion_domains,
            payload=request.token_payload,
            desktop_id=desktop_id,
            domains=data.domains,
        )
        return JSONResponse(
            content=SimpleResponse(id=desktop_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update desktop bastion domains",
            traceback.format_exc(),
        )


@token_router.post(
    "/item/desktop/{desktop_id}/verify-bastion-domain",
    tags=[tag, "bastion"],
    response_model=BastionDomainVerifyResponse,
    summary="DNS-verify a single bastion domain without saving",
    description=(
        "Checks that the DNS CNAME for the given candidate domain "
        "resolves to the expected target for this desktop's bastion "
        "category."
    ),
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_domain_id("desktop_id")),
        Depends(can_use_bastion_individual_domains),
    ],
)
async def verify_desktop_bastion_domain(
    request: Request,
    data: BastionDomainVerifyRequest,
    desktop_id: str = Path(..., description="The ID of the desktop"),
):
    try:
        result = await asyncio.to_thread(
            DesktopService.verify_bastion_domain,
            payload=request.token_payload,
            desktop_id=desktop_id,
            domain=data.domain,
        )
        return JSONResponse(
            content=BastionDomainVerifyResponse(**result).model_dump(mode="json"),
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
