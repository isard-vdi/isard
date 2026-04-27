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

from api import advanced_router, manager_router, token_router
from api.dependencies.alloweds import (
    is_allowed_deployment_id_and_user_id,
    is_allowed_template_ids_body,
    owns_deployment_id,
    owns_domain_id,
)
from api.dependencies.domains import (
    deployment_has_no_started_desktops,
    tag_desktop_ids_belong_to_deployment,
)
from api.dependencies.quotas import can_create_deployment
from api.dependencies.storage_pools import check_create_storage_pool_availability
from api.schemas.common import (
    DeleteResponse,
    EmptyResponse,
    ErrorResponse,
    SimpleResponse,
)
from api.schemas.deployments import (
    BulkDeleteDeploymentsErrorResponse,
    BulkDeleteDeploymentsRequest,
    CheckQuotaRequest,
    CoOwnersRequest,
    CoOwnersResponse,
    CreateDeploymentRequest,
    DeploymentCsvResponse,
    DeploymentEditData,
    DeploymentEditRequest,
    DeploymentEditUsersRequest,
    DeploymentResponse,
    OwnedDeploymentsResponse,
    SharedDeploymentsResponse,
    UserDeploymentResponse,
)
from api.schemas.domains.desktops import DesktopDetailsResponse
from api.services.deployments import DeploymentService
from api.services.error import Error
from fastapi import Depends, Query, Request, Security
from fastapi.responses import JSONResponse, Response
from fastapi.security.api_key import APIKeyHeader
from isardvdi_common.models.deployment import Deployment as RethinkDeployment

tag = "deployments"


