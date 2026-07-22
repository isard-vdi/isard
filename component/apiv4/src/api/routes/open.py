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

import asyncio
import base64
import glob
import hashlib
import os
import traceback
from typing import Optional

from api import admin_router, advanced_router, manager_router, open_router, token_router
from api.schemas.common import ErrorResponse
from api.schemas.open import ApiVersion
from api.services.admin.categories import AdminCategoryService
from api.services.categories import CategoryService
from api.services.error import Error
from api.services.login_config_cache import logo_cache, logo_collapsed_cache
from cachetools import cached
from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache

try:
    with open("/version", "r") as file:
        version = file.read()
except OSError:
    # /version is baked into the image at build time; absent when running tests
    version = ""

# Named caches: api_version is a constant during a process lifetime, and
# category custom_url is admin-edited via writers that should invalidate.
api_version_cache: SynchronizedTTLCache = SynchronizedTTLCache(maxsize=1, ttl=360)
category_custom_url_cache: SynchronizedTTLCache = SynchronizedTTLCache(
    maxsize=1, ttl=20
)


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
        response = JSONResponse(
            content=ApiVersion(
                name="IsardVDI",
                api_version="4.0-alpha1",
                isardvdi_version=version,
                usage=os.environ["USAGE"],  # Raises KeyError if missing
            ).model_dump(mode="json"),
            status_code=200,
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
        # TODO*: This endpoint calls a function that does not exsist
        return JSONResponse(
            content=await asyncio.to_thread(
                CategoryService.get_category_custom_login_url, category_id
            ),
            status_code=200,
        )
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
_DEFAULT_LOGO_COLLAPSED_PATH = "/usr/share/nginx/html/default_logo_collapsed.svg"
# Admin-mounted per-deployment branding. ``docker-compose-parts/apiv4.yml``
# bind-mounts ``/opt/isard/frontend/custom`` → ``/static/custom`` (rw), so
# dropping ``logo.<ext>`` there provides a deployment-wide fallback when
# no per-category branding is configured.
_STATIC_CUSTOM_LOGO_GLOB = "/static/custom/logo.*"
# Same admin-mounted directory, separate file for the collapsed-sidebar
# variant. ``component/frontend``'s ``Sidebar.vue`` requests both via the
# API; no per-category DB column for the collapsed variant yet, so this
# endpoint is glob-only and 404s when nothing is uploaded (Vue then falls
# back to the bundled ``LogoCollapsedSvg`` asset).
_STATIC_CUSTOM_LOGO_COLLAPSED_GLOB = "/static/custom/logo-collapsed.*"

_LOGO_MIME_TYPES = {
    "svg": "image/svg+xml",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "ico": "image/x-icon",
}


_LOGO_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
    "Cache-Control": "public, max-age=300",
}


def _serve_logo_from_glob(glob_pattern: str) -> Optional[Response]:
    """Serve the first readable file matching the glob as a Response.

    Returns ``None`` when no file matches so the caller can decide on the
    fallback (default-logo file for ``/logo``, plain 404 for
    ``/logo-collapsed``). The matching file's extension drives the
    ``media_type`` via :data:`_LOGO_MIME_TYPES`; unknown extensions fall
    back to ``application/octet-stream``.
    """
    for path in sorted(glob.glob(glob_pattern)):
        try:
            with open(path, "rb") as f:
                file_bytes = f.read()
        except OSError:
            continue
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        media_type = _LOGO_MIME_TYPES.get(ext, "application/octet-stream")
        return Response(
            content=file_bytes, media_type=media_type, headers=_LOGO_HEADERS
        )
    return None


def _logo_response_chain(
    candidates: list[tuple[str | None, str]],
    default_path: str | None,
) -> Response:
    for data_url, glob_pattern in candidates:
        if data_url and data_url.startswith("data:"):
            header, b64_data = data_url.split(",", 1)
            mime_type = header.split(":")[1].split(";")[0]
            return Response(
                content=base64.b64decode(b64_data),
                media_type=mime_type,
                headers=_LOGO_HEADERS,
            )
        response = _serve_logo_from_glob(glob_pattern)
        if response is not None:
            return response
    if default_path and os.path.isfile(default_path):
        with open(default_path, "rb") as f:
            return Response(
                content=f.read(),
                media_type="image/svg+xml",
                headers={"Cache-Control": "public, max-age=300"},
            )
    return Response(status_code=404)


def _logo_response(
    data_url: str | None,
    glob_pattern: str = _STATIC_CUSTOM_LOGO_GLOB,
    default_path: str | None = _DEFAULT_LOGO_PATH,
) -> Response:
    """Serve a branding logo: data URL → static glob → default file → 404.

    ``default_path=None`` skips the default-file step and returns 404. Thin
    single-candidate wrapper over :func:`_logo_response_chain`.
    """
    return _logo_response_chain([(data_url, glob_pattern)], default_path)


def _with_etag(request: Request, response: Response) -> Response:
    """Attach a strong ETag to a 200 image response and honour If-None-Match.

    Returns a 304 (empty body) when the client's If-None-Match matches, so
    repeat loads of the public logo endpoints cost nothing downstream.
    """
    if response.status_code != 200 or not getattr(response, "body", None):
        return response
    etag = '"%s"' % hashlib.sha256(response.body).hexdigest()
    if request.headers.get("if-none-match") == etag:
        not_modified = Response(status_code=304)
        not_modified.headers["ETag"] = etag
        not_modified.headers["Cache-Control"] = _LOGO_HEADERS["Cache-Control"]
        return not_modified
    response.headers["ETag"] = etag
    return response


