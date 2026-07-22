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
from typing import Annotated, Literal, Optional

from api import advanced_router, manager_router, open_router, token_router
from api.dependencies.alloweds import (
    is_allowed_template_id,
    owns_domain_id,
    owns_domain_id_body,
    owns_template_children,
)
from api.dependencies.domains import check_domain_kind, template_has_no_children
from api.dependencies.jwt_token import is_admin
from api.dependencies.quotas import can_create_template
from api.dependencies.storage_pools import check_create_storage_pool_availability
from api.schemas.domains.desktops import DomainInfoResponse
from api.services.desktops import DesktopService
from api.services.domains import DomainService
from api.services.error import Error
from fastapi import Body, Depends, Path, Query, Request
from fastapi.responses import JSONResponse

from ...schemas.allowed import AllowedBase, AllowedResponse, AllowedUpdate
from ...schemas.common import DeleteResponse, ErrorResponse, SimpleResponse
from ...schemas.domains.templates import (
    DuplicateTemplateRequest,
    NewTemplateRequest,
    TemplateDetailsResponse,
    TemplateEditRequest,
    TemplateSetEnabledRequest,
    TemplateToDesktopRequest,
    TemplateTreeResponse,
    UserAllowedTemplateFlatItem,
    UserAllowedTemplateSearchFields,
    UserAllowedTemplatesPaginationResponse,
    UserSharedTemplatesResponse,
    UserTemplateFilterParams,
    UserTemplateSearchFields,
    UserTemplatesPaginationResponse,
    UserTemplatesResponse,
)
from ...services.templates import TemplateService

tag = "templates"


