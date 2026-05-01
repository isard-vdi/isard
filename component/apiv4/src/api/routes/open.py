#
#   Copyright © 2025 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

import base64
import glob
import os
import traceback

from api import admin_router, advanced_router, manager_router, open_router, token_router
from api.schemas.common import ErrorResponse
from api.schemas.open import ApiVersion
from api.services.admin.categories import AdminCategoryService
from api.services.categories import CategoryService
from api.services.error import Error
from api.services.login_config_cache import logo_cache
from cachetools import TTLCache, cached
from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response

# with open("/version", "r") as file:
#     version = file.read()

# Named caches: api_version is a constant during a process lifetime, and
# category custom_url is admin-edited via writers that should invalidate.
api_version_cache: TTLCache = TTLCache(maxsize=1, ttl=360)
category_custom_url_cache: TTLCache = TTLCache(maxsize=1, ttl=20)


def clear_category_custom_url_cache() -> None:
    """Invalidate the custom_url cache after a category-branding write."""
    category_custom_url_cache.clear()


@cached(cache=api_version_cache)
@open_router.get(
    "/",
    response_model=ApiVersion,
    summary="Get API Version",
    description="Returns the current version of the API and IsardVDI.",
)
async def api_version():
    try:
        response = ApiVersion(
            name="IsardVDI",
            api_version="4.0-alpha1",
            isardvdi_version="fastapi",
            usage=os.environ["USAGE"],  # Raises KeyError if missing
        )
        return response
    except KeyError:
        return JSONResponse(
            content={"error": "USAGE environment variable is missing"},
            status_code=500,
        )


@cached(cache=category_custom_url_cache)
@open_router.get(
    "/item/category/{category_id}/custom_url",
    tags=["categories"],
    summary="Get category custom login URL",
    description="Returns the custom login URL for a specific category.",
    response_model=str,
    responses={
        500: {"model": ErrorResponse},
    },
)
async def api_v4_category_custom_url(category_id: str, request: Request):
    # Returned as a JSON-encoded string so the OAS spec (and every
    # generated client built from it) sees `application/json` and parses
    # the body with `response.json()`. Returning `PlainTextResponse`
    # here used to mismatch the spec, which crashed
    # `isardvdi_apiv4_client._parse_response` with
    # `JSONDecodeError: Expecting value` on the Flask webapp logout
    # path. Webapp consumers that decode the raw bytes still work —
    # `"my-url"` strips back to `my-url` via `.strip('"')`.
    try:
        return CategoryService.get_category_custom_login_url(category_id)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve custom URL for category '{category_id}'",
            traceback.format_exc(),
        )


_DEFAULT_LOGO_PATH = "/usr/share/nginx/html/default_logo.svg"
# Admin-mounted per-deployment branding. ``docker-compose-parts/apiv4.yml``
# bind-mounts ``/opt/isard/frontend/custom`` → ``/static/custom`` (rw), so
# dropping ``logo.<ext>`` there provides a deployment-wide fallback when
# no per-category branding is configured.
_STATIC_CUSTOM_LOGO_GLOB = "/static/custom/logo.*"

_LOGO_MIME_TYPES = {
    "svg": "image/svg+xml",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "ico": "image/x-icon",
}


@cached(cache=logo_cache, key=lambda r: r.headers.get("host", ""))
@open_router.get(
    "/logo",
    tags=["categories"],
    summary="Get logo",
    description="Returns the logo for the requesting domain. Falls back to the default logo.",
    responses={
        200: {"description": "Logo image file"},
        404: {"model": ErrorResponse},
    },
)
async def get_logo(request: Request):
    try:
        domain = request.headers.get("host", "").split(":")[0]
        data_url = AdminCategoryService.get_logo_by_domain(domain)
        if data_url and data_url.startswith("data:"):
            header, b64_data = data_url.split(",", 1)
            mime_type = header.split(":")[1].split(";")[0]
            file_bytes = base64.b64decode(b64_data)
            return Response(
                content=file_bytes,
                media_type=mime_type,
                headers={
                    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
                    "Cache-Control": "public, max-age=60",
                },
            )
        for path in sorted(glob.glob(_STATIC_CUSTOM_LOGO_GLOB)):
            try:
                with open(path, "rb") as f:
                    file_bytes = f.read()
            except OSError:
                continue
            ext = os.path.splitext(path)[1].lstrip(".").lower()
            media_type = _LOGO_MIME_TYPES.get(ext, "application/octet-stream")
            return Response(
                content=file_bytes,
                media_type=media_type,
                headers={
                    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
                    "Cache-Control": "public, max-age=60",
                },
            )
        if os.path.isfile(_DEFAULT_LOGO_PATH):
            with open(_DEFAULT_LOGO_PATH, "rb") as f:
                return Response(
                    content=f.read(),
                    media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=300"},
                )
        return Response(status_code=404)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve logo",
            traceback.format_exc(),
        )


if os.environ.get("USAGE", "production") != "production":

    @token_router.get("/test/payload")
    async def test_payload(request: Request):
        """Debug endpoint: returns decoded JWT payload (devel only)"""
        return request.token_payload