# cachetools.cached can't wrap the async endpoint (it would cache the
# coroutine and break on a second await), and placing it above @router.get
# is a no-op since FastAPI registers the unwrapped handler. So cache the
# synchronous DB+filesystem resolution instead, keyed by domain.
@cached(cache=logo_cache, key=lambda domain: domain)
def _logo_data_url_by_domain(domain: str) -> str | None:
    return AdminCategoryService.get_logo_by_domain(domain)


@cached(cache=logo_collapsed_cache, key=lambda domain: domain)
def _logo_collapsed_data_url_by_domain(domain: str) -> str | None:
    return AdminCategoryService.get_logo_collapsed_by_domain(domain)


@open_router.get(
    "/logo",
    tags=["categories"],
    response_class=Response,
    summary="Get logo",
    description="Returns the logo for the requesting domain. Falls back to the default logo.",
    responses={
        200: {
            "description": "Logo image file",
            "content": {
                "image/png": {},
                "image/jpeg": {},
                "image/svg+xml": {},
                "image/*": {},
            },
        },
        404: {"model": ErrorResponse},
    },
)
async def get_logo(request: Request):
    try:
        domain = request.headers.get("host", "").split(":")[0].lower()
        data_url = await asyncio.to_thread(_logo_data_url_by_domain, domain)
        return _with_etag(request, _logo_response(data_url))
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve logo",
            traceback.format_exc(),
        )


@open_router.get(
    "/logo/category/{category_id}",
    tags=["categories"],
    response_class=Response,
    summary="Get category logo",
    description="Returns the branding logo for a category. Falls back to the default logo.",
    responses={
        200: {
            "description": "Logo image file",
            "content": {
                "image/png": {},
                "image/jpeg": {},
                "image/svg+xml": {},
                "image/*": {},
            },
        },
        404: {"model": ErrorResponse},
    },
)
async def get_category_logo(category_id: str, request: Request):
    try:
        data_url = await asyncio.to_thread(
            AdminCategoryService.get_logo_by_category, category_id
        )
        return _with_etag(request, _logo_response(data_url))
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve logo for category '{category_id}'",
            traceback.format_exc(),
        )


@open_router.get(
    "/logo-collapsed",
    tags=["categories"],
    response_class=Response,
    summary="Get collapsed logo",
    description=(
        "Returns the collapsed-sidebar logo for the requesting domain. "
        "Falls back through the configured collapsed logo, then the "
        "configured full logo, and finally the bundled default collapsed logo."
    ),
    responses={
        200: {
            "description": "Collapsed logo image file",
            "content": {
                "image/png": {},
                "image/jpeg": {},
                "image/svg+xml": {},
                "image/*": {},
            },
        },
        404: {"model": ErrorResponse},
    },
)
async def get_logo_collapsed(request: Request):
    try:
        domain = request.headers.get("host", "").split(":")[0].lower()
        collapsed_url, logo_url = await asyncio.gather(
            asyncio.to_thread(_logo_collapsed_data_url_by_domain, domain),
            asyncio.to_thread(_logo_data_url_by_domain, domain),
        )
        return _with_etag(
            request,
            _logo_response_chain(
                [
                    (collapsed_url, _STATIC_CUSTOM_LOGO_COLLAPSED_GLOB),
                    (logo_url, _STATIC_CUSTOM_LOGO_GLOB),
                ],
                default_path=_DEFAULT_LOGO_COLLAPSED_PATH,
            ),
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve collapsed logo",
            traceback.format_exc(),
        )


@open_router.get(
    "/logo-collapsed/category/{category_id}",
    tags=["categories"],
    response_class=Response,
    summary="Get category collapsed logo",
    description=(
        "Returns the collapsed-sidebar branding logo for a category. Falls "
        "back through the category's collapsed logo, then its full logo, "
        "and finally the bundled default collapsed logo."
    ),
    responses={
        200: {
            "description": "Collapsed logo image file",
            "content": {
                "image/png": {},
                "image/jpeg": {},
                "image/svg+xml": {},
                "image/*": {},
            },
        },
        404: {"model": ErrorResponse},
    },
)
async def get_category_logo_collapsed(category_id: str, request: Request):
    try:
        collapsed_url, logo_url = await asyncio.gather(
            asyncio.to_thread(
                AdminCategoryService.get_logo_collapsed_by_category, category_id
            ),
            asyncio.to_thread(AdminCategoryService.get_logo_by_category, category_id),
        )
        return _with_etag(
            request,
            _logo_response_chain(
                [
                    (collapsed_url, _STATIC_CUSTOM_LOGO_COLLAPSED_GLOB),
                    (logo_url, _STATIC_CUSTOM_LOGO_GLOB),
                ],
                default_path=_DEFAULT_LOGO_COLLAPSED_PATH,
            ),
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve collapsed logo for category '{category_id}'",
            traceback.format_exc(),
        )


if os.environ.get("USAGE", "production") != "production":

    @token_router.get("/test/payload", response_model=dict)
    async def test_payload(request: Request):
        """Debug endpoint: returns decoded JWT payload (devel only)"""
        return request.token_payload