@advanced_router.get(
    "/items/deployments",
    tags=[tag],
    summary="Get all owned deployments",
    response_model=OwnedDeploymentsResponse,
    description="Returns all the deployments that the user in the payload is owner or co-owner.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_all_deployments(request: Request):
    try:
        return JSONResponse(
            content=OwnedDeploymentsResponse(
                deployments=DeploymentService.get_owned_deployments(
                    request.token_payload
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
            f"Failed to retrieve deployments",
            traceback.format_exc(),
        )


# NOTE: /item/deployment/check-quota MUST be declared before
# /item/deployment/{deployment_id} — otherwise the catch-all matches
# "check-quota" as the deployment_id and the literal is unreachable.
@advanced_router.get(
    "/item/deployment/check-quota",
    tags=[tag],
    summary="Check deployment creation quota",
    description="Checks if the user has enough quota to create a new deployment.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def check_deployment_quota_get(request: Request):
    try:
        DeploymentService.check_quota(request.token_payload["user_id"])
        return JSONResponse(content={}, status_code=200)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to check deployment quota",
            traceback.format_exc(),
        )


@advanced_router.post(
    "/item/deployment/check-quota",
    tags=[tag],
    summary="Check deployment creation quota with allowed users",
    description="Checks if the user has enough quota to create a new deployment with the given allowed users.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def check_deployment_quota_post(
    request: Request,
    data: CheckQuotaRequest,
):
    try:
        users = []
        if data.allowed:
            users = DeploymentService.get_selected_users(
                request.token_payload, data.allowed.model_dump()
            )
        DeploymentService.check_quota(request.token_payload["user_id"], users)
        return JSONResponse(content={}, status_code=200)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to check deployment quota",
            traceback.format_exc(),
        )


@advanced_router.get(
    "/item/deployment/{deployment_id}",
    tags=[tag],
    response_model=DeploymentResponse,
    summary="Get details of a deployment",
    description="Returns a deployment based on an ID.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_deployment_id)],
)
async def get_deployment(
    deployment_id: str,
    request: Request,
):
    try:
        return JSONResponse(
            content=DeploymentResponse(
                **DeploymentService.get_deployment(deployment_id)
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve deployment",
            traceback.format_exc(),
        )


@advanced_router.delete(
    "/item/deployment/{deployment_id}",
    tags=[tag],
    summary="Delete a deployment",
    description="Deletes a deployment and all it's desktops permanently.",
    response_model=DeleteResponse,
    responses={
        200: {"model": DeleteResponse},
        202: {"model": DeleteResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_deployment_id(check_co_owner=False)),
        Depends(deployment_has_no_started_desktops),
    ],
)
async def delete_deployment(
    request: Request,
    deployment_id: str,
    permanent: bool = Query(
        False, description="Whether to permanently delete the desktop"
    ),
):
    try:
        tasks = DeploymentService.delete_deployment(
            deployment_id, request.token_payload["user_id"], permanent=permanent
        )
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
                    message="Task queued to delete deployment",
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
            f"Failed to delete deployment {deployment_id}",
            traceback.format_exc(),
        )


@advanced_router.post(
    "/item/deployment",
    tags=[tag],
    summary="Create a new deployment",
    description="Creates a new deployment with the provided data.",
    response_model=SimpleResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(check_create_storage_pool_availability),
        Depends(can_create_deployment),
        Depends(is_allowed_template_ids_body()),
    ],
)
async def create_deployment(
    request: Request,
    data: CreateDeploymentRequest,
):
    return JSONResponse(
        content=SimpleResponse(
            id=DeploymentService.create_deployment(
                data.model_dump(exclude_unset=True),
                request.token_payload,
            )
        ).model_dump(mode="json"),
        status_code=200,
    )


@advanced_router.put(
    "/item/deployment/{deployment_id}/stop",
    tags=[tag],
    summary="Stop all desktops from a deployment",
    description="Stop all started desktops from a deployment.",
    responses={
        204: {"description": "Desktops stopped successfully"},
        404: {"model": ErrorResponse, "description": "No dekstops found in deployment"},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_deployment_id()),
    ],
)
async def stop_all_desktops_in_deployment(
    request: Request,
    deployment_id: str,
):
    try:
        DeploymentService.stop_all_desktops(deployment_id)
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to stop desktops for deployment {deployment_id}",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/item/deployment/{deployment_id}/user/{user_id}/stop",
    tags=[tag],
    summary="Stop all desktops from a user in a deployment",
    description="Stop all started desktops from a user in a deployment.",
    responses={
        204: {"description": "Desktops stopped successfully"},
        404: {"model": ErrorResponse, "description": "No dekstops found for user"},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_deployment_id()),
    ],
)
async def stop_user_desktops_in_deployment(
    request: Request,
    deployment_id: str,
    user_id: str,
):
    try:
        DeploymentService.stop_user_desktops(deployment_id, user_id)
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to stop desktops for user {user_id} in deployment {deployment_id}",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/item/deployment/{deployment_id}/toggle-visibility",
    tags=[tag],
    summary="Toggle deployment visibility",
    response_model=SimpleResponse,
    description="Toggles the visibility of the deployment with the given ID.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def toggle_deployment_visibility(
    deployment_id: str,
    request: Request,
    owns_deployment_id=Depends(owns_deployment_id()),
):
    try:
        # Vue 2 sends {"stop_started_domains": bool} so the user can choose
        # whether hiding a deployment also stops its Started desktops.
        # Request body is optional (Vue 3 may PUT with no body); default to
        # True to match the apiv3 contract.
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        stop_started_domains = bool(body.get("stop_started_domains", True))
        DeploymentService.toggle_visibility(deployment_id, stop_started_domains)
        return JSONResponse(
            content=SimpleResponse(id=deployment_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to update deployment visibility",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/item/deployment/{deployment_id}/edit",
    tags=[tag],
    summary="Edit an existing deployment. Designed to be used via form",
    description="Edits an existing deployment with the provided data.",
    response_model=SimpleResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_deployment_id()),
        Depends(deployment_has_no_started_desktops),
        Depends(is_allowed_template_ids_body("desktops_to_create")),
    ],
)
async def edit_deployment(
    request: Request,
    deployment_id: str,
    deployment_data: DeploymentEditRequest,
):
    try:
        tag_desktop_ids_belong_to_deployment(
            deployment_id, deployment_data.model_dump(mode="json")["desktops_to_delete"]
        )
        tag_desktop_ids_belong_to_deployment(
            deployment_id,
            [
                dktp["tag_desktop_id"]
                for dktp in deployment_data.model_dump(mode="json")["desktops_to_edit"]
            ],
        )

        DeploymentService.update_deployment(
            payload=request.token_payload,
            deployment_id=deployment_id,
            deployment_data=deployment_data.model_dump(mode="json", exclude_unset=True),
        )
        return JSONResponse(
            content=SimpleResponse(id=deployment_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to update deployment {deployment_id}",
            traceback.format_exc(),
        )


@advanced_router.get(
    "/item/deployment/{deployment_id}/download-csv",
    tags=[tag],
    summary="Export direct viewer URLs as CSV",
    description="Generates a CSV file with direct viewer URLs for all desktops in the deployment",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_deployment_csv(
    deployment_id: str,
    request: Request,
    regenerate: bool = Query(
        False, description="Regenerate all direct viewer links before exporting"
    ),
    owns_deployment_id=Depends(owns_deployment_id()),
):
    csv_content = DeploymentService.direct_viewer_csv(deployment_id, regenerate)
    try:
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={deployment_id}_direct_viewer.csv"
            },
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to generate CSV",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/item/deployment/{deployment_id}/recreate",
    tags=[tag],
    summary="Recreate a deployment",
    response_model=SimpleResponse,
    description="Recreates a deployment by deleting all desktops and creating them again with current parameters.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def recreate_deployment(
    deployment_id: str,
    request: Request,
    owns_deployment_id=Depends(owns_deployment_id()),
):
    try:
        # ``recreate_desktops`` loops over every desktop in the
        # deployment doing sync ``RethinkDomain.delete()`` per item
        # plus a recreate dispatch. Offload to a worker thread so
        # the event loop stays free for SocketIO and concurrent
        # HTTP traffic during a multi-desktop recreate.
        await asyncio.to_thread(
            DeploymentService.recreate_desktops,
            request.token_payload,
            deployment_id,
        )
        return JSONResponse(
            content=SimpleResponse(id=deployment_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to recreate deployment",
            traceback.format_exc(),
        )


@token_router.get(
    "/items/deployments/get-shared",
    tags=[tag],
    summary="Get all shared deployments",
    response_model=SharedDeploymentsResponse,
    description="Returns all the deployments shared to the user in payload.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_all_shared_deployments(request: Request):
    try:
        return JSONResponse(
            content=SharedDeploymentsResponse(
                deployments=DeploymentService.get_shared_deployments(
                    request.token_payload
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
            f"Failed to get deployments",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/deployment/{deployment_id}/desktops/user/{user_id}",
    tags=[tag],
    summary="Get all desktops in a deployment for a user",
    response_model=UserDeploymentResponse,
    description="Returns all desktops in a deployment for a specific user.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(is_allowed_deployment_id_and_user_id)],
)
async def get_deployment_user_desktops(
    deployment_id: str,
    user_id: str,
    request: Request,
):
    """
    Get all desktops in a deployment for a specific user.
    """
    try:
        return JSONResponse(
            content=UserDeploymentResponse(
                **DeploymentService.get_deployment_user_desktops(deployment_id, user_id)
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve desktops for user in deployment {deployment_id}",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/deployment/{deployment_id}/desktops/user/{user_id}/detail",
    tags=[tag],
    summary="Get desktop details in a deployment for a user",
    response_model=list[DesktopDetailsResponse],
    description="Returns the hardware, access, and configuration details of each desktop "
    "in a deployment for a specific user.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(is_allowed_deployment_id_and_user_id)],
)
async def get_deployment_user_desktops_detail(
    deployment_id: str,
    user_id: str,
    request: Request,
):
    try:
        return JSONResponse(
            content=[
                DesktopDetailsResponse(**d).model_dump(mode="json")
                for d in DeploymentService.get_deployment_user_desktops_detail(
                    deployment_id, user_id
                )
            ],
            status_code=200,
        )
    except Error as e:
        raise e
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve desktop details for user in deployment {deployment_id}",
            traceback.format_exc(),
        )


@advanced_router.get(
    "/item/deployment/{deployment_id}/videowall",
    tags=[tag],
    summary="Get deployment with videowall support",
    description="Returns a deployment with its desktops for videowall (lab) display.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_deployment_id())],
)
async def get_deployment_videowall(
    deployment_id: str,
    request: Request,
):
    try:
        return JSONResponse(
            content=DeploymentService.get_deployment_videowall(deployment_id),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve deployment videowall",
            traceback.format_exc(),
        )


@advanced_router.delete(
    "/items/deployments",
    tags=[tag],
    summary="Bulk delete deployments",
    description="Deletes multiple deployments. Optionally permanently.",
    responses={
        200: {"description": "Deployments queued for deletion"},
        428: {"model": BulkDeleteDeploymentsErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def bulk_delete_deployments(
    request: Request,
    data: BulkDeleteDeploymentsRequest,
):
    try:
        exceptions = []
        for d_id in data.ids:
            try:
                from isardvdi_common.helpers.helpers import Helpers

                Helpers.owns_deployment_id(
                    payload=request.token_payload,
                    deployment_id=d_id,
                    check_co_owner=False,
                )
                DeploymentService.check_desktops_started(d_id)
            except Error:
                raise
            except Exception as e:
                exceptions.append(str(e))

        if exceptions:
            return JSONResponse(
                content=BulkDeleteDeploymentsErrorResponse(
                    exceptions=exceptions
                ).model_dump(mode="json"),
                status_code=428,
            )

        DeploymentService.bulk_delete_deployments(
            data.ids, request.token_payload["user_id"], data.permanent
        )
        return JSONResponse(content={}, status_code=200)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to bulk delete deployments",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/item/deployment/{deployment_id}/start",
    tags=[tag],
    summary="Start all desktops in a deployment",
    description="Start all stopped desktops in a deployment.",
    responses={
        204: {"description": "Desktops started successfully"},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_deployment_id())],
)
async def start_all_desktops_in_deployment(
    request: Request,
    deployment_id: str,
):
    try:
        DeploymentService.start_all_desktops(deployment_id)
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to start desktops for deployment {deployment_id}",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/item/deployment/{deployment_id}/domain/{domain_id}/toggle-visibility",
    tags=[tag],
    summary="Toggle individual domain visibility",
    description="Toggles the visibility of a specific domain within a deployment.",
    response_model=SimpleResponse,
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_deployment_id())],
)
async def toggle_domain_visibility(
    deployment_id: str,
    domain_id: str,
    request: Request,
):
    try:
        DeploymentService.toggle_domain_visibility(domain_id)
        return JSONResponse(
            content=SimpleResponse(id=domain_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to toggle domain visibility",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/item/desktop/{desktop_id}/toggle-deployment-visibility",
    tags=[tag],
    summary="Toggle deployment domain visibility (by desktop id)",
    description=(
        "Toggles the ``tag_visible`` flag of a deployment desktop, "
        "identified by the desktop id alone. ``@is_not_user`` — "
        "doesn't require the deployment id in the path. Use the "
        "sibling route with the deployment id when the caller has "
        "it at hand."
    ),
    response_model=SimpleResponse,
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_domain_id("desktop_id"))],
)
async def toggle_desktop_deployment_visibility(
    desktop_id: str,
    request: Request,
):
    try:
        DeploymentService.toggle_domain_visibility(desktop_id)
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
            f"Failed to toggle deployment domain visibility",
            traceback.format_exc(),
        )


