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

import asyncio
import traceback

from api import admin_router
from api.schemas.admin.orchestrator_config import (
    OrchestratorConfigResponse,
    OrchestratorConfigUpdateRequest,
)
from api.schemas.common import ErrorResponse
from api.services.admin.orchestrator_config import AdminOrchestratorConfigService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse, Response

tag = "admin-orchestrator-config"


@admin_router.get(
    "/admin/item/orchestrator-config",
    tags=[tag],
    response_model=OrchestratorConfigResponse,
    summary="Get orchestrator configuration",
    description="Returns whether the orchestrator is enabled.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_orchestrator_config(request: Request):
    try:
        enabled = await asyncio.to_thread(
            AdminOrchestratorConfigService.get_orchestrator_config
        )
        return JSONResponse(
            content=OrchestratorConfigResponse(enabled=enabled).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get orchestrator configuration",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/item/orchestrator-config",
    tags=[tag],
    status_code=204,
    response_class=Response,
    summary="Update orchestrator configuration",
    description="Enables or disables the orchestrator.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_orchestrator_config_update(
    request: Request, data: OrchestratorConfigUpdateRequest
):
    try:
        await asyncio.to_thread(
            AdminOrchestratorConfigService.update_orchestrator_config, data.enabled
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update orchestrator configuration",
            traceback.format_exc(),
        )
