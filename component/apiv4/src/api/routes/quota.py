import asyncio
import traceback
from typing import Literal

from api import advanced_router, manager_router, token_router
from api.dependencies.quotas import (
    can_create_deployment,
    can_create_desktop,
    can_create_media,
    can_create_template,
)
from api.schemas.common import ErrorResponse
from api.schemas.quota import AdminQuotaResponse
from api.services.error import Error
from api.services.quota import QuotaService
from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response

tag = "quota"


@manager_router.get(
    "/admin/quota/{kind}",
    tags=[tag],
    response_model=AdminQuotaResponse,
    summary="Get max quota / limits for a user, category or group",
    description=(
        "Returns the current quota and limits dict for the caller's own "
        "``user``, ``category`` or ``group`` entity. Admin/manager only. "
        "Use the ``/admin/quota/{kind}/{item_id}`` variant to target a "
        "specific entity by id. ``@is_admin_or_manager``."
    ),
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_quota_by_kind(
    request: Request, kind: Literal["user", "category", "group"]
):
    try:
        result = await asyncio.to_thread(
            QuotaService.get_max_quota, request.token_payload, kind
        )
        return result
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to get quota for kind {kind}",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/quota/{kind}/{item_id}",
    tags=[tag],
    response_model=AdminQuotaResponse,
    summary="Get max quota / limits for a specific entity",
    description=(
        "Returns the current quota and limits dict for the given entity id. "
        "``kind`` is one of ``user``, ``category`` or ``group``. Admin/manager "
        "only. ``@is_admin_or_manager``."
    ),
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_quota_by_kind_item(
    request: Request,
    kind: Literal["user", "category", "group"],
    item_id: str,
):
    try:
        result = await asyncio.to_thread(
            QuotaService.get_max_quota, request.token_payload, kind, item_id
        )
        return result
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to get quota for kind {kind}/{item_id}",
            traceback.format_exc(),
        )


@advanced_router.get(
    "/quota/media/new",
    tags=[tag, "media"],
    status_code=204,
    response_class=Response,
    summary="Check media quota",
    description="Checks if adding new media would exceed the user's quota. Raises an error if the quota is exceeded.",
    responses={
        204: {"description": "Can create a new media"},
        428: {
            "model": ErrorResponse,
            "description": "Cannot create a new media, as it would exceed quota",
        },
    },
    dependencies=[Depends(can_create_media)],
)
async def check_quota_new_media():
    return Response(status_code=204)


@token_router.get(
    "/quota/desktop/new",
    tags=[tag, "desktops"],
    status_code=204,
    response_class=Response,
    summary="Check desktops quota",
    description="Checks if creating a new desktop would exceed the user's quota.",
    responses={
        204: {"description": "Can create a new desktop"},
        428: {
            "model": ErrorResponse,
            "description": "Cannot create a new desktop, as it would exceed quota",
        },
    },
    dependencies=[Depends(can_create_desktop)],
)
async def check_quota_new_desktop():
    return Response(status_code=204)


@advanced_router.get(
    "/quota/template/new",
    tags=[tag, "templates"],
    status_code=204,
    response_class=Response,
    summary="Check templates quota",
    description="Checks if creating a new template would exceed the user's quota.",
    responses={
        204: {"description": "Can create a new template"},
        428: {
            "model": ErrorResponse,
            "description": "Cannot create a new template, as it would exceed quota",
        },
    },
    dependencies=[Depends(can_create_template)],
)
async def check_quota_new_template():
    return Response(status_code=204)


@advanced_router.get(
    "/quota/deployment/new",
    tags=[tag, "deployments"],
    status_code=204,
    response_class=Response,
    summary="Check deployments quota",
    description="Checks if creating a new deployment would exceed the user's quota.",
    responses={
        204: {"description": "Can create a new deployment"},
        428: {
            "model": ErrorResponse,
            "description": "Cannot create a new deployment, as it would exceed quota",
        },
    },
    dependencies=[Depends(can_create_deployment)],
)
async def check_quota_new_deployment():
    return Response(status_code=204)
