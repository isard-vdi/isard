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


import traceback
from typing import Literal, Optional

from api import admin_router, advanced_router, manager_router, token_router
from api.dependencies.alloweds import allowed_deployment_action, owns_domain_id
from api.dependencies.bastion import (
    bastion_domain_verification_required,
    can_use_bastion,
    can_use_bastion_individual_domains,
    domain_has_bastion_target,
)
from api.dependencies.domains import check_domain_kind
from api.dependencies.storage_pools import (
    check_create_storage_pool_availability,
    check_virt_storage_pool_availability,
)
from api.schemas.common import (
    DeleteResponse,
    EmptyResponse,
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
        desktop_id = DesktopService.create_nonpersistent_desktop(
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
        desktop_id = DesktopService.create_desktop(
            user_id=request.token_payload["user_id"], data=data
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
        desktop = DesktopService.get_desktop(desktop_id)
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
        networks = DesktopService.get_desktop_networks(desktop_id)
        return JSONResponse(
            content=DesktopNetworksResponse(
                networks=networks,
            ).model_dump(mode="json"),
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
        info = DesktopService.get_desktop_details(desktop_id)
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
        bastion = DesktopService.get_desktop_bastion(desktop_id)
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
        DesktopService.update_desktop_bastion_authorized_keys(desktop_id, data)
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
        DesktopService.extend_desktop_timeout(request.token_payload, desktop_id)
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
        DesktopService.stop_desktop(
            desktop_id, user_id=request.token_payload["user_id"]
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
        DesktopService.stop_user_desktops(
            user_id=request.token_payload["user_id"], force=desktops_stop_request.force
        )
        return JSONResponse(
            content=EmptyResponse().model_dump(mode="json"),
            status_code=200,
        )
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
        DesktopService.start_desktop(
            desktop_id, user_id=request.token_payload["user_id"], request=request
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
        DesktopService.desktop_update_status(desktop_id)
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
        DesktopService.change_owner(
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
        result = DesktopService.retry_failed_desktop(
            desktop_id, user_id=request.token_payload["user_id"]
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
        # Pydantic ``model_dump`` keeps unknown fields too because the
        # schema is configured with ``extra = "allow"``.
        update_payload = data.model_dump(exclude_none=True, exclude={"ids"})
        result = DesktopService.bulk_edit_desktops(
            ids, update_payload, request.token_payload
        )
        return JSONResponse(content=result, status_code=200)
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
        result = DesktopService.bulk_create_persistent_desktops(
            request.token_payload, data.model_dump()
        )
        return JSONResponse(content=result, status_code=200)
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
        DesktopService.stop_desktop(
            desktop_id, user_id=request.token_payload["user_id"], force=True
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
        tasks = DesktopService.delete_desktop(
            desktop_id, request.token_payload["user_id"], permanent=permanent
        )
        if isinstance(tasks, bool):
            return Response(status_code=204)
        else:
            if tasks is None:
                return JSONResponse(
                    content=DeleteResponse(
                        message="Item sent to recycle bin", message_code="item.recycled"
                    ).model_dump(mode="json"),
                    status_code=200,
                )
            else:
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
    desktop_id: str = Query(None, description="Desktop ID for user cards"),
):
    try:
        user_id = request.token_payload["user_id"]

        if image_type in (None, "user") and not desktop_id:
            raise Error(
                "bad_request",
                "desktop_id is required when image_type is 'user' or omitted (both).",
            )

        image_strategies = {
            None: lambda: CardService.get_stock_cards()
            + CardService.get_user_cards(user_id, desktop_id),
            "stock": lambda: CardService.get_stock_cards(),
            "user": lambda: CardService.get_user_cards(user_id, desktop_id),
        }

        images = image_strategies[image_type]()

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
    response_model=DeleteResponse,
    summary="Delete user desktops from a deployment",
    description="Deletes all desktops belonging to one user inside a deployment",
    responses={
        200: {"model": DeleteResponse},
        202: {"model": DeleteResponse},
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
        task_ids = DeploymentService.delete_desktops(user_id, deployment_id, request)
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
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_user_desktops(request: Request):
    try:
        user_id = request.token_payload["user_id"]
        user_desktops = DesktopService.get_user_desktops(user_id)
        return JSONResponse(
            content=UserDesktopsResponse(
                desktops=user_desktops,
            ).model_dump(mode="json"),
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
    sort_field: str = Query(
        default="accessed",
        description="Field to sort the desktops by. Default is 'accessed'.",
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
        user_desktops = DesktopService.get_user_desktops_paginated(
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
        desktops = DesktopService.get_all_desktops(
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
        vgpus = DesktopService.get_user_allowed_reservables(request.token_payload)
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
        desktop_id = DesktopService.create_from_media(
            user_id=request.token_payload["user_id"], data=data
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
    dependencies=[Depends(owns_domain_id("desktop_id"))],
)
async def get_desktop_info(
    request: Request,
    desktop_id: str,
):

    try:
        desktop_data = DomainService.get_domain_info(desktop_id, request.token_payload)

        try:
            desktop_data["bastion_target"] = DesktopService.get_desktop_bastion(
                desktop_id
            )
        except Error:
            desktop_data["bastion_target"] = None

        return JSONResponse(
            content=desktop_data,
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve template information",
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
        DesktopService.edit_desktop(
            desktop_id, data.model_dump(exclude_unset=True), request.token_payload
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
        connection_string = DesktopService.get_desktop_viewer(
            request.token_payload["user_id"],
            desktop_id,
            viewer_type,
            request.token_payload["role_id"] == "admin",
            request,
        )
        return JSONResponse(
            content=DesktopGetViewerResponse(**connection_string).model_dump(
                mode="json", exclude_unset=True
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
        DesktopService.recreate_desktop(request.token_payload, desktop_id)
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
        DesktopService.update_desktop_bastion_domain(desktop_id, data.domain_name)
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
        DesktopService.update_desktop_bastion_domains(
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
        result = DesktopService.verify_bastion_domain(
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