@advanced_router.get(
    "/item/deployment/{deployment_id}/hardware",
    tags=[tag],
    summary="Get deployment hardware details",
    description="Returns the hardware configuration details of a deployment.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_deployment_id())],
)
async def get_deployment_hardware(
    deployment_id: str,
    request: Request,
):
    try:
        return JSONResponse(
            content=DeploymentService.get_deployment_hardware(deployment_id),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve deployment hardware",
            traceback.format_exc(),
        )


@advanced_router.get(
    "/item/deployment/{deployment_id}/info",
    tags=[tag],
    summary="Get deployment info with quota limits",
    description="Returns deployment info with hardware limited by user quota.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_deployment_id())],
)
async def get_deployment_info(
    deployment_id: str,
    request: Request,
):
    try:
        return JSONResponse(
            content=DeploymentService.get_deployment_info(
                deployment_id, request.token_payload
            ),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve deployment info",
            traceback.format_exc(),
        )


@advanced_router.get(
    "/item/deployment/{deployment_id}/co-owners",
    tags=[tag],
    summary="Get deployment co-owners",
    description="Returns the list of co-owners of a deployment.",
    response_model=CoOwnersResponse,
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_deployment_id())],
)
async def get_deployment_co_owners(
    deployment_id: str,
    request: Request,
):
    try:
        return JSONResponse(
            content=CoOwnersResponse(
                **DeploymentService.get_co_owners(deployment_id)
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve deployment co-owners",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/item/deployment/{deployment_id}/co-owners",
    tags=[tag],
    summary="Update deployment co-owners",
    description="Updates the list of co-owners of a deployment.",
    response_model=SimpleResponse,
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_deployment_id(check_co_owner=False))],
)
async def update_deployment_co_owners(
    deployment_id: str,
    request: Request,
    data: CoOwnersRequest,
):
    try:
        DeploymentService.update_co_owners(deployment_id, data.co_owners)
        return JSONResponse(
            content=SimpleResponse(id=deployment_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to update deployment co-owners",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/item/deployment/{deployment_id}/edit-users",
    tags=[tag],
    summary="Edit deployment allowed users",
    description="Updates the allowed users and groups for a deployment. "
    "Removes desktops for users no longer allowed and recreates for new users.",
    response_model=EmptyResponse,
    responses={
        404: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_deployment_id()),
        Depends(deployment_has_no_started_desktops),
    ],
)
async def edit_deployment_users(
    request: Request,
    deployment_id: str,
    data: DeploymentEditUsersRequest,
):
    try:
        DeploymentService.edit_deployment_users(
            request.token_payload, deployment_id, data.allowed
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
            f"Failed to edit deployment users",
            traceback.format_exc(),
        )


@manager_router.put(
    "/item/deployment/{deployment_id}/change-owner/{user_id}",
    tags=[tag],
    summary="Change deployment owner",
    description="Changes the owner of a deployment to a different user.",
    response_model=SimpleResponse,
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_deployment_id(check_co_owner=False))],
)
async def change_deployment_owner(
    deployment_id: str,
    user_id: str,
    request: Request,
):
    try:
        DeploymentService.change_owner(request.token_payload, deployment_id, user_id)
        return JSONResponse(
            content=SimpleResponse(id=deployment_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to change deployment owner",
            traceback.format_exc(),
        )


@advanced_router.get(
    "/item/deployment/{deployment_id}/permissions",
    tags=[tag],
    summary="Get deployment permissions",
    description="Returns the permissions configured for a deployment.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_deployment_id())],
)
async def get_deployment_permissions(
    deployment_id: str,
    request: Request,
):
    try:
        return JSONResponse(
            content=DeploymentService.get_permissions(deployment_id),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve deployment permissions",
            traceback.format_exc(),
        )
