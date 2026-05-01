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
from typing import Literal

from api import admin_router, manager_router
from api.dependencies.body_parsers import parse_json_or_form
from api.schemas.admin.domains import (
    AdminDomainStoragePathData,
    AdminDomainXmlData,
    AdminDomainXmlSectionsSaveData,
    AdminDomainXmlSectionsSaveResponse,
    AdminListDomainsData,
    AdminMultipleActionsData,
)
from api.schemas.common import EmptyResponse, ErrorResponse
from api.services.admin.domains import AdminDomainsService
from api.services.error import Error
from fastapi import BackgroundTasks, Depends, Path, Request

tag = "admin_domains"


# ══════════════════════════════════════════════════════════════════════════
#  List Domains (desktops & templates)
# ══════════════════════════════════════════════════════════════════════════


@manager_router.post(
    "/admin/domains",
    tags=[tag],
    response_model=list[dict],
    summary="List domains",
    description="List desktops or templates with optional category filter. "
    "Managers are scoped to their own category.",
    responses={
        200: {"description": "Domains list retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_list_domains(
    request: Request, data: AdminListDomainsData
) -> list[dict]:
    try:
        if data.domain_ids:
            result = AdminDomainsService.get_domains_by_ids(
                request.token_payload, data.domain_ids
            )
        elif data.kind == "desktop":
            result = AdminDomainsService.list_desktops(
                request.token_payload, data.categories
            )
        else:
            result = AdminDomainsService.list_templates(request.token_payload)
        return result or []
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list domains",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Domain Details
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/domain/{domain_id}/details",
    tags=[tag],
    response_model=dict,
    summary="Get domain details",
    description="Returns detailed data for a specific domain.",
    responses={
        200: {"description": "Domain details retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_domain_details(request: Request, domain_id: str) -> dict:
    try:
        result = AdminDomainsService.get_domain_details(
            request.token_payload, domain_id
        )
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get domain details",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/domain/{domain_id}/viewer_data",
    tags=[tag],
    response_model=dict,
    summary="Get domain viewer data",
    description="Returns viewer connection data for a domain.",
    responses={
        200: {"description": "Domain viewer data retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_domain_viewer_data(request: Request, domain_id: str) -> dict:
    try:
        result = AdminDomainsService.get_domain_viewer_data(
            request.token_payload, domain_id
        )
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get domain viewer data",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/deployment/{deployment_id}/viewer_data",
    tags=[tag],
    response_model=dict,
    summary="Get deployment viewer data",
    description="Returns viewer connection data for a deployment.",
    responses={
        200: {"description": "Deployment viewer data retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_deployment_viewer_data(request: Request, deployment_id: str) -> dict:
    try:
        result = AdminDomainsService.get_deployment_viewer_data(
            request.token_payload, deployment_id
        )
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get deployment viewer data",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Domains by Status
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/domains_status/{status}",
    tags=[tag],
    response_model=list[dict],
    summary="Get domains by status",
    description="Returns domains matching a given status. "
    "Supports 'delete_pending' and other status values.",
    responses={
        200: {"description": "Domains by status retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_domains_status(request: Request, status: str) -> list[dict]:
    try:
        result = AdminDomainsService.get_domains_by_status(
            request.token_payload, status
        )
        return result or []
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get domains by status",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/domains/status/{status}/find_storages",
    tags=[tag],
    response_model=dict,
    summary="Enqueue find tasks for storages of domains in a given status",
    description=(
        "Scans every ``desktop`` domain with the given status, collects "
        "their storage ids and enqueues a ``find`` task for each. "
        "``@is_admin_or_manager`` — managers are scoped to their own "
        "category via the ``kind_status_category`` secondary index."
    ),
    responses={
        500: {"model": ErrorResponse},
    },
)
async def admin_find_storages_by_domain_status(request: Request, status: str) -> dict:
    try:
        result = AdminDomainsService.find_storages_by_domain_status(
            request.token_payload, status
        )
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to enqueue find tasks for domain storages",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Domain Storage
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/domain/storage/{domain_id}",
    tags=[tag],
    response_model=list[dict],
    summary="Get domain storage",
    description="Returns storage information for a domain.",
    responses={
        200: {"description": "Domain storage info retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_domain_storage(request: Request, domain_id: str) -> list[dict]:
    try:
        result = AdminDomainsService.get_domain_storage(
            request.token_payload, domain_id
        )
        return result or []
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get domain storage",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Domain XML
# ══════════════════════════════════════════════════════════════════════════


@admin_router.get(
    "/admin/domain/{domain_id}/xml",
    tags=[tag],
    response_model=dict,
    summary="Get domain XML",
    description="Returns the XML configuration for a domain.",
    responses={
        200: {"description": "Domain XML retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_domain_xml_get(request: Request, domain_id: str) -> dict:
    try:
        result = AdminDomainsService.get_domain_xml(domain_id)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get domain XML",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/domain/{domain_id}/xml",
    tags=[tag],
    response_model=dict,
    summary="Update domain XML",
    description="Updates the XML configuration for a domain and returns the updated XML.",
    responses={
        200: {"description": "Domain XML updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_domain_xml_update(
    request: Request, domain_id: str, data: AdminDomainXmlData
) -> dict:
    try:
        request_data = data.model_dump(exclude_none=True)
        result = AdminDomainsService.update_domain_xml(domain_id, request_data)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update domain XML",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Template Tree
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/desktops/tree_list/{template_id}",
    tags=[tag],
    response_model=list[dict],
    summary="Get template tree list",
    description="Returns the template tree list for a given template.",
    responses={
        200: {"description": "Template tree list retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_desktops_tree_list(request: Request, template_id: str) -> list[dict]:
    try:
        result = AdminDomainsService.get_template_tree_list(
            request.token_payload, template_id
        )
        return result or []
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get template tree list",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/domain/template_tree/{desktop_id}",
    tags=[tag],
    response_model=list[dict],
    summary="Get domain template tree",
    description="Returns the template ancestry tree for a domain.",
    responses={
        200: {"description": "Domain template tree retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_domain_template_tree(request: Request, desktop_id: str) -> list[dict]:
    try:
        result = AdminDomainsService.get_domain_template_tree(
            request.token_payload, desktop_id
        )
        return result or []
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get domain template tree",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Multiple Actions
# ══════════════════════════════════════════════════════════════════════════


@manager_router.post(
    "/admin/multiple_actions",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Perform multiple domain actions",
    description="Perform bulk actions (start, stop, delete, etc.) on multiple domains.",
    responses={
        200: {"description": "Actions performed"},
        500: {"model": ErrorResponse},
    },
)
async def admin_multiple_actions(
    request: Request,
    data: AdminMultipleActionsData,
    background_tasks: BackgroundTasks,
) -> EmptyResponse:
    try:
        AdminDomainsService.multiple_actions(
            request.token_payload, data.action, data.ids, background_tasks
        )
        return EmptyResponse()
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to perform multiple actions",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Template Delete
# ══════════════════════════════════════════════════════════════════════════


@manager_router.delete(
    "/admin/templates/delete/{template_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete a template",
    description="Deletes a template by ID, moving it to recycle bin.",
    responses={
        200: {"description": "Template deleted"},
        500: {"model": ErrorResponse},
    },
)
async def admin_template_delete(request: Request, template_id: str) -> EmptyResponse:
    try:
        AdminDomainsService.delete_template(request.token_payload, template_id)
        return EmptyResponse()
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete template",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Domain Fields
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/domains/{field}/{kind}",
    tags=[tag],
    response_model=list,
    summary="Get domain field values",
    description="Returns distinct values for a specific field across domains of a given kind.",
    responses={
        200: {"description": "Domain field values retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_domains_field(request: Request, field: str, kind: str) -> list:
    try:
        result = AdminDomainsService.get_domains_field(
            request.token_payload, field, kind
        )
        return result or []
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get domain field values",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Domain Hardware
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/domain/hardware/{domain_id}",
    tags=[tag],
    response_model=dict,
    summary="Get domain hardware",
    description="Returns hardware details for a domain.",
    responses={
        200: {"description": "Domain hardware retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_domain_hardware(request: Request, domain_id: str) -> dict:
    try:
        result = AdminDomainsService.get_domain_hardware(
            request.token_payload, domain_id
        )
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get domain hardware",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Bulk Status Changes
# ══════════════════════════════════════════════════════════════════════════


@admin_router.put(
    "/desktops/{current_status}/{target_status}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Change desktop status in bulk",
    description="Changes the status of all desktops matching the current status "
    "to the target status.",
    responses={
        200: {"description": "Status changed"},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_desktops_status(
    request: Request, current_status: str, target_status: str
) -> EmptyResponse:
    try:
        AdminDomainsService.change_desktops_status(current_status, target_status)
        return EmptyResponse()
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to change desktop status",
            traceback.format_exc(),
        )


@admin_router.put(
    "/desktops/category/{category}/status/{current_status}/{target_status}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Change desktop status by category",
    description="Changes the status of desktops in a specific category matching "
    "the current status to the target status.",
    responses={
        200: {"description": "Status changed"},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_desktops_status_category(
    request: Request, category: str, current_status: str, target_status: str
) -> EmptyResponse:
    try:
        AdminDomainsService.change_desktops_status_category(
            category, current_status, target_status
        )
        return EmptyResponse()
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to change desktop status by category",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Domain Storage Path
# ══════════════════════════════════════════════════════════════════════════


@admin_router.put(
    "/domain/{domain_id}/storage_path",
    tags=[tag],
    response_model=dict,
    summary="Update domain storage path",
    description="Updates the storage path of a domain, replacing all occurrences "
    "of the old path with the new path.",
    responses={
        200: {"description": "Storage path updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_domain_storage_path(
    request: Request, domain_id: str, data: AdminDomainStoragePathData
) -> dict:
    try:
        result = AdminDomainsService.update_domain_storage_path(
            domain_id, data.old_path, data.new_path
        )
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update domain storage path",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Domain Search Info
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/domain/search-info/{domain_id}",
    tags=[tag],
    response_model=dict,
    summary="Get domain search info",
    description="Returns domain info enriched with owner data for search results.",
    responses={
        200: {"description": "Domain search info retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_domain_search_info(request: Request, domain_id: str) -> dict:
    try:
        result = AdminDomainsService.get_domain_search_info(
            request.token_payload, domain_id
        )
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get domain search info",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Logs Desktops Query
# ══════════════════════════════════════════════════════════════════════════


@admin_router.post(
    "/admin/logs_desktops",
    tags=[tag],
    response_model=dict,
    summary="Query desktop logs (raw)",
    description="Query desktop logs with DataTables-style parameters. "
    "Returns raw log data.",
    responses={
        200: {"description": "Desktop logs retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_logs_desktops_raw(
    request: Request, form_data=Depends(parse_json_or_form)
) -> dict:
    try:
        result = AdminDomainsService.query_logs_desktops(form_data, view="raw")
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to query desktop logs",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/logs_desktops/{view}",
    tags=[tag],
    response_model=dict,
    summary="Query desktop logs (grouped)",
    description="Query desktop logs with DataTables-style parameters. "
    "Supports views: 'raw', 'desktop_grouping', 'category_grouping'.",
    responses={
        200: {"description": "Desktop logs retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_logs_desktops_view(request: Request, view: str = "raw") -> dict:
    try:
        try:
            form_data = await request.form()
        except AssertionError:
            raise Error(
                "bad_request",
                "Request body must be multipart form data",
            )
        result = AdminDomainsService.query_logs_desktops(form_data, view=view)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to query desktop logs",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Logs Users Query
# ══════════════════════════════════════════════════════════════════════════


@admin_router.post(
    "/admin/logs_users",
    tags=[tag],
    response_model=dict,
    summary="Query user logs (raw)",
    description="Query user logs with DataTables-style parameters. "
    "Returns raw log data.",
    responses={
        200: {"description": "User logs retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_logs_users_raw(
    request: Request, form_data=Depends(parse_json_or_form)
) -> dict:
    try:
        result = AdminDomainsService.query_logs_users(form_data, view="raw")
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to query user logs",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/logs_users/{view}",
    tags=[tag],
    response_model=dict,
    summary="Query user logs (grouped)",
    description="Query user logs with DataTables-style parameters. "
    "Supports views: 'raw', 'user_grouping', 'category_grouping'.",
    responses={
        200: {"description": "User logs retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_logs_users_view(request: Request, view: str = "raw") -> dict:
    try:
        try:
            form_data = await request.form()
        except AssertionError:
            raise Error(
                "bad_request",
                "Request body must be multipart form data",
            )
        result = AdminDomainsService.query_logs_users(form_data, view=view)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to query user logs",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Logs REST List endpoints (JSON GET — simpler than DataTables POST)
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/logs_desktops/list",
    tags=[tag],
    response_model=list[dict],
    summary="List desktop logs (JSON)",
    description="Simple JSON list of desktop logs with optional filters.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_logs_desktops_list(
    request: Request,
    start_date: str = None,
    end_date: str = None,
    limit: int = 100,
    offset: int = 0,
    desktop_id: str = None,
    user_id: str = None,
) -> list[dict]:
    try:
        result = AdminDomainsService.list_desktop_logs(
            request.token_payload,
            start_date,
            end_date,
            limit,
            offset,
            desktop_id,
            user_id,
        )
        return result or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list desktop logs",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/logs_users/list",
    tags=[tag],
    response_model=list[dict],
    summary="List user logs (JSON)",
    description="Simple JSON list of user logs with optional filters.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_logs_users_list(
    request: Request,
    start_date: str = None,
    end_date: str = None,
    limit: int = 100,
    offset: int = 0,
    user_id: str = None,
    group_id: str = None,
) -> list[dict]:
    try:
        result = AdminDomainsService.list_user_logs(
            request.token_payload,
            start_date,
            end_date,
            limit,
            offset,
            user_id,
            group_id,
        )
        return result or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list user logs",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Logs Desktops Config
# ══════════════════════════════════════════════════════════════════════════


@admin_router.get(
    "/logs_desktops/config/old_entries",
    tags=[tag],
    response_model=dict,
    summary="Get desktop logs old entries config",
    description="Returns the configuration for desktop logs old entries management.",
    responses={
        200: {"description": "Config retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_logs_desktops_config(request: Request) -> dict:
    try:
        result = AdminDomainsService.get_logs_desktops_config()
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get desktop logs config",
            traceback.format_exc(),
        )


@admin_router.put(
    "/logs_desktops/config/old_entries/max_time/{max_time}",
    tags=[tag],
    response_model=dict,
    summary="Set desktop logs max time",
    description="Sets the maximum time (in hours) for desktop logs old entries. "
    "Minimum value is 24 hours.",
    responses={
        200: {"description": "Max time updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_logs_desktops_max_time(request: Request, max_time: int) -> dict:
    try:
        result = AdminDomainsService.set_logs_desktops_max_time(max_time)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to set desktop logs max time",
            traceback.format_exc(),
        )


@admin_router.put(
    "/logs_desktops/config/old_entries/action/{action}",
    tags=[tag],
    response_model=dict,
    summary="Set desktop logs old entries action",
    description="Sets the action for desktop logs old entries. "
    'Valid values: "delete", "none".',
    responses={
        200: {"description": "Action updated"},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_logs_desktops_action(
    request: Request, action: Literal["delete", "none"]
) -> dict:
    try:
        result = AdminDomainsService.set_logs_desktops_action(action)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to set desktop logs action",
            traceback.format_exc(),
        )


@admin_router.put(
    "/logs_desktops/old_entries/delete",
    tags=[tag],
    response_model=int,
    summary="Delete old desktop logs",
    description="Deletes desktop logs older than the configured max time. "
    "Runs asynchronously and returns the count of logs to delete.",
    responses={
        200: {"description": "Delete initiated, returns count"},
        500: {"model": ErrorResponse},
    },
)
async def admin_logs_desktops_delete(
    request: Request, background_tasks: BackgroundTasks
) -> int:
    try:
        count = AdminDomainsService.delete_old_desktop_logs(background_tasks)
        return count or 0
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete old desktop logs",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/logs_desktops/old_entries/delete/all",
    tags=[tag],
    response_model=int,
    summary="Delete all desktop logs",
    description="Deletes all desktop logs regardless of age. "
    "Runs asynchronously and returns the count of logs to delete.",
    responses={
        200: {"description": "Delete initiated, returns count"},
        500: {"model": ErrorResponse},
    },
)
async def admin_logs_desktops_delete_all(
    request: Request, background_tasks: BackgroundTasks
) -> int:
    try:
        count = AdminDomainsService.delete_all_desktop_logs(background_tasks)
        return count or 0
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete all desktop logs",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Logs Users
# ══════════════════════════════════════════════════════════════════════════


@admin_router.get(
    "/logs_users/config/old_entries",
    tags=[tag],
    response_model=dict,
    summary="Get user logs old entries config",
    description="Returns the configuration for user logs old entries management.",
    responses={
        200: {"description": "Config retrieved"},
        500: {"model": ErrorResponse},
    },
)
async def admin_logs_users_config(request: Request) -> dict:
    try:
        result = AdminDomainsService.get_logs_users_config()
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get user logs config",
            traceback.format_exc(),
        )


@admin_router.put(
    "/logs_users/config/old_entries/max_time/{max_time}",
    tags=[tag],
    response_model=dict,
    summary="Set user logs max time",
    description="Sets the maximum time (in hours) for user logs old entries. "
    "Minimum value is 24 hours.",
    responses={
        200: {"description": "Max time updated"},
        500: {"model": ErrorResponse},
    },
)
async def admin_logs_users_max_time(request: Request, max_time: int) -> dict:
    try:
        result = AdminDomainsService.set_logs_users_max_time(max_time)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to set user logs max time",
            traceback.format_exc(),
        )


@admin_router.put(
    "/logs_users/config/old_entries/action/{action}",
    tags=[tag],
    response_model=dict,
    summary="Set user logs old entries action",
    description="Sets the action for user logs old entries. "
    'Valid values: "delete", "none".',
    responses={
        200: {"description": "Action updated"},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_logs_users_action(
    request: Request, action: Literal["delete", "none"]
) -> dict:
    try:
        result = AdminDomainsService.set_logs_users_action(action)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to set user logs action",
            traceback.format_exc(),
        )


@admin_router.put(
    "/logs_users/old_entries/delete",
    tags=[tag],
    response_model=int,
    summary="Delete old user logs",
    description="Deletes user logs older than the configured max time. "
    "Runs asynchronously and returns the count of logs to delete.",
    responses={
        200: {"description": "Delete initiated, returns count"},
        500: {"model": ErrorResponse},
    },
)
async def admin_logs_users_delete(
    request: Request, background_tasks: BackgroundTasks
) -> int:
    try:
        count = AdminDomainsService.delete_old_user_logs(background_tasks)
        return count or 0
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete old user logs",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/logs_users/old_entries/delete/all",
    tags=[tag],
    response_model=int,
    summary="Delete all user logs",
    description="Deletes all user logs regardless of age. "
    "Runs asynchronously and returns the count of logs to delete.",
    responses={
        200: {"description": "Delete initiated, returns count"},
        500: {"model": ErrorResponse},
    },
)
async def admin_logs_users_delete_all(
    request: Request, background_tasks: BackgroundTasks
) -> int:
    try:
        count = AdminDomainsService.delete_all_user_logs(background_tasks)
        return count or 0
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete all user logs",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  XML Sections Editor
# ══════════════════════════════════════════════════════════════════════════


@admin_router.get(
    "/admin/domains/xml_capabilities",
    tags=[tag],
    response_model=dict,
    summary="Get XML capabilities",
    description="Returns libvirt domain XML capabilities and section definitions.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_domain_xml_capabilities(request: Request) -> dict:
    try:
        from api.services.xml_sections import get_domain_capabilities

        caps = get_domain_capabilities()
        return caps if isinstance(caps, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get XML capabilities",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/domains/xml_sections/parse",
    tags=[tag],
    response_model=dict,
    summary="Parse raw XML into sections",
    description="Split raw XML into editable sections without a saved domain.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_domain_xml_sections_parse(request: Request) -> dict:
    try:
        from api.services.xml_sections import split_xml_sections

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
        xml_str = data.get("xml", "")
        if not isinstance(xml_str, str) or not xml_str.strip():
            raise await Error.create(
                request, "bad_request", "Missing or invalid 'xml' field"
            )
        if len(xml_str) > 2 * 1024 * 1024:
            raise await Error.create(
                request, "bad_request", "XML exceeds maximum allowed size (2 MB)"
            )
        sections = split_xml_sections(xml_str, [])
        return {"sections": sections}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to parse XML sections",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/domains/xml_sections/{domain_id}",
    tags=[tag],
    response_model=dict,
    summary="Get domain XML sections",
    description="Split a domain's XML into editable sections.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_domain_xml_sections_get(request: Request, domain_id: str) -> dict:
    try:
        from api.services.xml_sections import split_xml_sections

        domain = AdminDomainsService.get_domain_xml_and_protected(domain_id)
        sections = split_xml_sections(domain["xml"], domain["protected"])
        return {"sections": sections, "xml_full": domain["xml"]}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get XML sections",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/domains/xml_sections/{domain_id}",
    tags=[tag],
    response_model=AdminDomainXmlSectionsSaveResponse,
    summary="Save domain XML sections",
    description="Merge edited XML sections back into the domain's full XML.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_domain_xml_sections_save(
    request: Request, domain_id: str, data: AdminDomainXmlSectionsSaveData
):
    try:
        new_xml = AdminDomainsService.apply_xml_section_edits(
            domain_id, data.sections, data.protected_sections
        )
        return AdminDomainXmlSectionsSaveResponse(xml=new_xml)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to save XML sections",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/domains/xml_sections/{domain_id}/save_virt_install",
    tags=[tag],
    response_model=dict,
    summary="Save domain XML sections as a new virt_install template",
    description=(
        "Merges the edited XML sections into the domain's full XML, "
        "generalises disk paths / UUIDs / runtime attributes, derives "
        "``www``/``icon``/``vers`` metadata from the libosinfo tag, and "
        "inserts a new ``virt_install`` row with a slug-of-name id."
    ),
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_domain_xml_sections_save_as_virt_install(
    request: Request, domain_id: str
) -> dict:
    try:
        from api.services.xml_sections import save_as_virt_install

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
        if "sections" not in data or "name" not in data:
            raise Error(
                "bad_request",
                "Missing 'sections' or 'name' in request body",
                traceback.format_exc(),
            )
        record = save_as_virt_install(domain_id, data["sections"], data["name"])
        return {"id": record["id"], "name": record["name"]}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to save XML sections as virt_install",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/virt_install/xml_sections/{virt_id}",
    tags=[tag],
    response_model=dict,
    summary="Get virt_install XML sections",
    description=(
        "Split a ``virt_install`` template's XML into editable sections "
        "for the admin XML sections editor."
    ),
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_virt_install_xml_sections_get(request: Request, virt_id: str) -> dict:
    try:
        from api.services.xml_sections import get_virt_install_xml_sections

        result = get_virt_install_xml_sections(virt_id)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get virt_install XML sections",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/virt_install/xml_sections/{virt_id}",
    tags=[tag],
    response_model=dict,
    summary="Save virt_install XML sections",
    description=(
        "Merge edited sections back into a ``virt_install`` template's " "full XML."
    ),
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_virt_install_xml_sections_save(request: Request, virt_id: str) -> dict:
    try:
        from api.services.xml_sections import save_virt_install_xml_sections

        try:

            data = await request.json()

        except json.JSONDecodeError:

            raise Error("bad_request", "Request body must be JSON")
        if "sections" not in data:
            raise Error(
                "bad_request",
                "Missing 'sections' in request body",
                traceback.format_exc(),
            )
        result = save_virt_install_xml_sections(virt_id, data["sections"])
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to save virt_install XML sections",
            traceback.format_exc(),
        )