@token_router.get(
    "/item/template/{template_id}/get-info",
    tags=[tag],
    response_model=DomainInfoResponse,
    dependencies=[Depends(is_allowed_template_id)],
    summary="Get template information",
    description="Returns detailed information about a specific template.",
)
async def get_template_info(template_id: str, request: Request):
    try:
        return JSONResponse(
            content=DomainInfoResponse(
                **await asyncio.to_thread(
                    DomainService.get_domain_info, template_id, request.token_payload
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
            "Failed to retrieve template information",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/template/{template_id}/get-details",
    response_model=TemplateDetailsResponse,
    summary="Get the details of a template",
    tags=[tag],
    description="Gets a template details based on the template ID",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(is_allowed_template_id),
    ],
)
async def get_template_details(
    request: Request,
    template_id: str = Path(..., description="The ID of the template"),
):
    try:
        info = await asyncio.to_thread(
            TemplateService.get_template_details, template_id
        )
        return JSONResponse(
            content=TemplateDetailsResponse(**info).model_dump(mode="json"),
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
            f"Failed to retrieve template details",
            traceback.format_exc(),
        )


@token_router.get(
    "/items/templates/allowed/{kind}",
    tags=[tag],
    response_model=list[UserAllowedTemplateFlatItem],
    summary="Get flat list of templates the user can use",
    description=(
        "Returns a flat list of enabled templates the caller is allowed "
        "to use. ``kind`` is one of ``all`` (owned + shared enabled "
        "templates) or ``shared`` (only templates shared with the user, "
        "not owned). Used by frontends that need a simple dropdown list "
        "without pagination. Replaces v3 "
        "``GET /user/templates/allowed/{kind}`` ``@has_token``."
    ),
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_user_allowed_templates_flat(
    request: Request, kind: Literal["all", "shared"]
):
    try:
        templates = await asyncio.to_thread(
            TemplateService.get_user_allowed_templates_flat, request.token_payload, kind
        )
        return JSONResponse(
            content=[
                UserAllowedTemplateFlatItem(**t).model_dump(mode="json")
                for t in (templates or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user allowed templates",
            traceback.format_exc(),
        )


@advanced_router.get(
    "/items/templates",
    tags=[tag],
    response_model=UserTemplatesResponse,
    summary="Get user templates",
    description="Returns a list of all templates that belong to the user calling the endpoint.",
    operation_id="get_user_templates",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_user_templates(
    request: Request,
):
    try:
        return JSONResponse(
            content=UserTemplatesResponse(
                templates=await asyncio.to_thread(
                    TemplateService.get_user_templates,
                    user_id=request.token_payload["user_id"],
                ),
            ).model_dump(mode="json"),
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


@advanced_router.get(
    "/items/paginated/templates",
    tags=[tag],
    response_model=UserTemplatesPaginationResponse,
    summary="Get user templates",
    description="Returns a list of all templates that belong to the user calling the endpoint.",
    operation_id="get_user_templates_paginated",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_user_templates(
    request: Request,
    start_after: int = Query(
        default=None,
        description="Start the retrieval after the given accessed. If not provided, starts from the beginning.",
    ),
    page_size: int = Query(
        default=10,
        description="Number of templates to return. Default is 10. The given value will be multiplied by 5 in order to preload more templates for the user.",
        ge=1,
        le=50,
    ),
    sort_field: str = Query(
        default="accessed",
        description="Field to sort the templates by. Default is 'accessed'.",
    ),
    sort_order: Literal["desc", "asc"] = Query(
        default="desc",
        description="Order to sort the templates by. Default is 'desc'. Can be 'asc' or 'desc'.",
    ),
    search: str = Query(
        default=None,
        description="Search term to filter templates by name or description. If provided, search_field must also be provided.",
    ),
    search_field: Optional[UserTemplateSearchFields] = Query(
        default=None,
        description="Field to search in. If not provided, no search is performed.",
    ),
    filters: UserTemplateFilterParams = Depends(),
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
        user_templates = await asyncio.to_thread(
            TemplateService.get_user_templates_paginated,
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
            content=UserTemplatesPaginationResponse(**user_templates).model_dump(
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
            "Failed to retrieve user templates",
            traceback.format_exc(),
        )


@token_router.get(
    "/items/templates/get-shared",
    tags=[tag],
    response_model=UserSharedTemplatesResponse,
    summary="Get shared templates for user",
    description="Returns a list of all templates that are shared with them.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_user_shared_templates(
    request: Request,
):
    try:
        return JSONResponse(
            content=UserSharedTemplatesResponse(
                templates=await asyncio.to_thread(
                    TemplateService.get_user_shared_templates, request.token_payload
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
            "Failed to retrieve user shared templates",
            traceback.format_exc(),
        )


@advanced_router.get(
    "/item/template/{template_id}/get-allowed",
    tags=[tag],
    response_model=AllowedResponse,
    summary="Get allowed users, roles, groups, categories for a template",
    description="Returns the list of groups, users, roles, and categories that currently have access to the specified template.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[
        Depends(owns_domain_id("template_id")),
        Depends(check_domain_kind("template_id", "template")),
    ],
)
async def get_template_allowed(template_id: str, request: Request):
    try:
        return JSONResponse(
            content=AllowedResponse(
                **await asyncio.to_thread(
                    TemplateService.get_template_allowed,
                    template_id,
                    request.token_payload["category_id"],
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
            f"Failed to retrieve template allowed entities",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/item/template/{template_id}/update-allowed",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Update allowed entities for a template",
    description="Update the list of groups, users, roles, and categories that have access to the specified template. Only provided fields will be updated.",
    dependencies=[
        Depends(owns_domain_id("template_id")),
        Depends(check_domain_kind("template_id", "template")),
    ],
)
async def update_template_allowed(
    request: Request, allowed: AllowedUpdate, template_id: str
):
    try:
        await asyncio.to_thread(
            TemplateService.update_template_allowed, template_id, allowed
        )
        return JSONResponse(
            content=SimpleResponse(id=template_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to update template allowed entities",
            traceback.format_exc(),
        )


@token_router.get(
    "/items/templates/get-allowed",
    tags=[tag],
    response_model=UserAllowedTemplatesPaginationResponse,
    summary="Get allowed templates for user",
    description="Returns a list of all templates that the user can see, considering its role permissions.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_user_allowed_templates(
    request: Request,
    start_after: int = Query(
        default=None,
        description="Start the retrieval after the given accessed. If not provided, starts from the beginning.",
    ),
    page_size: int = Query(
        default=10,
        description="Number of templates to return. Default is 10. The given value will be multiplied by 5 in order to preload more templates for the user.",
        ge=1,
        le=50,
    ),
    sort_field: Literal["accessed"] = Query(
        default="accessed",
        description="Field to sort the templates by. Default is 'accessed'.",
    ),
    sort_order: Literal["desc", "asc"] = Query(
        default="desc",
        description="Order to sort the templates by. Default is 'desc'. Can be 'asc' or 'desc'.",
    ),
    search: str = Query(
        default=None,
        description="Search term to filter templates by name or description. If provided, search_field must also be provided.",
    ),
    search_field: Optional[UserAllowedTemplateSearchFields] = Query(
        default=None,
        description="Field to search in. If not provided, no search is performed.",
    ),
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
        user_templates = await asyncio.to_thread(
            TemplateService.get_user_allowed_templates,
            user_id=request.token_payload["user_id"],
            user_category=request.token_payload["category_id"],
            user_group=request.token_payload["group_id"],
            user_role=request.token_payload.get("role_id"),
            start_after=start_after,
            page_size=page_size,
            sort_field=sort_field,
            sort_order=sort_order,
            search=search,
            search_field=search_field,
        )
        return JSONResponse(
            content=UserAllowedTemplatesPaginationResponse(**user_templates).model_dump(
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
            "Failed to retrieve user allowed templates",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/item/template/{template_id}/edit",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Update template information",
    description="Update the properties of a specific template.",
    dependencies=[
        Depends(owns_domain_id("template_id")),
        Depends(check_domain_kind("template_id", "template")),
    ],
)
async def update_template(
    request: Request,
    template_id: str,
    data: TemplateEditRequest,
):
    try:
        payload = data.model_dump(exclude_unset=True)
        if data.image is not None and getattr(data.image, "file", None) is not None:
            payload["image"]["file"] = data.image.file.model_dump(exclude_unset=True)

        if "forced_hyp" in payload or "favourite_hyp" in payload:
            await is_admin(request.token_payload)

        await asyncio.to_thread(
            DesktopService.edit_desktop,
            template_id,
            payload,
            request.token_payload,
        )

        return JSONResponse(
            content=SimpleResponse(id=template_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to edit template {template_id}",
            traceback.format_exc(),
        )


@manager_router.put(
    "/item/template/{template_id}/change-owner/{user_id}",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Change template owner",
    description=(
        "Reassigns a template to a different user. ``@is_admin_or_manager``. "
        "Both ``ownsUserId(user_id)`` and ``ownsDomainId(template_id)`` "
        "are enforced by the service."
    ),
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def change_template_owner(
    request: Request,
    template_id: str = Path(..., description="The ID of the template"),
    user_id: str = Path(..., description="The ID of the new owner"),
):
    try:
        await asyncio.to_thread(
            TemplateService.change_owner,
            payload=request.token_payload,
            template_id=template_id,
            new_user_id=user_id,
        )
        return JSONResponse(
            content=SimpleResponse(id=template_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to change template owner",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/item/template/{template_id}/set-enabled",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Enable or disable a template",
    description=(
        "Toggles whether a template is enabled (usable for creating "
        "desktops). Replaces v3 ``PUT /template/update`` and preserves "
        "its side effects: enable runs the template-create quota check, "
        "disable cascade-flags non-persistent desktops as ForceDeleting "
        "so the engine cleans them up."
    ),
    dependencies=[
        Depends(owns_domain_id("template_id")),
        Depends(check_domain_kind("template_id", "template")),
    ],
)
async def set_template_enabled(
    request: Request,
    template_id: str,
    data: TemplateSetEnabledRequest,
):
    try:
        await asyncio.to_thread(
            TemplateService.set_enabled,
            template_id,
            data.enabled,
            request.token_payload,
        )
        return JSONResponse(
            content=SimpleResponse(id=template_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to set enabled state for template {template_id}",
            traceback.format_exc(),
        )


@advanced_router.get(
    "/item/template/{template_id}/get-tree",
    tags=[tag],
    response_model=TemplateTreeResponse,
    summary="Get template dependency tree",
    description="Returns a tree structure showing all desktops and templates that depend on the specified template.",
    dependencies=[
        Depends(owns_domain_id("template_id")),
        Depends(check_domain_kind("template_id", "template")),
    ],
)
async def get_template_tree(
    request: Request,
    template_id: str,
):
    try:
        return JSONResponse(
            content=TemplateTreeResponse(
                **await asyncio.to_thread(
                    TemplateService.get_template_tree,
                    template_id,
                    request.token_payload,
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
            "Failed to retrieve template dependency tree",
            traceback.format_exc(),
        )


@advanced_router.post(
    "/item/template",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Create new template",
    description="Create a new template from a desktop.",
    dependencies=[
        Depends(can_create_template),
        Depends(check_create_storage_pool_availability),
        Depends(owns_domain_id_body("desktop_id")),
    ],
)
async def create_template(
    request: Request,
    data: NewTemplateRequest,
):
    try:
        parsed_data = data.model_dump()
        if request.token_payload.get("role_id") not in ["admin", "manager"]:
            parsed_data["allowed"] = AllowedBase(
                **parsed_data.get("allowed", {})
            ).model_dump()

        return JSONResponse(
            content=SimpleResponse(
                id=await asyncio.to_thread(
                    TemplateService.create_template,
                    request.token_payload,
                    parsed_data,
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
            "Failed to create new template",
            traceback.format_exc(),
        )


@advanced_router.post(
    "/item/template/{template_id}/duplicate",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Duplicate template",
    description="Create a new template by duplicating an existing one.",
    dependencies=[
        Depends(is_allowed_template_id),
        Depends(can_create_template),
        Depends(check_create_storage_pool_availability),
    ],
)
async def duplicate_template(
    request: Request,
    template_id: str,
    data: DuplicateTemplateRequest,
):
    try:
        return JSONResponse(
            content=SimpleResponse(
                id=await asyncio.to_thread(
                    TemplateService.duplicate_template,
                    request.token_payload,
                    template_id,
                    data.model_dump(),
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
            "Failed to duplicate template",
            traceback.format_exc(),
        )


@advanced_router.delete(
    "/item/template/{template_id}",
    tags=[tag],
    response_model=DeleteResponse,
    summary="Delete template",
    description="Delete a specific template.",
    dependencies=[
        Depends(owns_domain_id("template_id")),
        Depends(check_domain_kind("template_id", "template")),
        Depends(owns_template_children),
    ],
    responses={
        200: {"model": DeleteResponse},
        202: {"model": DeleteResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_template(request: Request, template_id: str):
    try:
        tasks = await asyncio.to_thread(
            TemplateService.delete_template, request.token_payload, template_id
        )
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
                message="Task queued to delete template",
                message_code="item.queued",
                tasks_ids=[task["id"] for task in tasks],
            ).model_dump(mode="json"),
            status_code=202,
        )

    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete template",
            traceback.format_exc(),
        )


@advanced_router.post(
    "/item/template/{template_id}/convert-to-desktop",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Convert template to desktop",
    description=(
        "Convert a specific template into a desktop. Ownership of the "
        "template is enforced by ``owns_domain_id`` (which transitively "
        "requires ``is_not_user``)."
    ),
    dependencies=[
        Depends(owns_domain_id("template_id")),
        Depends(check_domain_kind("template_id", "template")),
        Depends(template_has_no_children),
        Depends(check_create_storage_pool_availability),
    ],
)
async def convert_template_to_desktop(
    template_id: str,
    request: Request,
    data: TemplateToDesktopRequest,
):
    try:
        await asyncio.to_thread(
            TemplateService.convert_to_desktop,
            request.token_payload,
            template_id,
            data.name,
        )
        return JSONResponse(
            content=SimpleResponse(id=template_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete template",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/item/template/{template_id}/toggle-enabled",  # TODO:
    tags=[tag],
    response_model=SimpleResponse,
    summary="Enable or disable template",
    description="Enable or disable a specific template.",
    dependencies=[
        Depends(owns_domain_id("template_id")),
        Depends(check_domain_kind("template_id", "template")),
    ],
)
async def toggle_template_enabled(
    request: Request,
    template_id: str,
):
    try:
        await asyncio.to_thread(TemplateService.toggle_enabled, template_id)
        return JSONResponse(
            content=SimpleResponse(id=template_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to toggle template enabled state",
            traceback.format_exc(),
        )
