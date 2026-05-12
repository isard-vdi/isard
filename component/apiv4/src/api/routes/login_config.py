#
#   Copyright © 2026 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

"""Public ``/item/login-config`` endpoints.

Both endpoints serve the login-page configuration consumed by Vue 2
(``old-frontend``) and Vue 3 (``component/frontend``). Grouped here per
the apiv4 skill rule B5 (one resource → one route file). The previous
split across ``login.py`` (no category) and ``open.py`` (per category)
forced two writers to clear caches owned by routes/open.py via lazy
imports — the cache now lives in ``services.login_config_cache``.
"""

import asyncio
import traceback

from api import open_router
from api.schemas.common import ErrorResponse
from api.schemas.login import LoginConfigResponse
from api.services.admin.categories import AdminCategoryService
from api.services.config import ConfigService
from api.services.error import Error
from api.services.login_config_cache import login_config_cache
from cachetools import cached
from fastapi import Request
from fastapi.responses import JSONResponse

tag = "login"


@open_router.get(
    "/item/login-config",
    tags=[tag],
    # Pin the legacy ``apiV4LoginConfig`` operation_id so the generated
    # openapi-ts client keeps producing ``apiV4LoginConfigOptions`` —
    # consumed by Vue 3's LoginView, MaintenanceView, RegisterView,
    # DirectViewerView. The 51f865b6d consolidation renamed the
    # function from ``api_v4_login_config`` to ``get_login_config`` and
    # silently dropped the prefix from the auto-derived operation_id,
    # breaking every consumer until codegen ran. Set it explicitly so
    # future renames don't regress the wire contract.
    operation_id="apiV4LoginConfig",
    response_model=LoginConfigResponse,
    summary="Get login configuration",
    description="Returns login page configuration including notifications.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_login_config(request: Request):
    try:
        config = await asyncio.to_thread(ConfigService.get_login_config)
        return JSONResponse(
            content=LoginConfigResponse(**config).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve login configuration",
            traceback.format_exc(),
        )


@cached(
    cache=login_config_cache,
    key=lambda r, cid: cid,
)
@open_router.get(
    "/item/login-config/{category_id}",
    tags=[tag],
    response_model=LoginConfigResponse,
    summary="Get login config for category",
    description="Returns login configuration for a specific category, falling back to global.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_login_config_by_category(request: Request, category_id: str):
    try:
        config = await asyncio.to_thread(
            AdminCategoryService.get_login_config_for_category, category_id
        )

        return JSONResponse(
            content=LoginConfigResponse(**config).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve login config for category '{category_id}'",
            traceback.format_exc(),
        )
