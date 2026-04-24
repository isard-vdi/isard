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

from api import admin_router, manager_router, token_router
from api.dependencies.alloweds import owns_recycle_bin_id
from api.schemas.common import (
    DeleteResponse,
    EmptyResponse,
    ErrorResponse,
    SimpleResponse,
)
from api.schemas.recycle_bin import (
    DeleteActionEnum,
    OldEntriesActionEnum,
    RecycleBinBulkRequest,
    RecycleBinBulkResponse,
    RecycleBinCutoffTimeResponse,
    RecycleBinEntriesResponse,
    RecycleBinOldEntriesConfig,
    RecycleBinResponse,
    RecycleBinSetDefaultDeleteRequest,
    RecycleBinStatusResponse,
    RecycleBinSystemCutoffTimeResponse,
    RecycleBinUpdateCutoffTimeRequest,
    RecycleBinUpdateTaskRequest,
    UnusedItemTimeoutRuleCreateRequest,
    UnusedItemTimeoutRulesResponse,
    UnusedItemTimeoutRuleUpdateRequest,
)
from api.services.error import Error
from api.services.recycle_bin import RecycleBinService
from fastapi import Depends, Request
from fastapi.responses import JSONResponse

tag = "recycle_bin"


# ── Token-level endpoints (any authenticated user) ──────────────────────


