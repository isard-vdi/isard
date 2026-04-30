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

import traceback

from api import admin_router
from api.schemas.admin.smtp import (
    SmtpConfigRequest,
    SmtpConfigResponse,
    SmtpTestResponse,
)
from api.schemas.common import ErrorResponse
from api.services.admin.smtp import AdminSmtpService
from api.services.error import Error
from cachetools import TTLCache, cached
from fastapi import Request
from fastapi.responses import JSONResponse

tag = "admin-smtp"

# Named caches so the PUT and POST writers below can drop them and tests
# can clear between cases. 5 s TTL is mainly thundering-herd protection.
smtp_config_cache: TTLCache = TTLCache(maxsize=1, ttl=5)
smtp_enabled_cache: TTLCache = TTLCache(maxsize=1, ttl=5)


def clear_smtp_caches() -> None:
    """Invalidate both SMTP read caches after admin_smtp_put."""
    smtp_config_cache.clear()
    smtp_enabled_cache.clear()


# ══════════════════════════════════════════════════════════════════════════
#  SMTP Configuration
# ══════════════════════════════════════════════════════════════════════════


@cached(cache=smtp_config_cache)
@admin_router.get(
    "/smtp",
    tags=[tag],
    response_model=SmtpConfigResponse,
    summary="Get SMTP configuration",
    description="Returns the current SMTP configuration.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_smtp_get(request: Request) -> SmtpConfigResponse:
    try:
        config = AdminSmtpService.get_smtp_config()
        return SmtpConfigResponse(**(config or {}))
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get SMTP configuration",
            traceback.format_exc(),
        )


@admin_router.put(
    "/smtp",
    tags=[tag],
    response_model=SmtpConfigResponse,
    summary="Update SMTP configuration",
    description="Updates and saves the SMTP configuration.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_smtp_put(
    request: Request, data: SmtpConfigRequest
) -> SmtpConfigResponse:
    try:
        config = AdminSmtpService.update_smtp_config(data.model_dump(exclude_none=True))
        return SmtpConfigResponse(**(config or {}))
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update SMTP configuration",
            traceback.format_exc(),
        )


@cached(cache=smtp_enabled_cache)
@admin_router.get(
    "/smtp/enabled",
    tags=[tag],
    response_model=bool,
    summary="Get SMTP enabled status",
    description="Returns whether SMTP is enabled.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_smtp_enabled_get(request: Request) -> bool:
    try:
        return AdminSmtpService.get_smtp_enabled()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get SMTP enabled status",
            traceback.format_exc(),
        )


@admin_router.post(
    "/smtp/test",
    tags=[tag],
    response_model=SmtpTestResponse,
    summary="Test SMTP configuration",
    description="Tests an SMTP configuration by connecting and authenticating.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_smtp_test_post(request: Request, data: SmtpConfigRequest):
    try:
        result = AdminSmtpService.test_smtp(data.model_dump(exclude_none=True))
        return result
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to test SMTP configuration",
            traceback.format_exc(),
        )