@token_router.get(
    "/item/recycle-bin/get-default-delete-config",
    tags=[tag],
    response_model=bool,
    summary="Get recycle bin default delete configuration",
    description="Returns the default delete configuration for recycle bin items.",
)
async def get_recycle_bin_default_delete_config(request: Request):
    try:
        return JSONResponse(
            content=RecycleBinService.get_default_delete_config(),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve default delete config",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/recycle-bin/get-user-cutoff-time",
    tags=[tag],
    response_model=RecycleBinCutoffTimeResponse,
    summary="Get recycle bin cutoff time",
    description="Returns the cutoff time for recycle bin items.",
    responses={
        500: {"description": "Failed to retrieve cutoff time"},
    },
)
async def get_recycle_bin_cutoff_time(request: Request):
    try:
        return JSONResponse(
            content=RecycleBinCutoffTimeResponse(
                recycle_bin_cutoff_time=RecycleBinService.get_user_cutoff_time(
                    category_id=request.token_payload["category_id"]
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
            "Failed to retrieve cutoff time",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/recycle-bin/count",
    tags=[tag],
    response_model=int,
    summary="Get user recycle bin count",
    description="Returns the total number of items in the user's recycle bin.",
)
async def get_recycle_bin_count(request: Request):
    try:
        return JSONResponse(
            content=RecycleBinService.get_user_count(
                user_id=request.token_payload["user_id"]
            ),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve recycle bin count",
            traceback.format_exc(),
        )


@token_router.delete(
    "/item/recycle-bin/empty",
    tags=[tag],
    response_model=DeleteResponse,
    summary="Empty recycle bin",
    description="Empties the entire recycle bin.",
    responses={
        202: {"model": DeleteResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def empty_recycle_bin(request: Request):
    try:
        await RecycleBinService.empty_user_recycle_bin(
            user_id=request.token_payload["user_id"]
        )
        return JSONResponse(
            content=DeleteResponse(
                message="Recycle bin entries queued for deletion",
                message_code="item.queued",
            ).model_dump(mode="json"),
            status_code=202,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to empty recycle bin",
            traceback.format_exc(),
        )


@token_router.get(
    "/items/recycle-bin",
    tags=[tag],
    response_model=RecycleBinEntriesResponse,
    summary="Get the user recycle bin entries",
    description="Returns the list of recycle bin entries for a user.",
)
async def get_recycle_bin_item_count_user(request: Request):
    try:
        return JSONResponse(
            content=RecycleBinEntriesResponse(
                entries=RecycleBinService.get_user_recycle_bin_entries(
                    user_id=request.token_payload["user_id"]
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
            "Failed to retrieve recycle bin entries",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/recycle-bin/{recycle_bin_id}",
    tags=[tag],
    response_model=RecycleBinResponse,
    summary="Get recycle bin item details",
    description="Returns detailed information about a specific recycle bin item.",
    dependencies=[
        Depends(owns_recycle_bin_id),
    ],
)
async def get_recycle_bin(request: Request, recycle_bin_id: str):
    try:
        return JSONResponse(
            content=RecycleBinResponse(
                **RecycleBinService.get_recycle_bin_entry_details(
                    recycle_bin_id=recycle_bin_id,
                    all_data=True,
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
            "Failed to retrieve recycle bin details",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/recycle-bin/{recycle_bin_id}/restore",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Restore recycle bin item",
    description="Restores a recycle bin item by ID.",
    dependencies=[
        Depends(owns_recycle_bin_id),
    ],
)
async def restore_recycle_bin(request: Request, recycle_bin_id: str):
    try:
        RecycleBinService.restore_recycle_bin_entry(recycle_bin_id=recycle_bin_id)
        return JSONResponse(
            content=SimpleResponse(
                id=recycle_bin_id,
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to restore recycle bin entry",
            traceback.format_exc(),
        )


@token_router.put(
    "/items/recycle-bin/restore",
    tags=[tag],
    response_model=RecycleBinBulkResponse,
    summary="Bulk restore recycle bin items",
    description="Restores multiple recycle bin items. Processing happens in the background.",
)
async def bulk_restore_recycle_bin(request: Request, data: RecycleBinBulkRequest):
    try:
        ids = await RecycleBinService.bulk_restore(
            recycle_bin_ids=data.recycle_bin_ids,
            user_id=request.token_payload["user_id"],
        )
        return JSONResponse(
            content=RecycleBinBulkResponse(
                recycle_bin_ids=ids,
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to bulk restore recycle bin entries",
            traceback.format_exc(),
        )


@token_router.put(
    "/items/recycle-bin/delete",
    tags=[tag],
    response_model=RecycleBinBulkResponse,
    summary="Bulk delete recycle bin items",
    description="Permanently deletes multiple recycle bin items. Processing happens in the background.",
)
async def bulk_delete_recycle_bin(request: Request, data: RecycleBinBulkRequest):
    try:
        ids = await RecycleBinService.bulk_delete(
            recycle_bin_ids=data.recycle_bin_ids,
            user_id=request.token_payload["user_id"],
        )
        return JSONResponse(
            content=RecycleBinBulkResponse(
                recycle_bin_ids=ids,
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to bulk delete recycle bin entries",
            traceback.format_exc(),
        )


@token_router.delete(
    "/item/recycle-bin/{recycle_bin_id}",
    tags=[tag],
    response_model=DeleteResponse,
    summary="Delete recycle bin item",
    description="Deletes a recycle bin item by ID.",
    dependencies=[
        Depends(owns_recycle_bin_id),
    ],
    responses={
        202: {"model": DeleteResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_recycle_bin_entry(request: Request, recycle_bin_id: str):
    try:
        await RecycleBinService.delete_recycle_bin_entry(
            recycle_bin_id=recycle_bin_id, user_id=request.token_payload["user_id"]
        )
        return JSONResponse(
            content=DeleteResponse(
                message="Recycle bin entry queued for deletion",
                message_code="item.queued",
            ).model_dump(mode="json"),
            status_code=202,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete recycle bin",
            traceback.format_exc(),
        )


# ── Manager-level endpoints (manager + admin) ───────────────────────────


@manager_router.get(
    "/item/recycle-bin/system/cutoff-time",
    tags=[tag],
    response_model=RecycleBinSystemCutoffTimeResponse,
    summary="Get system recycle bin cutoff time",
    description="Returns the system-level cutoff time. Managers get their category's cutoff time.",
)
async def get_system_cutoff_time(request: Request):
    try:
        category_id = (
            request.token_payload["category_id"]
            if request.token_payload["role_id"] == "manager"
            else None
        )
        return JSONResponse(
            content=RecycleBinSystemCutoffTimeResponse(
                recycle_bin_cuttoff_time=RecycleBinService.get_system_cutoff_time(
                    category_id=category_id
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
            "Failed to retrieve system cutoff time",
            traceback.format_exc(),
        )


@manager_router.put(
    "/item/recycle-bin/system/cutoff-time",
    tags=[tag],
    response_model=RecycleBinSystemCutoffTimeResponse,
    summary="Update system recycle bin cutoff time",
    description="Updates the system-level cutoff time. Managers update their category's cutoff time.",
)
async def update_system_cutoff_time(
    request: Request, data: RecycleBinUpdateCutoffTimeRequest
):
    try:
        category_id = (
            request.token_payload["category_id"]
            if request.token_payload["role_id"] == "manager"
            else None
        )
        RecycleBinService.set_system_cutoff_time(
            cutoff_time=data.recycle_bin_cuttoff_time,
            category_id=category_id,
        )
        return JSONResponse(
            content=RecycleBinSystemCutoffTimeResponse(
                recycle_bin_cuttoff_time=data.recycle_bin_cuttoff_time
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update system cutoff time",
            traceback.format_exc(),
        )


@manager_router.get(
    # NOTE: /items/ (plural) so the path is not shadowed by the
    # /item/recycle-bin/{recycle_bin_id} catch-all on token_router,
    # which is registered earlier (token_router < manager_router).
    "/items/recycle-bin/status",
    tags=[tag],
    response_model=RecycleBinStatusResponse,
    summary="Get recycle bin status",
    description="Returns recycle bin entry counts by status. Managers see only their category.",
)
async def get_recycle_bin_status(request: Request):
    try:
        category_id = (
            request.token_payload["category_id"]
            if request.token_payload["role_id"] == "manager"
            else None
        )
        return JSONResponse(
            content=RecycleBinService.get_status(category_id=category_id),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve recycle bin status",
            traceback.format_exc(),
        )


@manager_router.get(
    "/items/recycle-bin/admin-entries",
    tags=[tag],
    summary="Get recycle bin entries with item counts (admin view)",
    description=(
        "Returns the full list of recycle bin entries with per-item-type "
        "counts (desktops, templates, storages, deployments, etc.) for the "
        "admin recycle bin table. Managers see only their own category. "
        "Optionally filter by a specific entry status."
    ),
)
async def get_recycle_bin_admin_entries(request: Request, status: str | None = None):
    try:
        category_id = (
            request.token_payload["category_id"]
            if request.token_payload["role_id"] == "manager"
            else None
        )
        return JSONResponse(
            content=RecycleBinService.get_item_count(
                category_id=category_id, status=status
            ),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve recycle bin admin entries",
            traceback.format_exc(),
        )


@manager_router.put(
    "/item/recycle-bin/update-task",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update recycle bin task status",
    description="Updates the status of a recycle bin task.",
)
async def update_recycle_bin_task(request: Request, data: RecycleBinUpdateTaskRequest):
    try:
        RecycleBinService.update_task(data.model_dump())
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
            "Failed to update recycle bin task",
            traceback.format_exc(),
        )


# ── Admin-level endpoints ────────────────────────────────────────────────


@admin_router.delete(
    # NOTE: /items/ (plural) so the path is not shadowed by the
    # /item/recycle-bin/{recycle_bin_id} DELETE catch-all on token_router,
    # which is registered earlier (token_router < admin_router).
    "/items/recycle-bin/cutoff-time-surpassed",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete entries past cutoff time",
    description="Permanently deletes all recycle bin entries that have surpassed the cutoff time.",
)
async def delete_cutoff_time_surpassed(request: Request):
    try:
        await RecycleBinService.delete_cutoff_time_surpassed(
            user_id=request.token_payload["user_id"]
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
            "Failed to delete cutoff-surpassed entries",
            traceback.format_exc(),
        )


@admin_router.put(
    "/item/recycle-bin/old-entries/max-time/{max_time}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Set old entries max time",
    description="Sets the maximum time (in hours) before old entries are processed.",
)
async def set_old_entries_max_time(request: Request, max_time: str):
    try:
        RecycleBinService.set_old_entries_max_time(max_time)
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
            "Failed to set old entries max time",
            traceback.format_exc(),
        )


@admin_router.put(
    "/item/recycle-bin/old-entries/action/{action}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Set old entries action",
    description="Sets the action to perform on old entries (delete or none).",
)
async def set_old_entries_action(request: Request, action: OldEntriesActionEnum):
    try:
        RecycleBinService.set_old_entries_action(action.value)
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
            "Failed to set old entries action",
            traceback.format_exc(),
        )


@admin_router.get(
    "/item/recycle-bin/old-entries/config",
    tags=[tag],
    response_model=RecycleBinOldEntriesConfig,
    summary="Get old entries configuration",
    description="Returns the configuration for old recycle bin entries.",
)
async def get_old_entries_config(request: Request):
    try:
        config = RecycleBinService.get_old_entries_config()
        return JSONResponse(
            content=RecycleBinOldEntriesConfig(**config).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve old entries config",
            traceback.format_exc(),
        )


@admin_router.put(
    "/item/recycle-bin/old-entries/delete",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete old entries",
    description="Permanently deletes recycle bin entries older than the configured max time.",
)
async def delete_old_entries(request: Request):
    try:
        RecycleBinService.delete_old_entries()
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
            "Failed to delete old entries",
            traceback.format_exc(),
        )


@admin_router.put(
    "/item/recycle-bin/config/default-delete",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Set default delete behavior",
    description="Sets whether items are sent to recycle bin or deleted permanently by default.",
)
async def set_default_delete(request: Request, data: RecycleBinSetDefaultDeleteRequest):
    try:
        RecycleBinService.set_default_delete(data.rb_default)
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
            "Failed to set default delete behavior",
            traceback.format_exc(),
        )


@admin_router.get(
    "/item/recycle-bin/config/delete-action",
    tags=[tag],
    response_model=str,
    summary="Get delete action",
    description="Returns the configured delete action (move or delete).",
)
async def get_delete_action(request: Request):
    try:
        return JSONResponse(
            content=RecycleBinService.get_delete_action(),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve delete action",
            traceback.format_exc(),
        )


@admin_router.put(
    "/item/recycle-bin/config/delete-action/{action}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Set delete action",
    description="Sets the delete action (move to recycle bin or delete permanently).",
)
async def set_delete_action(request: Request, action: DeleteActionEnum):
    try:
        RecycleBinService.set_delete_action(action.value)
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
            "Failed to set delete action",
            traceback.format_exc(),
        )


@admin_router.get(
    "/items/recycle-bin/unused-item-timeout-rules",
    tags=[tag],
    response_model=UnusedItemTimeoutRulesResponse,
    summary="Get all unused item timeout rules",
    description="Returns all configured unused item timeout rules.",
)
async def get_all_unused_item_timeout_rules(request: Request):
    try:
        rules = RecycleBinService.get_all_unused_item_timeout_rules()
        return JSONResponse(
            content=UnusedItemTimeoutRulesResponse(
                rules=rules,
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve unused item timeout rules",
            traceback.format_exc(),
        )


@admin_router.get(
    "/item/recycle-bin/unused-item-timeout-rule/{rule_id}",
    tags=[tag],
    summary="Get unused item timeout rule",
    description="Returns a specific unused item timeout rule.",
)
async def get_unused_item_timeout_rule(request: Request, rule_id: str):
    try:
        rule = RecycleBinService.get_unused_item_timeout_rule(rule_id)
        return JSONResponse(
            content=rule,
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve unused item timeout rule",
            traceback.format_exc(),
        )


@admin_router.post(
    "/items/recycle-bin/unused-item-timeout-rules",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Create unused item timeout rule",
    description="Creates a new unused item timeout rule.",
    status_code=201,
)
async def create_unused_item_timeout_rule(
    request: Request, data: UnusedItemTimeoutRuleCreateRequest
):
    try:
        rule_id = RecycleBinService.create_unused_item_timeout_rule(data.model_dump())
        return JSONResponse(
            content=SimpleResponse(id=rule_id).model_dump(mode="json"),
            status_code=201,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create unused item timeout rule",
            traceback.format_exc(),
        )


@admin_router.put(
    "/item/recycle-bin/unused-item-timeout-rule/{rule_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update unused item timeout rule",
    description="Updates an existing unused item timeout rule.",
)
async def update_unused_item_timeout_rule(
    request: Request,
    rule_id: str,
    data: UnusedItemTimeoutRuleUpdateRequest,
):
    try:
        RecycleBinService.update_unused_item_timeout_rule(
            rule_id, data.model_dump(exclude_none=True)
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
            "Failed to update unused item timeout rule",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/item/recycle-bin/unused-item-timeout-rule/{rule_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete unused item timeout rule",
    description="Deletes an unused item timeout rule.",
)
async def delete_unused_item_timeout_rule(request: Request, rule_id: str):
    try:
        RecycleBinService.delete_unused_item_timeout_rule(rule_id)
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
            "Failed to delete unused item timeout rule",
            traceback.format_exc(),
        )


@admin_router.post(
    "/recycle-bin/unused-items",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Send unused items to recycle bin",
    description="Finds unused desktops and sends them to the recycle bin. "
    "Called by the scheduler for automatic cleanup.",
    responses={500: {"model": ErrorResponse}},
)
async def recycle_bin_add_unused_items(request: Request):
    try:
        from isardvdi_common.lib.domains.desktops.desktops import Desktops

        unused = Desktops.get_unused_desktops()
        for desktop in unused:
            try:
                RecycleBinService.delete_item(desktop["id"], "isard-scheduler")
            except Error:
                raise
            except Exception:
                pass  # best-effort
        return JSONResponse(
            content=EmptyResponse().model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to process unused items",
            traceback.format_exc(),
        )
